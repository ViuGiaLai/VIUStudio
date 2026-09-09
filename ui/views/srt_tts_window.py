from __future__ import annotations

import os
import subprocess
from copy import deepcopy

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QApplication,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from helpers.srt_helpers import format_segments_to_srt, validate_srt_text
from runtime_paths import asset_path, bin_path, sanitize_ffmpeg_diagnostics, subprocess_text_kwargs
from services import ProjectService, VoiceCatalogService
from workflows.voice_workflow import VoiceWorkflow


class _VoiceWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(str, object, str)

    def __init__(self, workspace_root, segments, output_dir, temp_dir, voice_id, speed, sync_mode, state_path):
        super().__init__()
        self.args = (workspace_root, segments, output_dir, temp_dir, voice_id, speed, sync_mode, state_path)

    def run(self):
        root, segments, output_dir, temp_dir, voice_id, speed, sync_mode, state_path = self.args
        try:
            def report(event):
                percent = int(getattr(event, "percent", 0) or 0)
                message = str(getattr(event, "message", event) or "Generating voice…")
                self.progress.emit(percent, message)
            result = VoiceWorkflow(root).run(
                segments=segments,
                output_dir=output_dir,
                voice_name=voice_id,
                voice_speed=float(speed),
                timing_sync_mode=sync_mode,
                project_state_path=state_path,
                project_temp_dir=temp_dir,
                on_progress=report,
                cancellation_check=self.isInterruptionRequested,
            )
            self.completed.emit(str(result.get("voice_track", "")), result.get("segments", []), "")
        except Exception as exc:
            self.completed.emit("", [], str(exc))


class _Mp3ExportWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(str, str)

    def __init__(self, voice_path: str, output_path: str):
        super().__init__()
        self.voice_path = voice_path
        self.output_path = output_path

    @staticmethod
    def build_command(ffmpeg_path: str, voice_path: str, output_path: str) -> list[str]:
        return [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-i", voice_path,
            "-vn",
            "-codec:a", "libmp3lame",
            "-b:a", "192k",
            "-id3v2_version", "3",
            output_path,
        ]

    def run(self):
        try:
            ffmpeg = str(bin_path("ffmpeg", "ffmpeg.exe"))
            if not os.path.isfile(ffmpeg):
                raise FileNotFoundError(f"Không tìm thấy FFmpeg: {ffmpeg}")
            os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
            self.progress.emit(10, "Đang chuyển giọng TTS sang MP3…")
            result = subprocess.run(
                self.build_command(ffmpeg, self.voice_path, self.output_path),
                capture_output=True,
                timeout=3600,
                **subprocess_text_kwargs(),
            )
            if result.returncode != 0 or not os.path.isfile(self.output_path):
                raise RuntimeError(
                    sanitize_ffmpeg_diagnostics(result.stderr or result.stdout)
                    or "FFmpeg không tạo được file MP3."
                )
            self.progress.emit(100, "Xuất MP3 hoàn tất")
            self.completed.emit(self.output_path, "")
        except Exception as exc:
            self.completed.emit("", str(exc))


class SrtTtsWindow(QMainWindow):
    """Lightweight SRT → TTS → MP3 workspace sharing the production backend."""

    def __init__(self, workspace_root: str):
        super().__init__()
        self.workspace_root = os.path.abspath(workspace_root)
        self.srt_path = ""
        self.srt_text = ""
        self.voice_path = ""
        self.source_segments = []
        self.segments = []
        self.state = None
        self.voice_worker = None
        self.mp3_worker = None
        self._busy = False
        self._close_when_idle = False
        self.catalog = VoiceCatalogService(self.workspace_root).load_catalog()
        self.setWindowTitle("VIUStudio — SRT to TTS MP3")
        self.setMinimumSize(760, 560)
        self.resize(900, 680)
        icon_path = asset_path("viustudio.png")
        if os.path.isfile(icon_path):
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(icon_path))
        self._build_ui()
        self._refresh_voices()
        self._update_actions()

    def _build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #080b12;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
                font-size: 13px;
            }
            QFrame#card {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101625, stop:1 #0b0f19);
                border: 1px solid #1c273c;
                border-radius: 12px;
            }
            QFrame#card:hover {
                border-color: #263550;
            }
            QLabel#cardTitle {
                color: #818cf8;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.8px;
                text-transform: uppercase;
            }
            QLabel#fieldLabel {
                color: #94a3b8;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton {
                background-color: #121826;
                color: #cbd5e1;
                font-weight: 600;
                font-size: 12px;
                border-radius: 8px;
                border: 1px solid #1f2b40;
                padding: 7px 14px;
            }
            QPushButton:hover {
                background-color: #1a2438;
                border-color: #3b82f6;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #25334d;
                padding-top: 8px;
            }
            QPushButton:disabled {
                color: #475569;
                background-color: #0c101a;
                border-color: #162030;
            }
            QPushButton#primary {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
                border: 1px solid #818cf8;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                padding: 9px 20px;
                border-radius: 9px;
            }
            QPushButton#primary:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #818cf8, stop:1 #6366f1);
                border-color: #a5b4fc;
            }
            QPushButton#primary:pressed {
                background-color: #3730a3;
                padding-top: 10px;
            }
            QPushButton#primary:disabled {
                background-color: #151829;
                color: #4b5275;
                border-color: #1f243d;
            }
            QPushButton#export {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                border: 1px solid #34d399;
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                padding: 9px 20px;
                border-radius: 9px;
            }
            QPushButton#export:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34d399, stop:1 #10b981);
                border-color: #6ee7b7;
            }
            QPushButton#export:pressed {
                background-color: #047857;
                padding-top: 10px;
            }
            QPushButton#export:disabled {
                background-color: #0f1d19;
                color: #3a564d;
                border-color: #172b25;
            }
            QPushButton#launcher {
                background-color: #0f1524;
                color: #94a3b8;
                border: 1px solid #1e2a40;
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 600;
            }
            QPushButton#launcher:hover {
                background-color: #172138;
                color: #ffffff;
                border-color: #6366f1;
            }
            QComboBox, QDoubleSpinBox {
                background-color: #080d16;
                color: #f1f5f9;
                border: 1px solid #1c273c;
                border-radius: 8px;
                padding: 6px 10px;
                min-height: 24px;
                font-size: 12px;
                font-weight: 500;
            }
            QComboBox:hover, QDoubleSpinBox:hover {
                border-color: #3b82f6;
                background-color: #0b1220;
            }
            QComboBox:focus, QDoubleSpinBox:focus {
                border-color: #6366f1;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #94a3b8;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #0d1424;
                border: 1px solid #23324d;
                border-radius: 8px;
                color: #f1f5f9;
                selection-background-color: #1c2842;
                selection-color: #38bdf8;
                padding: 4px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #151d2c;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #38bdf8);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
                background: #ffffff;
                border: 2px solid #6366f1;
            }
            QSlider::handle:horizontal:hover {
                background: #e0e7ff;
                border-color: #818cf8;
            }
            QSlider::handle:horizontal:pressed {
                background: #818cf8;
            }
            QCheckBox {
                color: #cbd5e1;
                font-weight: 600;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid #24334a;
                background: #090e18;
            }
            QCheckBox::indicator:hover {
                border-color: #3b82f6;
            }
            QCheckBox::indicator:checked {
                background-color: #4f46e5;
                border-color: #818cf8;
            }
            QPlainTextEdit {
                background-color: #060911;
                color: #93c5fd;
                border: 1px solid #162033;
                border-radius: 10px;
                padding: 10px 12px;
                font-family: 'Cascadia Code', 'Consolas', 'Fira Code', 'Courier New', monospace;
                font-size: 12px;
                line-height: 1.4em;
            }
            QPlainTextEdit:focus {
                border-color: #312e81;
            }
            QProgressBar {
                border: none;
                border-radius: 4px;
                background: #0b101c;
                height: 8px;
                text-align: right;
                color: transparent;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:0.6 #10b981, stop:1 #34d399);
                border-radius: 4px;
            }
        """)
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("SRT → TTS → MP3")
        title.setStyleSheet("font-size: 22px; font-weight: 850; color: #ffffff; letter-spacing: -0.3px;")
        title_row.addWidget(title)
        fast_badge = QLabel("⚡ FAST-TRACK STUDIO")
        fast_badge.setStyleSheet(
            "background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.3); "
            "color: #a5b4fc; border-radius: 999px; padding: 3px 10px; font-size: 10px; font-weight: 750;"
        )
        title_row.addWidget(fast_badge)
        title_row.addStretch(1)
        header_left.addLayout(title_row)

        hint = QLabel("Workspace riêng, không tải timeline, thumbnail, OCR, ASR hay Full Pipeline.")
        hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        header_left.addWidget(hint)
        header.addLayout(header_left, 1)

        launcher_btn = QPushButton("← Launcher")
        launcher_btn.setObjectName("launcher")
        launcher_btn.setCursor(Qt.PointingHandCursor)
        launcher_btn.setToolTip("Quay lại màn hình launcher")
        launcher_btn.clicked.connect(self._return_to_launcher)
        header.addWidget(launcher_btn)
        root.addLayout(header)

        # ── Card 1: Input files ──
        input_card = QFrame()
        input_card.setObjectName("card")
        input_card_layout = QVBoxLayout(input_card)
        input_card_layout.setContentsMargins(16, 14, 16, 14)
        input_card_layout.setSpacing(10)

        card1_title = QLabel("1. IMPORT SUBTITLE")
        card1_title.setObjectName("cardTitle")
        input_card_layout.addWidget(card1_title)

        input_layout = QFormLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setVerticalSpacing(8)

        self.srt_label = QLabel("Chưa import file phụ đề .srt")
        self.srt_label.setStyleSheet(
            "color: #64748b; font-size: 12px; background: #070b13; border: 1px dashed #1c273c; "
            "border-radius: 8px; padding: 7px 12px;"
        )
        self.srt_btn = QPushButton("📝  Import SRT…")
        self.srt_btn.setCursor(Qt.PointingHandCursor)
        self.srt_btn.clicked.connect(self._choose_srt)
        srt_row = QHBoxLayout()
        srt_row.setSpacing(10)
        srt_row.addWidget(self.srt_label, 1)
        srt_row.addWidget(self.srt_btn)
        input_layout.addRow("Phụ đề SRT", srt_row)
        input_card_layout.addLayout(input_layout)
        root.addWidget(input_card)

        # ── Card 2: Voice & Timing ──
        settings_card = QFrame()
        settings_card.setObjectName("card")
        settings_card_layout = QVBoxLayout(settings_card)
        settings_card_layout.setContentsMargins(16, 14, 16, 14)
        settings_card_layout.setSpacing(10)

        card2_title = QLabel("2. VOICE & TIMING CONFIGURATION")
        card2_title.setObjectName("cardTitle")
        settings_card_layout.addWidget(card2_title)

        settings_layout = QFormLayout()
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setVerticalSpacing(8)

        self.language_combo = QComboBox()
        self.language_combo.addItem("Tiếng Việt", "vi")
        self.language_combo.addItem("English", "en")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        self.voice_combo = QComboBox()
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.75, 1.25)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setSuffix("x")

        self.sync_combo = QComboBox()
        self.sync_combo.addItem("Smart (khuyên dùng)", "smart")
        self.sync_combo.addItem("Tắt", "off")

        self.voice_combo.currentIndexChanged.connect(self._invalidate_voice)
        self.speed_spin.valueChanged.connect(self._invalidate_voice)
        self.sync_combo.currentIndexChanged.connect(self._invalidate_voice)

        settings_layout.addRow("Ngôn ngữ / voice", self.language_combo)
        settings_layout.addRow("Giọng đọc", self.voice_combo)
        settings_layout.addRow("Tốc độ", self.speed_spin)
        settings_layout.addRow("Khớp thời gian", self.sync_combo)
        settings_card_layout.addLayout(settings_layout)
        root.addWidget(settings_card)

        # ── SRT preview & execution ──
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Nội dung SRT sẽ hiển thị tại đây khi được nạp…")
        self.preview.setMaximumHeight(115)
        root.addWidget(self.preview)

        status_row = QHBoxLayout()
        self.status = QLabel("●  Sẵn sàng")
        self.status.setStyleSheet("color: #34d399; font-weight: 700; font-size: 12px;")
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch(1)

        self.generate_btn = QPushButton("🎙  Tạo giọng TTS")
        self.generate_btn.setObjectName("primary")
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self._generate_voice)

        self.export_btn = QPushButton("🎵  Xuất MP3")
        self.export_btn.setObjectName("export")
        self.export_btn.setMinimumHeight(40)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_mp3)

        actions.addWidget(self.generate_btn)
        actions.addWidget(self.export_btn)
        root.addLayout(actions)

    def _on_language_changed(self, *_args):
        self._refresh_voices()
        self._invalidate_voice()

    def _invalidate_voice(self, *_args):
        had_voice = bool(self.voice_path)
        self.voice_path = ""
        if had_voice and not self._busy:
            self.status.setText("⚠  Thiết lập TTS đã thay đổi. Hãy tạo lại giọng.")
            self.status.setStyleSheet("color: #fbbf24; font-weight: 700; font-size: 12px;")
        self._update_actions()

    def _update_actions(self):
        if not hasattr(self, "generate_btn"):
            return
        has_srt = bool(self.srt_text and self.source_segments)
        has_voice = bool(self.voice_path and os.path.isfile(self.voice_path))
        self.generate_btn.setEnabled((not self._busy) and has_srt)
        self.export_btn.setEnabled((not self._busy) and has_voice)
        self.export_btn.setToolTip("" if has_voice else "Hãy tạo giọng TTS trước khi xuất MP3.")

    def _return_to_launcher(self):
        for worker in (self.voice_worker, self.mp3_worker):
            if worker is not None and worker.isRunning():
                QMessageBox.information(
                    self,
                    "Đang xử lý",
                    "Hãy chờ tác vụ hiện tại hoàn tất trước khi quay lại Launcher.",
                )
                return

        from views.launcher import LauncherWindow, show_launcher

        self.hide()
        selection = show_launcher(None)
        if not selection:
            self.show()
            return

        if isinstance(selection, dict) and selection.get("launch_mode") == "srt_tts":
            next_window = SrtTtsWindow(self.workspace_root)
            next_window.show()
        else:
            from main_window import VideoTranslatorGUI
            from utils.project_launch import initialize_editor_from_selection

            LauncherWindow.add_recent(None, selection)
            next_window = VideoTranslatorGUI()
            next_window.prepare_initial_editor_layout()
            next_window.show()
            QTimer.singleShot(100, lambda: initialize_editor_from_selection(next_window, selection))

        QApplication.instance()._viustudio_active_window = next_window
        self.close()

    def _refresh_voices(self):
        language = self.language_combo.currentData() if hasattr(self, "language_combo") else "vi"
        current = self.voice_combo.currentData() if hasattr(self, "voice_combo") else ""
        self.voice_combo.clear()
        for entry in self.catalog:
            if str(entry.get("language", "")).lower().startswith(str(language)):
                self.voice_combo.addItem(str(entry.get("name") or entry.get("id")), str(entry.get("id")))
        index = self.voice_combo.findData(current)
        if index >= 0: self.voice_combo.setCurrentIndex(index)

    def _choose_srt(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import SRT",
            os.path.dirname(self.srt_path),
            "Subtitle (*.srt)",
        )
        if not path: return
        try:
            text = open(path, "r", encoding="utf-8-sig").read()
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi SRT", str(exc)); return
        valid, segments, error = validate_srt_text(text)
        if not valid:
            QMessageBox.warning(self, "SRT không hợp lệ", error); return
        self.srt_path = os.path.abspath(path)
        self.srt_text = text
        self.source_segments = deepcopy(segments)
        self.segments = deepcopy(segments)
        self.srt_label.setText(f"📝  {os.path.basename(path)} • {len(segments)} câu")
        self.srt_label.setStyleSheet(
            "color: #f1f5f9; font-size: 12px; font-weight: 600; background: #0c1524; "
            "border: 1px solid #6366f1; border-radius: 8px; padding: 7px 12px;"
        )
        self.preview.setPlainText(text)
        self._invalidate_voice()

    def _ensure_project(self):
        if self.state is None:
            service = ProjectService(self.workspace_root)
            self.state = service.create_project()
        else:
            service = ProjectService(self.workspace_root)
        self.state.input_video = ""
        self.state.target_language = str(self.language_combo.currentData())
        self.state.mode = "voice"
        self.state.set_setting("launch_mode", "srt_tts")
        service.save_project(self.state)
        translation_dir = os.path.join(self.state.project_root, "translation"); os.makedirs(translation_dir, exist_ok=True)
        normalized_srt = os.path.join(translation_dir, "imported_tts.srt")
        # Preserve the imported cue boundaries verbatim. Smart Timing may
        # adapt generated audio inside those windows, but must never rewrite
        # the SRT timecodes the user will later import into CapCut.
        with open(normalized_srt, "w", encoding="utf-8-sig") as handle:
            handle.write((self.srt_text or format_segments_to_srt(self.segments)).strip() + "\n")
        self.state.set_artifact("srt_translated", normalized_srt); ProjectService(self.workspace_root).save_project(self.state)
        return normalized_srt

    def _set_busy(self, busy):
        self._busy = bool(busy)
        for control in (
            self.srt_btn,
            self.language_combo,
            self.voice_combo,
            self.speed_spin,
            self.sync_combo,
        ):
            control.setEnabled(not self._busy)
        self._update_actions()

    def _generate_voice(self):
        if not self.source_segments:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Hãy import file SRT trước."); return
        voice_id = str(self.voice_combo.currentData() or "")
        if not voice_id:
            QMessageBox.warning(self, "Thiếu voice", "Không tìm thấy voice đã cài cho ngôn ngữ này."); return
        self._ensure_project()
        self._set_busy(True)
        self.progress.setValue(0)
        self.status.setText("⚡  Đang tạo giọng TTS…")
        self.status.setStyleSheet("color: #818cf8; font-weight: 700; font-size: 12px;")
        state_path = os.path.join(self.state.project_root, "project.json"); temp_dir = os.path.join(self.state.project_root, "temp", "srt_tts")
        # Every run starts from the imported cue boundaries. The aligned result
        # must not become the input of the next run and accumulate timing drift.
        source_segments = deepcopy(self.source_segments)
        self.voice_worker = _VoiceWorker(self.workspace_root, source_segments, os.path.join(self.state.project_root, "audio"), temp_dir, voice_id, self.speed_spin.value(), str(self.sync_combo.currentData()), state_path)
        worker = self.voice_worker
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._voice_done)
        worker.finished.connect(lambda worker=worker: self._worker_finished("voice_worker", worker))
        worker.start()

    def _on_progress(self, percent, message):
        self.progress.setValue(max(0, min(100, int(percent))))
        self.status.setText(f"⚡  {message}")

    def _voice_done(self, voice_path, segments, error):
        if error or not os.path.isfile(voice_path):
            self.status.setText("⚠  Tạo giọng thất bại")
            self.status.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            QMessageBox.critical(self, "Lỗi TTS", error or "Không tạo được file giọng.")
            return
        self.voice_path = voice_path
        if segments: self.segments = list(segments)
        self.progress.setValue(100)
        self.status.setText("●  Giọng TTS đã sẵn sàng. Có thể xuất MP3.")
        self.status.setStyleSheet("color: #34d399; font-weight: 700; font-size: 12px;")

    def _export_mp3(self):
        if not self.voice_path or not os.path.isfile(self.voice_path):
            QMessageBox.warning(self, "Thiếu giọng TTS", "Hãy tạo giọng TTS trước khi xuất MP3.")
            return
        suggested = os.path.splitext(os.path.basename(self.srt_path))[0] + "_tts.mp3"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất giọng TTS MP3",
            os.path.join(os.path.dirname(self.srt_path), suggested),
            "MP3 Audio (*.mp3)",
        )
        if not output:
            return
        if not output.lower().endswith(".mp3"):
            output += ".mp3"
        self._set_busy(True)
        self.progress.setValue(0)
        self.status.setText("⚡  Đang xuất MP3…")
        self.status.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 12px;")
        self.mp3_worker = _Mp3ExportWorker(self.voice_path, output)
        worker = self.mp3_worker
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._mp3_done)
        worker.finished.connect(lambda worker=worker: self._worker_finished("mp3_worker", worker))
        worker.start()

    def _mp3_done(self, output, error):
        if error:
            self.status.setText("⚠  Xuất MP3 thất bại")
            self.status.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            QMessageBox.critical(self, "Lỗi xuất MP3", error)
            return
        self.progress.setValue(100)
        self.status.setText("●  Xuất MP3 hoàn tất")
        self.status.setStyleSheet("color: #34d399; font-weight: 700; font-size: 12px;")
        QMessageBox.information(self, "Hoàn tất", f"File MP3 đã lưu tại:\n\n{output}")

    def _worker_finished(self, attribute_name, worker):
        """Release a QThread only after Qt confirms that its run method exited."""
        if getattr(self, attribute_name, None) is worker:
            setattr(self, attribute_name, None)
        worker.deleteLater()
        if not any(
            item is not None and item.isRunning()
            for item in (self.voice_worker, self.mp3_worker)
        ):
            self._set_busy(False)
            if self._close_when_idle:
                self._close_when_idle = False
                QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        running = [
            worker
            for worker in (self.voice_worker, self.mp3_worker)
            if worker is not None and worker.isRunning()
        ]
        if running:
            event.ignore()
            self._close_when_idle = True
            self.status.setText("⚠  Đang dừng tác vụ an toàn trước khi đóng…")
            for worker in running:
                worker.requestInterruption()
            return
        super().closeEvent(event)
