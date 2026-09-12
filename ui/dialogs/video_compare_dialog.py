from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTime, QUrl
from PySide6.QtGui import QColor, QFont
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class VideoCompareDialog(QDialog):
    """Side-by-side Video Comparison Dialog: Original vs Anti-Duplicate Protected."""

    def __init__(
        self,
        original_video_path: str,
        processed_video_path: str,
        decisions: Optional[List[Any]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.original_video_path = str(original_video_path or "").strip()
        self.processed_video_path = str(processed_video_path or "").strip()
        self.decisions = list(decisions or [])
        self._is_seeking = False
        self._audio_source = "processed"  # "processed" or "original"

        self.setWindowTitle("So sánh Video: Gốc vs Đã xử lý Chống trùng lặp (Anti-Duplicate)")
        self.resize(1120, 780)
        self.setMinimumSize(920, 640)
        self._apply_theme()

        self._init_players()
        self._build_ui()
        self._populate_table()

    def _apply_theme(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            }
            QLabel {
                color: #cbd5e1;
            }
            QFrame#card {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }
            QPushButton#primaryBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 7px 16px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #3b82f6;
            }
            QPushButton#secondaryBtn {
                background-color: #334155;
                color: #e2e8f0;
                border: 1px solid #475569;
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: 600;
                font-size: 12px;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #475569;
                color: #ffffff;
            }
            QPushButton#audioToggleBtn {
                background-color: #1e3a5f;
                color: #93c5fd;
                border: 1px solid #3b82f6;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#audioToggleBtn:hover {
                background-color: #2563eb;
                color: #ffffff;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #334155;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #3b82f6;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #60a5fa;
                border: 1px solid #2563eb;
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
            QTableWidget {
                background-color: #111827;
                color: #e2e8f0;
                border: 1px solid #1f2937;
                gridline-color: #1f2937;
                border-radius: 6px;
                font-size: 12px;
            }
            QTableWidget::item:selected {
                background-color: #1e3a8a;
                color: #ffffff;
            }
            QHeaderView::section {
                background-color: #1f2937;
                color: #93c5fd;
                padding: 5px;
                border: none;
                border-bottom: 1px solid #374151;
                font-weight: 600;
                font-size: 12px;
            }
        """)

    def _init_players(self):
        # Original Player
        self.orig_player = QMediaPlayer(self)
        self.orig_audio = QAudioOutput(self)
        self.orig_player.setAudioOutput(self.orig_audio)
        if self.original_video_path and os.path.exists(self.original_video_path):
            self.orig_player.setSource(QUrl.fromLocalFile(self.original_video_path))
        self.orig_audio.setMuted(True)  # Muted by default, listen to processed

        # Processed (Anti-Duplicate) Player
        self.proc_player = QMediaPlayer(self)
        self.proc_audio = QAudioOutput(self)
        self.proc_player.setAudioOutput(self.proc_audio)
        if self.processed_video_path and os.path.exists(self.processed_video_path):
            self.proc_player.setSource(QUrl.fromLocalFile(self.processed_video_path))
        self.proc_audio.setMuted(False)  # Unmuted by default

        self.proc_player.positionChanged.connect(self._on_player_position_changed)
        self.proc_player.durationChanged.connect(self._on_player_duration_changed)

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(10)

        # 1. Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("🔍 So sánh Video: Gốc vs Đã xử lý Chống trùng lặp (Anti-Duplicate)")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title.setStyleSheet("color: #f8fafc;")
        title_box.addWidget(title)

        subtitle = QLabel(
            "Phát song song để trực tiếp kiểm tra hình ảnh (Zoom 105%+, Đổi màu vi sai, Lệch góc) "
            "và âm thanh (Dịch cao độ Pitch shift ±2%)."
        )
        subtitle.setStyleSheet("color: #94a3b8; font-size: 12px;")
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)

        header_layout.addStretch()
        close_btn = QPushButton("✕ Đóng", self)
        close_btn.setObjectName("secondaryBtn")
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        root_layout.addLayout(header_layout)

        # 2. Summary Badge Chips
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        num_shots = len(self.decisions)
        badges = [
            f"🛡️ Trạng thái: Đã kháng Content ID ({num_shots} shot)",
            "🪞 Phản chiếu: Đã lật ngang (CapCut Mirror)",
            "📐 Khung hình: Cắt viền 5% + Chuẩn YouTube 16:9",
            "🔍 Zoom: Điểm nhấn ngắt quãng (Không chóng mặt)",
            "🎵 Audio Fingerprint: Phá hủy (Pitch ±1.5%)",
        ]
        for badge_text in badges:
            b_label = QLabel(badge_text)
            b_label.setStyleSheet("""
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            """)
            badge_row.addWidget(b_label)
        badge_row.addStretch()
        root_layout.addLayout(badge_row)

        # 3. Side-by-Side Video Players
        video_splitter = QSplitter(Qt.Horizontal)
        video_splitter.setHandleWidth(8)

        # Left: Original Video
        orig_box = QFrame()
        orig_box.setObjectName("card")
        orig_layout = QVBoxLayout(orig_box)
        orig_layout.setContentsMargins(8, 8, 8, 8)
        orig_layout.setSpacing(6)
        orig_header = QLabel("🎞️ VIDEO GỐC (Chưa can thiệp)")
        orig_header.setStyleSheet("color: #cbd5e1; font-weight: 700; font-size: 12px;")
        orig_layout.addWidget(orig_header)
        self.orig_video_widget = QVideoWidget()
        self.orig_video_widget.setMinimumHeight(240)
        self.orig_video_widget.setStyleSheet("background-color: #000000; border-radius: 4px;")
        self.orig_player.setVideoOutput(self.orig_video_widget)
        orig_layout.addWidget(self.orig_video_widget, 1)
        video_splitter.addWidget(orig_box)

        # Right: Protected Video
        proc_box = QFrame()
        proc_box.setObjectName("card")
        proc_layout = QVBoxLayout(proc_box)
        proc_layout.setContentsMargins(8, 8, 8, 8)
        proc_layout.setSpacing(6)
        proc_header = QLabel("🛡️ VIDEO ĐÃ XỬ LÝ (Phản chiếu CapCut · Cắt viền 16:9 · Pitch Audio)")
        proc_header.setStyleSheet("color: #4ade80; font-weight: 700; font-size: 12px;")
        proc_layout.addWidget(proc_header)
        self.proc_video_widget = QVideoWidget()
        self.proc_video_widget.setMinimumHeight(240)
        self.proc_video_widget.setStyleSheet("background-color: #000000; border-radius: 4px;")
        self.proc_player.setVideoOutput(self.proc_video_widget)
        proc_layout.addWidget(self.proc_video_widget, 1)
        video_splitter.addWidget(proc_box)

        root_layout.addWidget(video_splitter, 3)

        # 4. Master Playback Controls
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(12, 8, 12, 8)
        ctrl_layout.setSpacing(6)

        # Slider and time
        time_row = QHBoxLayout()
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600; min-width: 90px;")
        time_row.addWidget(self.time_label)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderMoved.connect(self._on_slider_moved)
        self.seek_slider.sliderPressed.connect(self._on_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_slider_released)
        time_row.addWidget(self.seek_slider, 1)
        ctrl_layout.addLayout(time_row)

        # Button row
        btn_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Phát cả hai")
        self.play_btn.setObjectName("primaryBtn")
        self.play_btn.clicked.connect(self._toggle_playback)
        btn_row.addWidget(self.play_btn)

        step_back_btn = QPushButton("⏪ -5s")
        step_back_btn.setObjectName("secondaryBtn")
        step_back_btn.clicked.connect(lambda: self._step_relative(-5000))
        btn_row.addWidget(step_back_btn)

        step_fwd_btn = QPushButton("+5s ⏩")
        step_fwd_btn.setObjectName("secondaryBtn")
        step_fwd_btn.clicked.connect(lambda: self._step_relative(5000))
        btn_row.addWidget(step_fwd_btn)

        btn_row.addSpacing(16)
        self.audio_toggle_btn = QPushButton("🔊 Đang nghe: Video Đã xử lý (Nhấn để chuyển sang Video Gốc)")
        self.audio_toggle_btn.setObjectName("audioToggleBtn")
        self.audio_toggle_btn.clicked.connect(self._toggle_audio_source)
        btn_row.addWidget(self.audio_toggle_btn)

        btn_row.addStretch()
        ctrl_layout.addLayout(btn_row)
        root_layout.addWidget(ctrl_card)

        # 5. Shot-by-Shot Inspection Table
        table_title_row = QHBoxLayout()
        table_title = QLabel("📋 Danh sách chi tiết các can thiệp từng Shot (Bấm vào dòng để nhảy đến cảnh đó):")
        table_title.setStyleSheet("font-weight: 700; color: #cbd5e1; font-size: 12px;")
        table_title_row.addWidget(table_title)
        root_layout.addLayout(table_title_row)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Cảnh #",
            "Thời gian",
            "Zoom (Visual)",
            "Màu sắc (Hash)",
            "Khung hình / Góc",
            "Âm thanh (Pitch)",
            "Ghi chú bảo vệ",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.cellClicked.connect(self._on_table_row_clicked)
        self.table.setFixedHeight(150)
        root_layout.addWidget(self.table, 1)

    def _populate_table(self):
        self.table.setRowCount(0)
        if not self.decisions:
            self.table.setRowCount(1)
            item = QTableWidgetItem("Không có danh sách EDL cụ thể. Toàn bộ video đã được áp dụng bộ lọc Chống trùng lặp 1-pass.")
            self.table.setItem(0, 0, item)
            self.table.setSpan(0, 0, 1, 7)
            return

        self.table.setRowCount(len(self.decisions))
        for idx, d in enumerate(self.decisions):
            start = float(getattr(d, "start_time", 0.0) or 0.0)
            end = float(getattr(d, "end_time", 0.0) or 0.0)
            zoom = float(getattr(d, "zoom_scale", 1.0) or 1.0)
            color = bool(getattr(d, "color_grade", True))
            pan = str(getattr(d, "pan_direction", "none") or "none")
            crop = str(getattr(d, "crop_mode", "none") or "none")
            flip = bool(getattr(d, "horizontal_flip", False))
            pitch = bool(getattr(d, "pitch_shift", True))
            notes = str(getattr(d, "recap_notes", "") or "")

            zoom_str = f"Zoom {int(round(zoom * 100))}%" if zoom > 1.01 else "105% (Cắt viền 16:9)"
            color_str = "✓ Đổi màu vi sai" if color else "Gốc"

            frame_parts = []
            if flip:
                frame_parts.append("Phản chiếu (Lật an toàn)")
            if pan != "none":
                frame_parts.append(f"Pan {pan}")
            if crop != "none":
                frame_parts.append(f"Crop {crop}")
            if not frame_parts:
                frame_parts.append("Cắt viền 16:9")
            frame_str = " · ".join(frame_parts)

            audio_str = "✓ Dịch cao độ ±1.5%" if pitch else "Gốc"

            row_items = [
                f"Shot {idx + 1}",
                f"{self._format_sec(start)} - {self._format_sec(end)}",
                zoom_str,
                color_str,
                frame_str,
                audio_str,
                notes,
            ]
            for col, val in enumerate(row_items):
                cell = QTableWidgetItem(val)
                cell.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if col in (2, 3, 5):
                    cell.setForeground(QColor("#4ade80"))  # Highlight protection green
                self.table.setItem(idx, col, cell)

    def _format_sec(self, seconds: float) -> str:
        s = int(seconds)
        m = s // 60
        sec = s % 60
        return f"{m:02d}:{sec:02d}"

    def _on_player_position_changed(self, pos_ms: int):
        if not self._is_seeking:
            dur = self.proc_player.duration()
            if dur > 0:
                val = int((pos_ms / dur) * 1000)
                self.seek_slider.blockSignals(True)
                self.seek_slider.setValue(val)
                self.seek_slider.blockSignals(False)
            curr = QTime(0, 0, 0).addMSecs(pos_ms).toString("mm:ss")
            total = QTime(0, 0, 0).addMSecs(dur).toString("mm:ss")
            self.time_label.setText(f"{curr} / {total}")

            # Highlight corresponding row in table
            curr_sec = pos_ms / 1000.0
            for idx, d in enumerate(self.decisions):
                start = float(getattr(d, "start_time", 0.0) or 0.0)
                end = float(getattr(d, "end_time", 0.0) or 0.0)
                if start <= curr_sec <= end:
                    self.table.selectRow(idx)
                    break

    def _on_player_duration_changed(self, dur_ms: int):
        curr = QTime(0, 0, 0).addMSecs(self.proc_player.position()).toString("mm:ss")
        total = QTime(0, 0, 0).addMSecs(dur_ms).toString("mm:ss")
        self.time_label.setText(f"{curr} / {total}")

    def _on_slider_pressed(self):
        self._is_seeking = True

    def _on_slider_moved(self, val: int):
        dur = self.proc_player.duration()
        if dur > 0:
            target_ms = int((val / 1000.0) * dur)
            self._seek_both(target_ms)

    def _on_slider_released(self):
        self._is_seeking = False
        val = self.seek_slider.value()
        dur = self.proc_player.duration()
        if dur > 0:
            target_ms = int((val / 1000.0) * dur)
            self._seek_both(target_ms)

    def _seek_both(self, pos_ms: int):
        self.proc_player.setPosition(pos_ms)
        self.orig_player.setPosition(pos_ms)

    def _step_relative(self, delta_ms: int):
        cur = self.proc_player.position()
        target = max(0, min(self.proc_player.duration(), cur + delta_ms))
        self._seek_both(target)

    def _toggle_playback(self):
        is_playing = self.proc_player.playbackState() == QMediaPlayer.PlayingState
        if is_playing:
            self.proc_player.pause()
            self.orig_player.pause()
            self.play_btn.setText("▶ Phát cả hai")
        else:
            # Sync positions before playing
            cur = self.proc_player.position()
            self.orig_player.setPosition(cur)
            self.proc_player.play()
            self.orig_player.play()
            self.play_btn.setText("⏸ Tạm dừng")

    def _toggle_audio_source(self):
        if self._audio_source == "processed":
            self._audio_source = "original"
            self.proc_audio.setMuted(True)
            self.orig_audio.setMuted(False)
            self.audio_toggle_btn.setText("🔊 Đang nghe: Video Gốc (Nhấn để chuyển sang Video Đã xử lý)")
            self.audio_toggle_btn.setStyleSheet("background-color: #334155; color: #f8fafc;")
        else:
            self._audio_source = "processed"
            self.proc_audio.setMuted(False)
            self.orig_audio.setMuted(True)
            self.audio_toggle_btn.setText("🔊 Đang nghe: Video Đã xử lý (Nhấn để chuyển sang Video Gốc)")
            self.audio_toggle_btn.setStyleSheet("background-color: #1e3a5f; color: #93c5fd;")

    def _on_table_row_clicked(self, row: int, _col: int):
        if 0 <= row < len(self.decisions):
            d = self.decisions[row]
            start_ms = int(float(getattr(d, "start_time", 0.0) or 0.0) * 1000)
            self._seek_both(start_ms)

    def closeEvent(self, event):
        try:
            self.orig_player.stop()
            self.proc_player.stop()
        except Exception:
            pass
        super().closeEvent(event)
