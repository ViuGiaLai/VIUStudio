from __future__ import annotations

import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.helpers.srt_helpers import format_timestamp


class SubtitleSyncDialog(QDialog):
    """Dialog to adjust subtitle timing, sync with video start, playhead, or custom offsets."""

    def __init__(self, host, selected_index: int = -1, parent=None):
        dlg_parent = parent if isinstance(parent, QWidget) else (host if isinstance(host, QWidget) else None)
        super().__init__(dlg_parent)
        self.host = host
        self.selected_index = selected_index
        self.setWindowTitle("Đồng bộ & Dịch chuyển thời gian Phụ đề (Subtitle Timing & Sync)")
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.resize(650, 600)

        # Retrieve current segments
        self.active_segments = list(
            (host.current_translated_segments if hasattr(host, "current_translated_segments") and host.current_translated_segments else None)
            or (host.current_segments if hasattr(host, "current_segments") and host.current_segments else None)
            or []
        )

        # Resolve video start time (first non-image video clip, or first clip)
        self.first_video_start = 0.0
        self.video_clips = []
        if hasattr(host, "get_timeline_video_clips"):
            try:
                self.video_clips = host.get_timeline_video_clips(existing_only=False)
            except Exception:
                self.video_clips = []
        if self.video_clips:
            # Find first real video clip, or fallback to first clip
            first_vid = next((c for c in self.video_clips if not getattr(c, "is_image", False)), None)
            if first_vid is None:
                first_vid = self.video_clips[0]
            self.first_video_start = float(
                first_vid.timeline_start if hasattr(first_vid, "timeline_start") else (
                    first_vid.get("timeline_start", 0.0) if isinstance(first_vid, dict) else 0.0
                )
            )

        # Resolve current playhead
        self.playhead_s = 0.0
        if hasattr(host, "timeline_position_ms"):
            self.playhead_s = max(0.0, float(host.timeline_position_ms()) / 1000.0)
        elif hasattr(host, "media_player") and hasattr(host.media_player, "position"):
            self.playhead_s = max(0.0, float(host.media_player.position()) / 1000.0)

        self._setup_style()
        self._init_ui()
        self._update_preview()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0d131f;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                background-color: #131b2c;
                border: 1px solid #23314a;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 16px;
                padding-left: 12px;
                padding-right: 12px;
                padding-bottom: 12px;
                font-size: 12px;
                font-weight: 700;
                color: #93c5fd;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 2px 8px;
                background-color: #1a273e;
                border: 1px solid #2d4263;
                border-radius: 4px;
                color: #bfdbfe;
            }
            QRadioButton {
                color: #e2e8f0;
                font-size: 12px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox {
                color: #e2e8f0;
                font-size: 12px;
                spacing: 8px;
            }
            QDoubleSpinBox {
                background-color: #0b1019;
                color: #38bdf8;
                border: 1px solid #2f4568;
                border-radius: 6px;
                padding: 6px 10px;
                font-family: 'Consolas', monospace;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2b3b52;
                border-color: #475569;
            }
            QPushButton#primaryBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: 1px solid #3b82f6;
            }
            QPushButton#primaryBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#presetBtn {
                background-color: #16243b;
                color: #93c5fd;
                border: 1px solid #273e63;
                text-align: left;
                padding: 8px 12px;
                font-size: 12px;
            }
            QPushButton#presetBtn:hover {
                background-color: #1f3354;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton#nudgeBtn {
                background-color: #182234;
                color: #cbd5e1;
                border: 1px solid #273952;
                padding: 4px 8px;
                font-size: 11px;
                font-family: 'Consolas', monospace;
                min-width: 42px;
            }
            QPushButton#nudgeBtn:hover {
                background-color: #263650;
                color: #38bdf8;
                border-color: #3b82f6;
            }
            QTextEdit#previewBox {
                background-color: #080c14;
                color: #94a3b8;
                border: 1px solid #1e2d42;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                line-height: 1.4;
            }
        """)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 16, 18, 16)
        root_layout.setSpacing(12)

        # 1. Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        title_label = QLabel("⏱️ ĐỒNG BỘ & DỊCH CHUYỂN THỜI GIAN PHỤ ĐỀ")
        title_label.setStyleSheet("color: #60a5fa; font-size: 14px; font-weight: 800; letter-spacing: 0.5px;")
        desc_label = QLabel("Khớp phụ đề vào đầu video, con trỏ xem trước, hoặc dịch chuyển thủ công chính xác từng mili-giây.")
        desc_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        desc_label.setWordWrap(True)
        header_layout.addWidget(title_label)
        header_layout.addWidget(desc_label)
        root_layout.addLayout(header_layout)

        # 2. Scope selection
        scope_group = QGroupBox("1. PHẠM VI ÁP DỤNG (SCOPE)")
        scope_layout = QVBoxLayout(scope_group)
        scope_layout.setSpacing(8)

        total_segs = len(self.active_segments)
        self.radio_all = QRadioButton(f"Toàn bộ phụ đề ({total_segs} câu trên Timeline)")
        self.radio_ripple = QRadioButton(
            f"Từ câu đang chọn #{self.selected_index + 1} đến hết (Ripple Shift từ #{self.selected_index + 1})"
            if 0 <= self.selected_index < total_segs
            else "Từ câu đang chọn về sau (Chưa chọn câu cụ thể)"
        )
        self.radio_selected = QRadioButton(
            f"Chỉ riêng câu đang chọn #{self.selected_index + 1}"
            if 0 <= self.selected_index < total_segs
            else "Chỉ riêng câu đang chọn (Chưa chọn câu cụ thể)"
        )

        self.scope_button_group = QButtonGroup(self)
        self.scope_button_group.addButton(self.radio_all)
        self.scope_button_group.addButton(self.radio_ripple)
        self.scope_button_group.addButton(self.radio_selected)

        if 0 <= self.selected_index < total_segs:
            self.radio_ripple.setChecked(True)
        else:
            self.radio_all.setChecked(True)
            self.radio_ripple.setEnabled(False)
            self.radio_selected.setEnabled(False)

        self.radio_all.toggled.connect(self._update_preview)
        self.radio_ripple.toggled.connect(self._update_preview)
        self.radio_selected.toggled.connect(self._update_preview)

        scope_layout.addWidget(self.radio_all)
        scope_layout.addWidget(self.radio_ripple)
        scope_layout.addWidget(self.radio_selected)
        root_layout.addWidget(scope_group)

        # 3. Presets & Actions
        action_group = QGroupBox("2. TÍNH NĂNG NHANH / CÂN CHỈNH TỰ ĐỘNG")
        action_layout = QVBoxLayout(action_group)
        action_layout.setSpacing(8)

        # Preset 1: Video Start
        first_sub_start = float(self.active_segments[0].get("start", 0.0)) if self.active_segments else 0.0
        delta_to_video = round(self.first_video_start - first_sub_start, 3)
        self.btn_preset_video = QPushButton(
            f"🎯 Khớp vào đầu Video chính  (Đầu video: {self.first_video_start:.2f}s | Lệch: {delta_to_video:+.2f}s)"
        )
        self.btn_preset_video.setObjectName("presetBtn")
        self.btn_preset_video.setCursor(Qt.PointingHandCursor)
        self.btn_preset_video.clicked.connect(lambda: self._apply_preset_offset(delta_to_video))
        action_layout.addWidget(self.btn_preset_video)

        # Preset 2: Playhead
        ref_start = (
            float(self.active_segments[self.selected_index].get("start", 0.0))
            if 0 <= self.selected_index < len(self.active_segments)
            else first_sub_start
        )
        delta_to_playhead = round(self.playhead_s - ref_start, 3)
        self.btn_preset_playhead = QPushButton(
            f"⏱️ Khớp vào vị trí con trỏ phát  (Con trỏ: {self.playhead_s:.2f}s | Lệch: {delta_to_playhead:+.2f}s)"
        )
        self.btn_preset_playhead.setObjectName("presetBtn")
        self.btn_preset_playhead.setCursor(Qt.PointingHandCursor)
        self.btn_preset_playhead.clicked.connect(lambda: self._apply_preset_offset(delta_to_playhead))
        action_layout.addWidget(self.btn_preset_playhead)

        # Preset 3: Auto-Fit short cues into trailing silence gaps
        self.btn_preset_autofit = QPushButton(
            "⚡ Tự động mở rộng câu ngắn vào khoảng trống (Auto-Fit Durations & Fix Fast Voice)"
        )
        self.btn_preset_autofit.setObjectName("presetBtn")
        self.btn_preset_autofit.setStyleSheet("color: #38bdf8; font-weight: 700;")
        self.btn_preset_autofit.setToolTip(
            "Tự động kéo dài thời lượng các câu phụ đề ngắn vào khoảng im lặng phía sau.\n"
            "Giúp người xem kịp đọc chữ và giúp giọng đọc TTS tự nhiên, không bị ép đọc quá nhanh."
        )
        self.btn_preset_autofit.setCursor(Qt.PointingHandCursor)
        self.btn_preset_autofit.clicked.connect(self._apply_auto_fit_cue_durations)
        action_layout.addWidget(self.btn_preset_autofit)

        root_layout.addWidget(action_group)

        # 4. Custom offset
        offset_group = QGroupBox("3. ĐIỀU CHỈNH ĐỘ DỊCH CHUYỂN THỜI GIAN (OFFSET)")
        offset_layout = QVBoxLayout(offset_group)
        offset_layout.setSpacing(8)

        spin_row = QHBoxLayout()
        spin_row.setSpacing(10)
        spin_label = QLabel("Số giây dịch chuyển (âm: lùi, dương: tiến):")
        spin_label.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.spin_offset = QDoubleSpinBox()
        self.spin_offset.setRange(-3600.0, 3600.0)
        self.spin_offset.setDecimals(3)
        self.spin_offset.setSingleStep(0.1)
        self.spin_offset.setValue(0.0)
        self.spin_offset.setSuffix(" s")
        self.spin_offset.setMinimumWidth(120)
        self.spin_offset.valueChanged.connect(self._update_preview)

        spin_row.addWidget(spin_label)
        spin_row.addWidget(self.spin_offset)
        spin_row.addStretch()
        offset_layout.addLayout(spin_row)

        # Nudge buttons
        nudge_row = QHBoxLayout()
        nudge_row.setSpacing(4)
        nudges = [
            ("-5s", -5.0),
            ("-1s", -1.0),
            ("-0.5s", -0.5),
            ("-0.1s", -0.1),
            ("0.0s", 0.0),
            ("+0.1s", 0.1),
            ("+0.5s", 0.5),
            ("+1s", 1.0),
            ("+5s", 5.0),
        ]
        for label, val in nudges:
            btn = QPushButton(label)
            btn.setObjectName("nudgeBtn")
            btn.setCursor(Qt.PointingHandCursor)
            if val == 0.0:
                btn.clicked.connect(lambda: self.spin_offset.setValue(0.0))
            else:
                btn.clicked.connect(lambda _, v=val: self.spin_offset.setValue(round(self.spin_offset.value() + v, 3)))
            nudge_row.addWidget(btn)
        nudge_row.addStretch()
        offset_layout.addLayout(nudge_row)

        root_layout.addWidget(offset_group)

        # 5. Live preview
        preview_group = QGroupBox("4. XEM TRƯỚC THAY ĐỔI (LIVE PREVIEW)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_text = QTextEdit()
        self.preview_text.setObjectName("previewBox")
        self.preview_text.setReadOnly(True)
        self.preview_text.setFixedHeight(95)
        preview_layout.addWidget(self.preview_text)
        root_layout.addWidget(preview_group)

        # 6. Checkbox to also shift voiceover/TTS and overlays
        self.chk_shift_all = QCheckBox("Đồng bộ cả lớp voiceover/TTS và các lớp phủ liên quan (Sync voiceover & overlays)")
        self.chk_shift_all.setChecked(True)
        root_layout.addWidget(self.chk_shift_all)

        # 7. Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Hủy bỏ")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply = QPushButton("✓ Áp dụng đồng bộ (Apply)")
        self.btn_apply.setObjectName("primaryBtn")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.clicked.connect(self._on_apply)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
        root_layout.addLayout(btn_layout)

    def _apply_preset_offset(self, delta: float):
        self.spin_offset.setValue(delta)

    def _apply_auto_fit_cue_durations(self):
        """Auto-extend all short cues into following silence gaps."""
        from ui.helpers.srt_helpers import expand_short_cues_into_gaps
        if not self.active_segments:
            return

        expanded = expand_short_cues_into_gaps(self.active_segments)
        changed = 0
        lines = []
        for i, (orig, exp) in enumerate(zip(self.active_segments, expanded)):
            orig_end = float(orig.get("end", 0.0))
            exp_end = float(exp.get("end", 0.0))
            if abs(exp_end - orig_end) > 0.01:
                changed += 1
                st = float(orig.get("start", 0.0))
                orig_dur = orig_end - st
                new_dur = exp_end - st
                text_snip = str(exp.get("text") or exp.get("final_text") or exp.get("dubbing_vi") or "")[:24]
                lines.append(f"#{i+1:02d}: {orig_dur:.2f}s -> {new_dur:.2f}s | {text_snip}...")

        if not changed:
            self.preview_text.setPlainText("Tất cả các câu phụ đề đều đã có thời lượng chuẩn, không cần mở rộng thêm.")
            return

        self.active_segments = expanded

        # Apply to host segments directly
        for seg_list_name in ("current_segments", "current_translated_segments"):
            segments = getattr(self.host, seg_list_name, None)
            if isinstance(segments, list):
                for i in range(min(len(segments), len(expanded))):
                    segments[i]["end"] = expanded[i]["end"]

        # Apply to host segment models if present
        if hasattr(self.host, "current_translated_segment_models") and getattr(self.host, "current_translated_segment_models"):
            models = self.host.current_translated_segment_models
            for i in range(min(len(models), len(expanded))):
                models[i].end = float(expanded[i]["end"])

        if hasattr(self.host, "apply_segments_to_timeline"):
            self.host.apply_segments_to_timeline()
        if hasattr(self.host, "refresh_ui_state"):
            self.host.refresh_ui_state()

        self.preview_text.setPlainText(
            f"✓ Đã tự động mở rộng thành công {changed} câu phụ đề ngắn vào khoảng trống im lặng:\n"
            + "\n".join(lines[:6])
            + (f"\n... và {changed - 6} câu khác." if changed > 6 else "")
        )


    def _update_preview(self):
        delta = round(self.spin_offset.value(), 3)
        if not self.active_segments:
            self.preview_text.setPlainText("Không có phụ đề nào trên timeline.")
            return

        lines = []
        is_all = self.radio_all.isChecked()
        is_ripple = self.radio_ripple.isChecked()
        is_single = self.radio_selected.isChecked()

        start_idx = 0
        end_idx = len(self.active_segments)
        if is_single and 0 <= self.selected_index < len(self.active_segments):
            start_idx = self.selected_index
            end_idx = self.selected_index + 1
        elif is_ripple and 0 <= self.selected_index < len(self.active_segments):
            start_idx = self.selected_index

        preview_count = 0
        for i in range(start_idx, end_idx):
            if preview_count >= 5:
                remaining = (end_idx - start_idx) - preview_count
                if remaining > 0:
                    lines.append(f"... và {remaining} câu phụ đề khác.")
                break
            seg = self.active_segments[i]
            st = float(seg.get("start", 0.0))
            en = float(seg.get("end", st + 0.1))
            new_st = max(0.0, round(st + delta, 3))
            new_en = max(new_st + 0.05, round(en + delta, 3))
            text_snip = str(seg.get("text") or seg.get("translated") or seg.get("original") or "")[:25]
            lines.append(
                f"#{i+1:02d}: [{format_timestamp(st)} -> {format_timestamp(en)}]  ==>  "
                f"[{format_timestamp(new_st)} -> {format_timestamp(new_en)}]  | {text_snip}..."
            )
            preview_count += 1

        self.preview_text.setPlainText("\n".join(lines))

    def _on_apply(self):
        delta = round(self.spin_offset.value(), 3)
        if abs(delta) < 0.0001:
            self.accept()
            return

        is_all = self.radio_all.isChecked()
        is_ripple = self.radio_ripple.isChecked()
        is_single = self.radio_selected.isChecked()
        shift_all_tracks = self.chk_shift_all.isChecked()

        if is_all:
            # Shift all cues
            if shift_all_tracks and hasattr(self.host, "shift_timeline_timed_elements"):
                self.host.shift_timeline_timed_elements(delta, after_time=0.0)
            else:
                self._shift_segments_direct(0, delta)
        elif is_ripple:
            # Shift from selected cue onwards
            if 0 <= self.selected_index < len(self.active_segments):
                cue_start = float(self.active_segments[self.selected_index].get("start", 0.0))
                if shift_all_tracks and hasattr(self.host, "shift_timeline_timed_elements"):
                    self.host.shift_timeline_timed_elements(delta, after_time=cue_start)
                elif hasattr(self.host, "ripple_nudge_selected_timeline_segment"):
                    self.host.ripple_nudge_selected_timeline_segment(delta)
                else:
                    self._shift_segments_direct(self.selected_index, delta)
        elif is_single:
            # Only shift single cue
            if 0 <= self.selected_index < len(self.active_segments):
                seg = self.active_segments[self.selected_index]
                st = float(seg.get("start", 0.0))
                en = float(seg.get("end", st + 0.1))
                new_st = max(0.0, round(st + delta, 3))
                new_en = max(new_st + 0.05, round(en + delta, 3))
                if hasattr(self.host, "on_timeline_segment_timing_changed"):
                    self.host.on_timeline_segment_timing_changed(self.selected_index, new_st, new_en)
                else:
                    seg["start"] = new_st
                    seg["end"] = new_en

        self.accept()

    def _shift_segments_direct(self, from_index: int, delta: float):
        for seg_list_name in ("current_segments", "current_translated_segments"):
            segments = getattr(self.host, seg_list_name, None)
            if isinstance(segments, list):
                for i in range(from_index, len(segments)):
                    seg = segments[i]
                    if isinstance(seg, dict):
                        st = float(seg.get("start", 0.0))
                        en = float(seg.get("end", st + 0.1))
                        dur = max(0.05, en - st)
                        new_st = max(0.0, round(st + delta, 3))
                        seg["start"] = new_st
                        seg["end"] = round(new_st + dur, 3)

        if hasattr(self.host, "apply_segments_to_timeline"):
            self.host.apply_segments_to_timeline()
        if hasattr(self.host, "refresh_ui_state"):
            self.host.refresh_ui_state()
