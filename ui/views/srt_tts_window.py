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
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QSlider,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from helpers.srt_helpers import format_segments_to_srt, validate_srt_text
from runtime_paths import asset_path, bin_path, sanitize_ffmpeg_diagnostics, subprocess_text_kwargs
from services import ProjectService, VoiceCatalogService, ResourceDownloadService
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
                raise FileNotFoundError(f"FFmpeg not found: {ffmpeg}")
            os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
            self.progress.emit(10, "Encoding voice audio to MP3…")
            result = subprocess.run(
                self.build_command(ffmpeg, self.voice_path, self.output_path),
                capture_output=True,
                timeout=3600,
                **subprocess_text_kwargs(),
            )
            if result.returncode != 0 or not os.path.isfile(self.output_path):
                raise RuntimeError(
                    sanitize_ffmpeg_diagnostics(result.stderr or result.stdout)
                    or "FFmpeg could not create the MP3 file."
                )
            self.progress.emit(100, "MP3 export complete")
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
        self.preview_worker = None
        self._sample_player = None
        self._track_player = None
        self._busy = False
        self._close_when_idle = False
        self.catalog = VoiceCatalogService(self.workspace_root).load_catalog()
        self.setWindowTitle("VIUStudio — SRT to TTS MP3")
        self.setMinimumSize(760, 560)
        self.resize(1040, 820)
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
                background: #090d19;
                color: #e2e8f0;
                font-family: 'Segoe UI';
                font-size: 13px;
            }
            QFrame#card {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #101625, stop:1 #0b0f19);
                border: 1px solid #35416b;
                border-radius: 16px;
            }
            QFrame#card:hover {
                border-color: #607bd9;
            }
            QLabel { background: transparent; }
            QLabel#voiceHint { color: #95accb; font-size: 12px; }
            QLabel#cardTitle {
                color: #8faaff;
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
                border-color: #8b9bff;
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
                color: #e2f8ff;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #06b6d4, stop:0.6 #10b981, stop:1 #34d399);
                border-radius: 4px;
            }
        """)
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        header = QHBoxLayout()
        header_left = QVBoxLayout()
        header_left.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("SRT → TTS → MP3")
        title.setStyleSheet("font-size: 22px; font-weight: 850; color: #ffffff; letter-spacing: -0.3px;")
        title_row.addWidget(title)
        fast_badge = QLabel("FAST-TRACK STUDIO")
        fast_badge.setStyleSheet(
            "background: rgba(99, 102, 241, 0.12); border: 1px solid rgba(99, 102, 241, 0.3); "
            "color: #a5b4fc; border-radius: 999px; padding: 3px 10px; font-size: 10px; font-weight: 750;"
        )
        title_row.addWidget(fast_badge)
        title_row.addStretch(1)
        header_left.addLayout(title_row)

        hint = QLabel("Turn subtitles into a voice track. Choose a voice, match your timing, and export MP3.")
        hint.setStyleSheet("color: #94a3b8; font-size: 12px;")
        header_left.addWidget(hint)
        header.addLayout(header_left, 1)

        launcher_btn = QPushButton("← Launcher")
        launcher_btn.setObjectName("launcher")
        launcher_btn.setCursor(Qt.PointingHandCursor)
        launcher_btn.setToolTip("Return to the launcher")
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

        self.srt_label = QLabel("No subtitle file selected")
        self.srt_label.setStyleSheet(
            "color: #64748b; font-size: 12px; background: #070b13; border: 1px dashed #1c273c; "
            "border-radius: 8px; padding: 7px 12px;"
        )
        self.srt_btn = QPushButton("Import SRT…")
        self.srt_btn.setCursor(Qt.PointingHandCursor)
        self.srt_btn.clicked.connect(self._choose_srt)
        srt_row = QHBoxLayout()
        srt_row.setSpacing(10)
        srt_row.addWidget(self.srt_label, 1)
        srt_row.addWidget(self.srt_btn)
        input_layout.addRow("Subtitle file", srt_row)
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
        self.language_combo.addItem("Vietnamese", "vi")
        self.language_combo.addItem("English", "en")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)

        self.voice_combo = QComboBox()
        self.engine_combo = QComboBox()
        for label, value in (
            ("Select TTS engine…", ""),
            ("Piper [VI/EN] · Fast · Offline", "piper"),
            ("Edge TTS [VI/EN] · Natural · Online", "edge"),
            ("ZeroTTS [VI] · Local", "zerotts"),
            ("Kokoro-82M [EN] · Local", "kokoro"),
            ("KorvaTTS [VI/EN] · Not available", "korvatts"),
        ):
            self.engine_combo.addItem(label, value)
        self.engine_combo.currentIndexChanged.connect(self._on_language_changed)
        self.gender_combo = QComboBox()
        for label, value in (("Any", "any"), ("Female", "female"), ("Male", "male")):
            self.gender_combo.addItem(label, value)
        self.gender_combo.currentIndexChanged.connect(self._on_language_changed)
        self.voice_hint = QLabel()
        self.voice_hint.setObjectName("voiceHint")
        self.voice_hint.setWordWrap(True)
        self.preview_voice_btn = QPushButton("Hear Sample")
        self.preview_voice_btn.setToolTip("Generate and listen to a short sample of this voice")
        self.preview_voice_btn.clicked.connect(self._preview_voice)
        self.manage_voice_btn = QPushButton("Manage Voices")
        self.manage_voice_btn.clicked.connect(self._manage_voices)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.75, 1.25)
        self.speed_spin.setSingleStep(0.05)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setSuffix("x")

        self.sync_combo = QComboBox()
        self.sync_combo.addItem("Smart · Fit speech to subtitle timing", "smart")
        self.sync_combo.addItem("Off · Report speech that exceeds its cue", "off")

        self.voice_combo.currentIndexChanged.connect(self._invalidate_voice)
        self.speed_spin.valueChanged.connect(self._invalidate_voice)
        self.sync_combo.currentIndexChanged.connect(self._invalidate_voice)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        filters.addWidget(self.language_combo, 1)
        filters.addWidget(QLabel("Voice type"))
        filters.addWidget(self.gender_combo, 1)
        settings_layout.addRow("Language", filters)
        settings_layout.addRow("Voice engine", self.engine_combo)
        voice_row = QHBoxLayout()
        voice_row.setSpacing(8)
        voice_row.addWidget(self.voice_combo, 1)
        voice_row.addWidget(self.preview_voice_btn)
        voice_row.addWidget(self.manage_voice_btn)
        settings_layout.addRow("Voice", voice_row)
        settings_layout.addRow("", self.voice_hint)
        timing_row = QHBoxLayout()
        timing_row.setSpacing(10)
        self.speed_spin.setMaximumWidth(100)
        timing_row.addWidget(self.speed_spin)
        timing_row.addWidget(QLabel("Timing"))
        timing_row.addWidget(self.sync_combo, 1)
        settings_layout.addRow("Speed", timing_row)
        settings_card_layout.addLayout(settings_layout)
        root.addWidget(settings_card)

        # ── SRT preview & execution ──
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Your subtitle text and timecodes will appear here after import…")
        self.preview.setMaximumHeight(115)
        root.addWidget(self.preview)

        playback_card = QFrame()
        playback_card.setObjectName("card")
        playback = QVBoxLayout(playback_card)
        playback.setContentsMargins(14, 10, 14, 10)
        playback.addWidget(QLabel("3. LISTEN TO GENERATED AUDIO"))
        player_row = QHBoxLayout()
        player_row.setSpacing(8)
        self.play_voice_btn = QPushButton("Play Voice")
        self.play_voice_btn.setToolTip("Listen to the complete generated TTS track before export")
        self.play_voice_btn.clicked.connect(self._toggle_track)
        self.stop_voice_btn = QPushButton("Stop")
        self.stop_voice_btn.clicked.connect(self._stop_track)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderMoved.connect(self._seek_track)
        self.play_time = QLabel("00:00 / 00:00")
        for widget in (self.play_voice_btn, self.stop_voice_btn):
            player_row.addWidget(widget)
        player_row.addWidget(self.seek_slider, 1)
        player_row.addWidget(self.play_time)
        playback.addLayout(player_row)
        root.addWidget(playback_card)

        status_row = QHBoxLayout()
        self.status = QLabel("●  Ready — import an SRT and choose your voice")
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

        self.generate_btn = QPushButton("Generate Voice")
        self.generate_btn.setObjectName("primary")
        self.generate_btn.setFixedHeight(36)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self._generate_voice)

        self.export_btn = QPushButton("Export MP3")
        self.export_btn.setObjectName("export")
        self.export_btn.setFixedHeight(36)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export_mp3)

        actions.addWidget(self.generate_btn)
        actions.addWidget(self.export_btn)
        root.addLayout(actions)

        # Real Qt glow effects: CSS box-shadow is not supported by Qt.
        from PySide6.QtGui import QColor
        for widget, color, blur in (
            (title, "#555ed9", 18),
            (input_card, "#263961", 20),
            (settings_card, "#454197", 24),
            (self.generate_btn, "#7364ff", 26),
            (self.export_btn, "#10b99b", 24),
        ):
            effect = QGraphicsDropShadowEffect(widget)
            shade = QColor(color)
            shade.setAlpha(125)
            effect.setColor(shade)
            effect.setBlurRadius(blur)
            effect.setOffset(0, 0)
            widget.setGraphicsEffect(effect)

    def _on_language_changed(self, *_args):
        self._refresh_voices()
        self._invalidate_voice()

    def _invalidate_voice(self, *_args):
        self._stop_track()
        if self._sample_player is not None:
            self._sample_player.stop()
        had_voice = bool(self.voice_path)
        self.voice_path = ""
        if had_voice and not self._busy:
            self.status.setText("Voice settings changed. Generate the voice again before exporting.")
            self.status.setStyleSheet("color: #fbbf24; font-weight: 700; font-size: 12px;")
        self._update_actions()

    def _update_actions(self):
        if not hasattr(self, "generate_btn"):
            return
        has_srt = bool(self.srt_text and self.source_segments)
        has_voice = bool(self.voice_path and os.path.isfile(self.voice_path))
        selected = bool(self.voice_combo.currentData())
        self.generate_btn.setEnabled((not self._busy) and has_srt and selected)
        self.preview_voice_btn.setEnabled(not self._busy and selected)
        self.export_btn.setEnabled((not self._busy) and has_voice)
        for control in (self.play_voice_btn, self.stop_voice_btn, self.seek_slider):
            control.setEnabled(not self._busy and has_voice)
        for button in (self.generate_btn, self.export_btn):
            if button.graphicsEffect() is not None:
                button.graphicsEffect().setEnabled(button.isEnabled())
        self.export_btn.setToolTip("" if has_voice else "Generate TTS voice audio before exporting MP3.")

    def _return_to_launcher(self):
        for worker in (self.voice_worker, self.mp3_worker, self.preview_worker):
            if worker is not None and worker.isRunning():
                QMessageBox.information(
                    self,
                    "Processing",
                    "Wait for the current task to finish before returning to the launcher.",
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
        engine = self.engine_combo.currentData()
        gender = self.gender_combo.currentData()
        resources = ResourceDownloadService(self.workspace_root)
        for key, label in (("zerotts", "ZeroTTS [VI]"), ("kokoro", "Kokoro-82M [EN]")):
            index = self.engine_combo.findData(key)
            ready = resources.is_resource_installed(f"tts:{key}")
            self.engine_combo.setItemText(index, f"{label} · Local · {'Installed' if ready else 'Not installed'}")
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for entry in self.catalog:
            if (entry.get("enabled", True) and entry.get("provider") == engine
                    and str(entry.get("language", "")).lower().split("-", 1)[0] == language
                    and (gender == "any" or entry.get("gender") == gender)):
                value = str(entry.get("id")) if engine == "piper" else f"{engine}:{entry.get('provider_voice')}"
                self.voice_combo.addItem(str(entry.get("name") or entry.get("id")), value)
        index = self.voice_combo.findData(current)
        if index >= 0: self.voice_combo.setCurrentIndex(index)
        self.voice_combo.blockSignals(False)
        if not engine:
            hint = "Choose an engine, then a voice. Language selects pronunciation; it does not translate the SRT."
        elif engine == "korvatts":
            hint = "KorvaTTS is not integrated. Choose an available engine."
        elif not self.voice_combo.count():
            hint = "No matching voices. Check language/type or install voices using Manage Voices."
        elif engine == "edge":
            hint = f"{self.voice_combo.count()} voices · Internet required. Text is sent to Microsoft's speech service. No voice model download."
        else:
            hint = f"{self.voice_combo.count()} voices · Offline. Required runtime/models are checked before preview and generation."
        self.voice_hint.setText(hint)

    def _manage_voices(self):
        from views.resource_manager import open_resource_manager
        open_resource_manager(self.workspace_root, parent=self)
        self.catalog = VoiceCatalogService(self.workspace_root).load_catalog()
        self._on_language_changed()

    def _validate_voice(self):
        voice = str(self.voice_combo.currentData() or "")
        if not voice:
            return False
        issues = ResourceDownloadService(self.workspace_root).validate_tts_voice_runtime(voice)
        if issues:
            QMessageBox.warning(self, "Voice unavailable", "\n".join(message for _, message in issues))
            return False
        return True

    def _preview_voice(self):
        if self._busy or not self._validate_voice():
            return
        self._stop_track()
        text = "Hello, this is a preview of the selected voice." if self.language_combo.currentData() == "en" else "Xin chào, đây là giọng đọc bạn đã chọn."
        self._set_busy(True)
        folder = os.path.join(self.workspace_root, "temp", "srt_voice_preview")
        # Same synthesis and speed path as generation, without importing an SRT
        # or publishing sample audio as an exportable project voice track.
        worker = _VoiceWorker(self.workspace_root, [{"start": 0.0, "end": 15.0, "text": text}],
                              folder, folder, str(self.voice_combo.currentData()),
                              self.speed_spin.value(), "smart", "")
        self.preview_worker = worker
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._preview_done)
        worker.finished.connect(lambda: self._worker_finished("preview_worker", worker))
        worker.start()

    def _preview_done(self, path, _segments, error):
        if error:
            QMessageBox.warning(self, "Voice preview failed", error)
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        if self._sample_player is None:
            self._sample_player = QMediaPlayer(self)
            self._sample_output = QAudioOutput(self)
            self._sample_player.setAudioOutput(self._sample_output)
        self._sample_player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
        self._sample_player.play()
        self.status.setText("Playing selected voice preview")

    def _toggle_track(self):
        if self._busy or not self.voice_path or not os.path.isfile(self.voice_path):
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        if self._sample_player is not None:
            self._sample_player.stop()
        if self._track_player is None:
            self._track_player = QMediaPlayer(self)
            self._track_output = QAudioOutput(self)
            self._track_player.setAudioOutput(self._track_output)
            self._track_player.positionChanged.connect(self._track_position)
            self._track_player.durationChanged.connect(self.seek_slider.setMaximum)
            self._track_player.playbackStateChanged.connect(
                lambda state: self.play_voice_btn.setText(
                    "Pause" if state == QMediaPlayer.PlayingState else "Play Voice"))
            self._track_player.errorOccurred.connect(
                lambda _error, message: self.status.setText(f"Audio playback failed: {message}"))
        source = QUrl.fromLocalFile(os.path.abspath(self.voice_path))
        if self._track_player.source() != source:
            self._track_player.setSource(source)
        if self._track_player.playbackState() == QMediaPlayer.PlayingState:
            self._track_player.pause()
        else:
            self._track_player.play()

    def _track_position(self, position):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)
        duration = self._track_player.duration() if self._track_player else 0
        def clock(ms):
            seconds = max(0, int(ms)) // 1000
            return f"{seconds // 60:02d}:{seconds % 60:02d}"
        self.play_time.setText(f"{clock(position)} / {clock(duration)}")

    def _seek_track(self, position):
        if self._track_player is not None:
            self._track_player.setPosition(position)

    def _stop_track(self):
        if self._track_player is not None:
            self._track_player.stop()
        if hasattr(self, "seek_slider"):
            self.seek_slider.setValue(0)
            self.play_voice_btn.setText("Play Voice")

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
            QMessageBox.critical(self, "SRT error", str(exc)); return
        valid, segments, error = validate_srt_text(text)
        if not valid:
            QMessageBox.warning(self, "Invalid SRT", error); return
        self.srt_path = os.path.abspath(path)
        self.srt_text = text
        self.source_segments = deepcopy(segments)
        self.segments = deepcopy(segments)
        self.srt_label.setText(f"{os.path.basename(path)} • {len(segments)} cues")
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
        self.state.set_setting("voice_engine", self.engine_combo.currentData())
        self.state.set_setting("voice_name", self.voice_combo.currentData())
        self.state.set_setting("voice_speed", self.speed_spin.value())
        self.state.set_setting("voice_timing_sync_mode", self.sync_combo.currentData())
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
        if self._busy:
            self._stop_track()
            if self._sample_player is not None:
                self._sample_player.stop()
        for control in (
            self.srt_btn,
            self.language_combo,
            self.engine_combo,
            self.gender_combo,
            self.manage_voice_btn,
            self.voice_combo,
            self.speed_spin,
            self.sync_combo,
        ):
            control.setEnabled(not self._busy)
        self._update_actions()

    def _generate_voice(self):
        if not self.source_segments:
            QMessageBox.warning(self, "No subtitles", "Import an SRT file first."); return
        voice_id = str(self.voice_combo.currentData() or "")
        if not voice_id:
            QMessageBox.warning(self, "No voice selected", "Choose an available voice for this language."); return
        if not self._validate_voice():
            return
        self._ensure_project()
        self._set_busy(True)
        self.progress.setValue(0)
        self.status.setText("Generating voice audio…")
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
            self.status.setText("Voice generation failed")
            self.status.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            QMessageBox.critical(self, "TTS error", error or "No voice audio was generated.")
            return
        self.voice_path = voice_path
        if segments: self.segments = list(segments)
        self.progress.setValue(100)
        self.status.setText("●  Voice ready — export your MP3")
        self.status.setStyleSheet("color: #34d399; font-weight: 700; font-size: 12px;")

    def _export_mp3(self):
        if not self.voice_path or not os.path.isfile(self.voice_path):
            QMessageBox.warning(self, "No voice audio", "Generate voice audio before exporting MP3.")
            return
        suggested = os.path.splitext(os.path.basename(self.srt_path))[0] + "_tts.mp3"
        output, _ = QFileDialog.getSaveFileName(
            self,
            "Export Voice as MP3",
            os.path.join(os.path.dirname(self.srt_path), suggested),
            "MP3 Audio (*.mp3)",
        )
        if not output:
            return
        if not output.lower().endswith(".mp3"):
            output += ".mp3"
        self._set_busy(True)
        self.progress.setValue(0)
        self.status.setText("Exporting MP3…")
        self.status.setStyleSheet("color: #38bdf8; font-weight: 700; font-size: 12px;")
        self.mp3_worker = _Mp3ExportWorker(self.voice_path, output)
        worker = self.mp3_worker
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._mp3_done)
        worker.finished.connect(lambda worker=worker: self._worker_finished("mp3_worker", worker))
        worker.start()

    def _mp3_done(self, output, error):
        if error:
            self.status.setText("MP3 export failed")
            self.status.setStyleSheet("color: #f87171; font-weight: 700; font-size: 12px;")
            QMessageBox.critical(self, "MP3 export error", error)
            return
        self.progress.setValue(100)
        self.status.setText("●  MP3 export complete")
        self.status.setStyleSheet("color: #34d399; font-weight: 700; font-size: 12px;")
        QMessageBox.information(self, "Export complete", f"MP3 saved to:\n\n{output}")

    def _worker_finished(self, attribute_name, worker):
        """Release a QThread only after Qt confirms that its run method exited."""
        if getattr(self, attribute_name, None) is worker:
            setattr(self, attribute_name, None)
        worker.deleteLater()
        if not any(
            item is not None and item.isRunning()
            for item in (self.voice_worker, self.mp3_worker, self.preview_worker)
        ):
            self._set_busy(False)
            if self._close_when_idle:
                self._close_when_idle = False
                QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        running = [
            worker
            for worker in (self.voice_worker, self.mp3_worker, self.preview_worker)
            if worker is not None and worker.isRunning()
        ]
        if running:
            event.ignore()
            self._close_when_idle = True
            self.status.setText("Stopping the current task before closing…")
            for worker in running:
                worker.requestInterruption()
            return
        if self._sample_player is not None:
            self._sample_player.stop()
        self._stop_track()
        super().closeEvent(event)
