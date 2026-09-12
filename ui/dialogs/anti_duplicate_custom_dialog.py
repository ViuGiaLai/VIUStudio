from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.anti_duplicate import AntiDuplicateSettings


class StylePreviewDialog(QDialog):
    """Cửa sổ hiển thị ảnh so sánh trực quan 4 phong cách bố cục làm mới video."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("👁️ Bảng So Sánh Trực Quan 4 Phong Cách Bố Cục Video")
        self.resize(1020, 690)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1329;
                color: #f8fafc;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #e2e8f0;
            }
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        hdr = QLabel(
            "<b>So sánh thực tế:</b> Video gốc và 4 phong cách bố cục làm mới (≥40% biến đổi thị giác để bẻ gãy Content ID).<br>"
            "<span style='color: #38bdf8;'>• Phong cách 1 (Univisium 2.05:1): Viền chỉ 6.6% (72px) - an toàn tuyệt đối cho trán nhân vật &amp; phụ đề.</span><br>"
            "<span style='color: #94a3b8;'>• Phong cách 2 (Ambient 92%) | Phong cách 3 (Ken Burns Lia máy) | Phong cách 4 (Vệt sáng &amp; Hạt bụi).</span>"
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        lbl_img = QLabel()
        lbl_img.setAlignment(Qt.AlignCenter)
        lbl_img.setStyleSheet("border: 1px solid #1e293b; border-radius: 8px; background-color: #020617; padding: 4px;")

        img_path = Path(__file__).resolve().parent.parent.parent / "assets" / "anti_duplicate_styles_comparison.jpg"
        if not img_path.exists():
            fallback = Path(r"C:\Users\works\.gemini\antigravity\brain\7abbd13d-8372-45f2-9f71-88e4d112c758\proof_4_styles_final_comparison.jpg")
            if fallback.exists():
                img_path = fallback

        if img_path.exists():
            pix = QPixmap(str(img_path))
            if not pix.isNull():
                lbl_img.setPixmap(pix.scaled(980, 560, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl_img.setText("Không thể đọc tệp ảnh minh họa.")
        else:
            lbl_img.setText("Không tìm thấy tệp ảnh minh họa.")

        layout.addWidget(lbl_img, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch(1)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)


class AntiDuplicateCustomDialog(QDialog):
    """Dialog tuy chinh tung ky thuat Auto Recap / Chong trung lap (Anti-Duplicate)."""

    settings_saved = Signal(object)

    def __init__(self, settings: AntiDuplicateSettings | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings or AntiDuplicateSettings(enabled=True, continuous_mode=True, allow_horizontal_flip=True)
        self.setWindowTitle("⚙️ Tùy chỉnh Kỹ thuật Chống trùng lặp (Auto Recap)")
        self.setMinimumWidth(560)
        self.setMinimumHeight(640)
        self.resize(580, 680)
        self._setup_style()
        self._init_ui()

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: 700;
                color: #94a3b8;
                font-size: 13px;
                background-color: #1e293b;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #38bdf8;
            }
            QCheckBox, QRadioButton {
                color: #e2e8f0;
                font-size: 13px;
                spacing: 8px;
                padding: 3px 0;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #0f172a;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid #475569;
                background-color: #0f172a;
            }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background-color: #2563eb;
                border-color: #38bdf8;
            }
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 18px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton#secondaryBtn {
                background-color: #334155;
                color: #cbd5e1;
            }
            QPushButton#secondaryBtn:hover {
                background-color: #475569;
            }
            QLabel#hintLabel {
                color: #64748b;
                font-size: 11px;
                margin-left: 26px;
                margin-bottom: 4px;
            }
        """)

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setSpacing(10)
        root_layout.setContentsMargins(18, 16, 18, 16)

        # Header Title
        title_label = QLabel("🛡️ Tùy chỉnh Kỹ thuật Chống trùng lặp (Auto Recap)")
        title_label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        title_label.setStyleSheet("color: #38bdf8;")
        root_layout.addWidget(title_label)

        sub_label = QLabel("Bật/tắt từng kỹ thuật để phù hợp với nội dung video của bạn. (Mặc định: Tất cả bật)")
        sub_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        root_layout.addWidget(sub_label)

        # Scroll Area for techniques
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        c_layout = QVBoxLayout(container)
        c_layout.setSpacing(12)
        c_layout.setContentsMargins(0, 0, 8, 0)

        # ---------------- Section 1: Video Transforms ----------------
        video_group = QGroupBox("🎬 HÌNH ẢNH / VIDEO (Video Fingerprint)")
        vg_layout = QVBoxLayout(video_group)
        vg_layout.setSpacing(6)

        # 1.0 Chế độ lật gương (Cách 2: 4p xuôi / 1p lật)
        flip_box = QFrame()
        flip_box.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 6px;")
        fb_layout = QVBoxLayout(flip_box)
        fb_layout.setSpacing(5)
        fb_layout.setContentsMargins(10, 8, 10, 8)

        lbl_flip_title = QLabel("🪞 Chế độ Phản chiếu (Lật gương)")
        lbl_flip_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        fb_layout.addWidget(lbl_flip_title)

        self.flip_group = QButtonGroup(self)
        self.radio_flip_periodic = QRadioButton("✨ Xen kẽ thông minh: 80% xuôi / 20% lật (Tự thích ứng thời lượng)")
        self.radio_flip_periodic.setToolTip("Tự động nhận diện thời lượng: Video ngắn xen kẽ mỗi 48s/12s, video dài xen kẽ 4p/1p. Đảm bảo 80% thời lượng xem xuôi bình thường.")
        self.radio_flip_always = QRadioButton("🔁 Lật toàn bộ video (100% thời lượng)")
        self.radio_flip_none = QRadioButton("⏹️ Tắt lật gương (Giữ 100% video xuôi - thích hợp khi có chữ/đồng hồ)")

        self.flip_group.addButton(self.radio_flip_periodic, 0)
        self.flip_group.addButton(self.radio_flip_always, 1)
        self.flip_group.addButton(self.radio_flip_none, 2)

        cur_mode = getattr(self.settings, "flip_mode", "periodic")
        allow_flip = getattr(self.settings, "allow_horizontal_flip", True)
        if not allow_flip or cur_mode == "none":
            self.radio_flip_none.setChecked(True)
        elif cur_mode == "always":
            self.radio_flip_always.setChecked(True)
        else:
            self.radio_flip_periodic.setChecked(True)

        fb_layout.addWidget(self.radio_flip_periodic)
        fb_layout.addWidget(self.radio_flip_always)
        fb_layout.addWidget(self.radio_flip_none)
        vg_layout.addWidget(flip_box)

        self.zoom_box = QFrame()
        self.zoom_box.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 6px;")
        zb_layout = QVBoxLayout(self.zoom_box)
        zb_layout.setSpacing(5)
        zb_layout.setContentsMargins(10, 8, 10, 8)

        self.zoom_cb = QCheckBox("🔍 Thu phóng vi mô (Zoom 105% chuẩn điện ảnh)")
        self.zoom_cb.setChecked(getattr(self.settings, "add_zoom", True))
        zb_layout.addWidget(self.zoom_cb)

        self.punch_zoom_cb = QCheckBox("⚡ Punch Zoom nhịp điệu 5.5s (Đổi góc cận/toàn · Bẻ chuỗi 7s quét YouTube)")
        self.punch_zoom_cb.setChecked(getattr(self.settings, "add_punch_zoom", True))
        self.punch_zoom_cb.setToolTip(
            "Cứ mỗi 5.5s tự động đổi giữa góc toàn cảnh (105%) và cận cảnh (110% lệch tâm):\n"
            "• Bẻ gãy chuỗi nhận diện liên tục 7s của YouTube Content ID\n"
            "• Bảo toàn 100.00% thời lượng video (0.000s drift) -> Giữ phụ đề & giọng đọc TTS khớp chuẩn 100%\n"
            "• Tốc độ xuất video siêu nhanh với flags=fast_bilinear."
        )
        zb_layout.addWidget(self.punch_zoom_cb)
        lbl_zoom = QLabel("Đổi góc máy nhịp điệu 5.5s giả lập 2 camera Studio, bẻ gãy Content ID mà không lệch phụ đề.", objectName="hintLabel")
        zb_layout.addWidget(lbl_zoom)

        def _update_zoom_ui(checked):
            self.punch_zoom_cb.setEnabled(checked)

        self.zoom_cb.toggled.connect(_update_zoom_ui)
        _update_zoom_ui(self.zoom_cb.isChecked())

        vg_layout.addWidget(self.zoom_box)

        # 1.2 Chế độ màu sắc (Đề xuất 1: Xoay vòng 4 Tone màu điện ảnh mỗi 4 phút)
        color_box = QFrame()
        color_box.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 6px;")
        cb_layout = QVBoxLayout(color_box)
        cb_layout.setSpacing(5)
        cb_layout.setContentsMargins(10, 8, 10, 8)

        lbl_color_title = QLabel("🎨 Chế độ Màu sắc (Cinematic Color Shift)")
        lbl_color_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        cb_layout.addWidget(lbl_color_title)

        self.color_group = QButtonGroup(self)
        self.radio_color_periodic = QRadioButton("✨ Xoay vòng 4 Tone màu điện ảnh mỗi 4 phút (Đề xuất 1 - Khuyên dùng)")
        self.radio_color_periodic.setToolTip("Ấm điện ảnh (0-4m) -> Lạnh hiện đại (4-8m) -> Đậm đà tương phản (8-12m) -> Cổ điển dịu mắt (12-16m). Phá vỡ triệt để biểu đồ màu Content ID.")
        self.radio_color_random = QRadioButton("🎲 Vi chỉnh một màu ngẫu nhiên cố định (Cả video)")
        self.radio_color_random.setToolTip("Áp dụng một vi chỉnh màu ngẫu nhiên duy nhất cho toàn bộ video.")
        self.radio_color_none = QRadioButton("⏹️ Giữ nguyên màu gốc (Không đổi màu)")

        self.color_group.addButton(self.radio_color_periodic, 0)
        self.color_group.addButton(self.radio_color_random, 1)
        self.color_group.addButton(self.radio_color_none, 2)

        cur_color_mode = getattr(self.settings, "color_grading_mode", "periodic")
        allow_color = getattr(self.settings, "random_color_grade", True)
        if not allow_color or cur_color_mode == "none":
            self.radio_color_none.setChecked(True)
        elif cur_color_mode == "random":
            self.radio_color_random.setChecked(True)
        else:
            self.radio_color_periodic.setChecked(True)

        cb_layout.addWidget(self.radio_color_periodic)
        cb_layout.addWidget(self.radio_color_random)
        cb_layout.addWidget(self.radio_color_none)
        vg_layout.addWidget(color_box)

        # 1.3 Bố cục Làm mới Khung hình (Visual Refresh Layout >= 40%)
        layout_box = QFrame()
        layout_box.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 6px;")
        lb_layout = QVBoxLayout(layout_box)
        lb_layout.setSpacing(6)
        lb_layout.setContentsMargins(10, 8, 10, 8)

        lb_hdr = QHBoxLayout()
        lbl_layout_title = QLabel("📐 Bố cục Làm mới Khung hình (Visual Refresh ≥ 40%)")
        lbl_layout_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        lb_hdr.addWidget(lbl_layout_title)
        lb_hdr.addStretch(1)

        self.btn_preview_styles = QPushButton("👁️ Xem ảnh so sánh 4 phong cách...")
        self.btn_preview_styles.setStyleSheet("""
            QPushButton {
                background-color: #0369a1;
                color: #e0f2fe;
                border: 1px solid #0284c7;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_preview_styles.setToolTip("Mở bảng so sánh ảnh thực tế giữa video gốc và 4 phong cách làm mới")
        self.btn_preview_styles.clicked.connect(self._show_style_preview)
        lb_hdr.addWidget(self.btn_preview_styles)
        lb_layout.addLayout(lb_hdr)

        self.layout_group = QButtonGroup(self)
        self.radio_layout_letterbox = QRadioButton("🎬 Chuẩn Điện ảnh 2.05:1 (Mờ nhẹ 6.6% mép viền · Bỏ viền cứng - Khuyên dùng)")
        self.radio_layout_letterbox.setToolTip("Dải mờ sương nhẹ nhàng (Soft Translucent Mist) chuyển tiếp mềm mại ở 2 mép, bỏ hoàn toàn đường viền cứng, an toàn 100% cho trán & phụ đề, tự nhiên và sang trọng.")

        self.radio_layout_ambient = QRadioButton("🪟 Bo góc Nổi khối + Viền Ambient 92% (Phong cách Recap hiện đại)")
        self.radio_layout_ambient.setToolTip("Thu nhỏ 92% đặt trên nền đệm Slate sâu thẳm #0f172a với viền neon Cyan 2px, tạo cảm giác video nổi 3D sống động.")

        self.radio_layout_kenburns = QRadioButton("🎥 Cú Lia Máy Giả lập (Ken Burns Dynamic Pan trôi chậm 0.3px/s)")
        self.radio_layout_kenburns.setToolTip("Zoom nhẹ 104% và lia máy chậm theo chu kỳ hình sin 60s, biến 100% tọa độ mọi khung hình liên tục trôi nhẹ, chống nhận diện pixel.")

        self.radio_layout_lightleak = QRadioButton("✨ Vệt Sáng Quang Học & Hạt Bụi Điện ảnh (Light Leak Flare)")
        self.radio_layout_lightleak.setToolTip("Tạo vệt lóa sáng quang học mềm mại chuyển động ở góc khung hình mang lại cảm giác thước phim rạp chất lượng cao.")

        self.radio_layout_none = QRadioButton("⏹️ Giữ nguyên khung hình 16:9 gốc (Không đổi bố cục)")
        self.radio_layout_none.setToolTip("Giữ nguyên 100% khung hình và tỷ lệ 16:9 gốc.")

        self.layout_group.addButton(self.radio_layout_letterbox, 0)
        self.layout_group.addButton(self.radio_layout_ambient, 1)
        self.layout_group.addButton(self.radio_layout_kenburns, 2)
        self.layout_group.addButton(self.radio_layout_lightleak, 3)
        self.layout_group.addButton(self.radio_layout_none, 4)

        cur_layout_mode = getattr(self.settings, "visual_layout_mode", "letterbox")
        if cur_layout_mode == "none":
            self.radio_layout_none.setChecked(True)
        elif cur_layout_mode == "ambient_frame":
            self.radio_layout_ambient.setChecked(True)
        elif cur_layout_mode == "ken_burns":
            self.radio_layout_kenburns.setChecked(True)
        elif cur_layout_mode == "light_leak":
            self.radio_layout_lightleak.setChecked(True)
        else:
            self.radio_layout_letterbox.setChecked(True)

        lb_layout.addWidget(self.radio_layout_letterbox)
        lb_layout.addWidget(self.radio_layout_ambient)
        lb_layout.addWidget(self.radio_layout_kenburns)
        lb_layout.addWidget(self.radio_layout_lightleak)
        lb_layout.addWidget(self.radio_layout_none)

        # 1.3b Tùy chọn Chạy chữ thương hiệu trên dải viền mờ (Marquee Text Banner)
        marquee_box = QFrame()
        marquee_box.setStyleSheet("background-color: #0b1322; border: 1px solid #1e2d44; border-radius: 6px;")
        mb_layout = QVBoxLayout(marquee_box)
        mb_layout.setSpacing(6)
        mb_layout.setContentsMargins(10, 8, 10, 8)

        self.marquee_cb = QCheckBox("📜 Chạy chữ thương hiệu trên dải viền mờ (Marquee Text Ticker)")
        self.marquee_cb.setChecked(getattr(self.settings, "marquee_enabled", True))
        self.marquee_cb.setToolTip("Hiển thị dòng chữ chuyển động cuộn liên tục trên dải mờ mép trên, bẻ gãy mạnh mẽ thuật toán Content ID.")
        mb_layout.addWidget(self.marquee_cb)

        # Row 1: Text content
        row_text = QHBoxLayout()
        row_text.setSpacing(8)
        lbl_txt = QLabel("Nội dung:")
        lbl_txt.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        self.marquee_text_edit = QLineEdit()
        self.marquee_text_edit.setText(getattr(self.settings, "marquee_text", "VIURECAP"))
        self.marquee_text_edit.setPlaceholderText("VIURECAP")
        self.marquee_text_edit.setStyleSheet("""
            QLineEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QLineEdit:focus {
                border-color: #38bdf8;
            }
            QLineEdit:disabled {
                background-color: #0b111c;
                color: #475569;
                border-color: #1e293b;
            }
        """)
        row_text.addWidget(lbl_txt)
        row_text.addWidget(self.marquee_text_edit, 1)
        mb_layout.addLayout(row_text)

        # Row 2: Direction & Speed controls
        row_options = QHBoxLayout()
        row_options.setSpacing(8)

        lbl_dir = QLabel("Hướng:")
        lbl_dir.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        row_options.addWidget(lbl_dir)

        self.dir_group = QButtonGroup(self)
        self.radio_dir_rtl = QRadioButton("Phải ➔ Trái")
        self.radio_dir_rtl.setToolTip("Chữ chạy từ mép phải sang mép trái (chuẩn truyền hình & recap)")
        self.radio_dir_ltr = QRadioButton("Trái ➔ Phải")
        self.radio_dir_ltr.setToolTip("Chữ chạy từ mép trái sang mép phải")

        self.dir_group.addButton(self.radio_dir_rtl, 0)
        self.dir_group.addButton(self.radio_dir_ltr, 1)

        cur_dir = getattr(self.settings, "marquee_direction", "right_to_left")
        if cur_dir == "left_to_right":
            self.radio_dir_ltr.setChecked(True)
        else:
            self.radio_dir_rtl.setChecked(True)

        row_options.addWidget(self.radio_dir_rtl)
        row_options.addWidget(self.radio_dir_ltr)

        row_options.addSpacing(10)

        lbl_spd = QLabel("Tốc độ:")
        lbl_spd.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        row_options.addWidget(lbl_spd)

        self.marquee_speed_combo = QComboBox()
        self.marquee_speed_combo.setStyleSheet("""
            QComboBox {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                min-width: 130px;
            }
            QComboBox:focus {
                border-color: #38bdf8;
            }
            QComboBox:disabled {
                background-color: #0b111c;
                color: #475569;
                border-color: #1e293b;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #0284c7;
            }
        """)
        self.marquee_speed_combo.addItem("🐢 Rất chậm (45 px/s)", 45)
        self.marquee_speed_combo.addItem("✨ Chậm êm dịu (70 px/s)", 70)
        self.marquee_speed_combo.addItem("🚶 Vừa phải (110 px/s)", 110)
        self.marquee_speed_combo.addItem("⚡ Nhanh (160 px/s)", 160)

        cur_spd = getattr(self.settings, "marquee_speed", 70)
        idx = self.marquee_speed_combo.findData(cur_spd)
        if idx >= 0:
            self.marquee_speed_combo.setCurrentIndex(idx)
        else:
            if cur_spd <= 55:
                self.marquee_speed_combo.setCurrentIndex(0)
            elif cur_spd <= 85:
                self.marquee_speed_combo.setCurrentIndex(1)
            elif cur_spd <= 135:
                self.marquee_speed_combo.setCurrentIndex(2)
            else:
                self.marquee_speed_combo.setCurrentIndex(3)

        row_options.addWidget(self.marquee_speed_combo)
        row_options.addStretch(1)
        mb_layout.addLayout(row_options)

        def _update_marquee_fields(checked):
            self.marquee_text_edit.setEnabled(checked)
            self.radio_dir_rtl.setEnabled(checked)
            self.radio_dir_ltr.setEnabled(checked)
            self.marquee_speed_combo.setEnabled(checked)

        self.marquee_cb.toggled.connect(_update_marquee_fields)
        _update_marquee_fields(self.marquee_cb.isChecked())

        lb_layout.addWidget(marquee_box)
        vg_layout.addWidget(layout_box)

        self.vignette_cb = QCheckBox("📐 Biến dạng hình học (Crop viền 3.5% + Vignette viền mờ)")
        self.vignette_cb.setChecked(getattr(self.settings, "geometric_mode", "both") not in ("none", "", None))
        vg_layout.addWidget(self.vignette_cb)
        lbl_geo = QLabel("Làm mờ 4 góc cực nhẹ (PI/8) và dịch khung hình.", objectName="hintLabel")
        vg_layout.addWidget(lbl_geo)

        self.grain_cb = QCheckBox("🎞️ Phủ hạt phim điện ảnh vi mô (Grain Noise 3%)")
        self.grain_cb.setChecked(getattr(self.settings, "add_grain_noise", True))
        vg_layout.addWidget(self.grain_cb)
        lbl_grain = QLabel("Phá vỡ perceptual hash DCT của thuật toán quét YouTube/TikTok.", objectName="hintLabel")
        vg_layout.addWidget(lbl_grain)

        self.unsharp_cb = QCheckBox("🔪 Tăng độ nét cạnh viền nhẹ (Unsharp filter)")
        self.unsharp_cb.setChecked(getattr(self.settings, "add_unsharp", True))
        vg_layout.addWidget(self.unsharp_cb)
        lbl_unsharp = QLabel("Tăng vi độ nét cho các cạnh vật thể, video nhìn rõ hơn.", objectName="hintLabel")
        vg_layout.addWidget(lbl_unsharp)

        self.speed_cb = QCheckBox("⏱️ Vi tốc độ hình ảnh (+0.01% Micro Speed)")
        self.speed_cb.setChecked(getattr(self.settings, "add_micro_speed", True))
        vg_layout.addWidget(self.speed_cb)
        lbl_speed = QLabel("Dịch nhịp cắt cảnh vi mô, không làm thay đổi thời lượng cảm nhận.", objectName="hintLabel")
        vg_layout.addWidget(lbl_speed)

        c_layout.addWidget(video_group)

        # ---------------- Section 2: Audio Fingerprint ----------------
        audio_group = QGroupBox("🎵 ÂM THANH GỐC (Chỉ áp dụng âm thanh gốc, không đổi giọng TTS)")
        ag_layout = QVBoxLayout(audio_group)
        ag_layout.setSpacing(4)

        self.pitch_cb = QCheckBox("🎼 Dịch cao độ vi mô (+1.5% Pitch Shift)")
        self.pitch_cb.setChecked(getattr(self.settings, "add_pitch_shift", True))
        ag_layout.addWidget(self.pitch_cb)
        lbl_pitch = QLabel("Phá nhận diện tần số giọng gốc mà người nghe không cảm nhận được méo.", objectName="hintLabel")
        ag_layout.addWidget(lbl_pitch)

        self.eq_cb = QCheckBox("🎚️ Lệch dải tần EQ (Phá Chromaprint / Shazam)")
        self.eq_cb.setChecked(getattr(self.settings, "add_eq_audio", True))
        ag_layout.addWidget(self.eq_cb)
        lbl_eq = QLabel("Tăng nhẹ 1200Hz và hạ nhẹ 5500Hz để thay đổi spectrogram âm thanh gốc.", objectName="hintLabel")
        ag_layout.addWidget(lbl_eq)

        self.vol_cb = QCheckBox("🔉 Vi chỉnh mức âm lượng (-0.3 dB)")
        self.vol_cb.setChecked(getattr(self.settings, "add_volume_level", True))
        ag_layout.addWidget(self.vol_cb)
        lbl_vol = QLabel("Hạ mức PCM 3% để sai lệch với fingerprint mức đỉnh của bot.", objectName="hintLabel")
        ag_layout.addWidget(lbl_vol)

        self.music_camouflage_cb = QCheckBox("🎵 Ngụy trang nhạc nền (KT#13 · Micro Echo 9ms + Tần số +3Hz)")
        self.music_camouflage_cb.setChecked(getattr(self.settings, "add_music_camouflage", False))
        self.music_camouflage_cb.setToolTip(
            "Thêm vi echo 9ms + dịch tần số +3Hz vào nhạc nền:\n"
            "• Phá fingerprint ACRCloud / YouTube Content ID cho nhạc nền\n"
            "• Người nghe KHÔNG phân biệt được (ngưỡng cảm nhận: echo >20ms, pitch >0.5 cent)\n"
            "• FFmpeg native: tốc độ xuất gần như không ảnh hưởng (~0.5% CPU thêm)\n"
            "⚠️ Chỉ bật khi video có nhạc nền gốc có bản quyền cần đăng lên YouTube."
        )
        ag_layout.addWidget(self.music_camouflage_cb)
        lbl_mc = QLabel(
            "Phá nhận diện ACRCloud/Shazam theo time-domain (echo) & frequency-domain (freqshift). Không ảnh hưởng giọng đọc.",
            objectName="hintLabel"
        )
        ag_layout.addWidget(lbl_mc)

        # KT#14: Lồng nhạc nền đệm nhẹ (BGM Collision 10-15%)
        bgm_box = QFrame()
        bgm_box.setStyleSheet("background-color: #0b1322; border: 1px solid #1e2d44; border-radius: 6px;")
        bgm_layout = QVBoxLayout(bgm_box)
        bgm_layout.setSpacing(6)
        bgm_layout.setContentsMargins(10, 8, 10, 8)

        self.bgm_overlay_cb = QCheckBox("🎵 Lồng nhạc nền đệm nhẹ kháng bản quyền (BGM Collision 10-15%)")
        self.bgm_overlay_cb.setChecked(getattr(self.settings, "add_bgm_overlay", True))
        self.bgm_overlay_cb.setToolTip(
            "Đòn bẩy kháng bản quyền YouTube mạnh nhất:\n"
            "• Trộn thêm 1 track BGM nhẹ (10% - 15%) vào âm thanh gốc bằng FFmpeg native amix.\n"
            "• Gây xung đột đa nguồn (Multi-track collision) khiến AI Content ID không thể tách khớp nhạc gốc.\n"
            "• Tốc độ xuất SIÊU NHANH (không tốn thêm thời gian xuất)."
        )
        bgm_layout.addWidget(self.bgm_overlay_cb)

        # Controls row
        row_bgm_ctrl = QHBoxLayout()
        row_bgm_ctrl.setSpacing(8)

        lbl_bgm_vol = QLabel("Âm lượng BGM:")
        lbl_bgm_vol.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: 600;")
        row_bgm_ctrl.addWidget(lbl_bgm_vol)

        self.bgm_vol_combo = QComboBox()
        self.bgm_vol_combo.setStyleSheet("""
            QComboBox {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
                min-width: 140px;
            }
            QComboBox:focus {
                border-color: #38bdf8;
            }
            QComboBox:disabled {
                background-color: #0b111c;
                color: #475569;
                border-color: #1e293b;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #0284c7;
            }
        """)
        self.bgm_vol_combo.addItem("🍃 Rất nhẹ (8%)", 0.08)
        self.bgm_vol_combo.addItem("✨ Chuẩn khuyến nghị (12%)", 0.12)
        self.bgm_vol_combo.addItem("🔊 Vừa phải (15%)", 0.15)
        self.bgm_vol_combo.addItem("📢 Nổi bật (20%)", 0.20)

        cur_vol = float(getattr(self.settings, "bgm_volume", 0.12) or 0.12)
        if cur_vol <= 0.09:
            self.bgm_vol_combo.setCurrentIndex(0)
        elif cur_vol <= 0.13:
            self.bgm_vol_combo.setCurrentIndex(1)
        elif cur_vol <= 0.17:
            self.bgm_vol_combo.setCurrentIndex(2)
        else:
            self.bgm_vol_combo.setCurrentIndex(3)

        row_bgm_ctrl.addWidget(self.bgm_vol_combo)

        self.btn_pick_bgm = QPushButton("📁 Chọn bài khác...")
        self.btn_pick_bgm.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284c7;
                color: #ffffff;
            }
        """)
        self.btn_pick_bgm.clicked.connect(self._pick_custom_bgm)
        row_bgm_ctrl.addWidget(self.btn_pick_bgm)

        self.btn_reset_bgm = QPushButton("🔄 Mặc định")
        self.btn_reset_bgm.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                color: #94a3b8;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #334155;
                color: #f8fafc;
            }
        """)
        self.btn_reset_bgm.clicked.connect(self._reset_bgm_path)
        row_bgm_ctrl.addWidget(self.btn_reset_bgm)

        row_bgm_ctrl.addStretch(1)
        bgm_layout.addLayout(row_bgm_ctrl)

        self.lbl_bgm_current = QLabel(self._format_bgm_label())
        self.lbl_bgm_current.setStyleSheet("color: #64748b; font-size: 11px; margin-left: 4px;")
        bgm_layout.addWidget(self.lbl_bgm_current)

        def _update_bgm_ui(checked):
            self.bgm_vol_combo.setEnabled(checked)
            self.btn_pick_bgm.setEnabled(checked)
            self.btn_reset_bgm.setEnabled(checked)
            self.lbl_bgm_current.setEnabled(checked)

        self.bgm_overlay_cb.toggled.connect(_update_bgm_ui)
        _update_bgm_ui(self.bgm_overlay_cb.isChecked())

        ag_layout.addWidget(bgm_box)

        c_layout.addWidget(audio_group)

        # ---------------- Section 3: Metadata ----------------
        meta_group = QGroupBox("📁 FILE & THÔNG TIN (Metadata)")
        mg_layout = QVBoxLayout(meta_group)
        mg_layout.setSpacing(4)

        self.meta_cb = QCheckBox("🧹 Xóa sạch và tạo mới Metadata file xuất (Poison Metadata)")
        self.meta_cb.setChecked(getattr(self.settings, "poison_metadata", True))
        mg_layout.addWidget(self.meta_cb)
        lbl_meta = QLabel("Xóa ID máy quay, tác giả, phần mềm gốc, gắn encoder VIUStudio mới.", objectName="hintLabel")
        mg_layout.addWidget(lbl_meta)

        c_layout.addWidget(meta_group)

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.reset_btn = QPushButton("🔄 Khôi phục mặc định")
        self.reset_btn.setObjectName("secondaryBtn")
        self.reset_btn.setToolTip("Bật lại toàn bộ kỹ thuật tối ưu kháng bản quyền")
        self.reset_btn.clicked.connect(self._reset_defaults)
        btn_row.addWidget(self.reset_btn)

        btn_row.addStretch(1)

        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.setObjectName("secondaryBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("💾 Lưu & Áp dụng")
        self.save_btn.clicked.connect(self._save_and_close)
        btn_row.addWidget(self.save_btn)

        root_layout.addLayout(btn_row)

    def _format_bgm_label(self) -> str:
        custom_p = getattr(self.settings, "bgm_file_path", "")
        if custom_p and os.path.isfile(custom_p):
            return f"🎵 Tệp: {os.path.basename(custom_p)}"
        return "🎵 Nhạc mặc định: Nhạc nền Recap bản quyền tự do (AudioBay)"

    def _pick_custom_bgm(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp nhạc nền BGM",
            "",
            "Audio Files (*.mp3 *.wav *.aac *.m4a *.flac *.ogg)",
        )
        if file_path:
            self.settings.bgm_file_path = file_path
            self.lbl_bgm_current.setText(self._format_bgm_label())

    def _reset_bgm_path(self):
        self.settings.bgm_file_path = ""
        self.lbl_bgm_current.setText(self._format_bgm_label())

    def _show_style_preview(self):
        """Hiển thị cửa sổ phóng to ảnh minh chứng 4 phong cách làm mới video."""
        dialog = StylePreviewDialog(self)
        dialog.exec()

    def _reset_defaults(self):
        self.radio_flip_periodic.setChecked(True)
        self.radio_color_periodic.setChecked(True)
        self.radio_layout_letterbox.setChecked(True)
        self.zoom_cb.setChecked(True)
        self.punch_zoom_cb.setChecked(True)
        self.vignette_cb.setChecked(True)
        self.grain_cb.setChecked(True)
        self.unsharp_cb.setChecked(True)
        self.speed_cb.setChecked(True)
        self.pitch_cb.setChecked(True)
        self.eq_cb.setChecked(True)
        self.vol_cb.setChecked(True)
        self.music_camouflage_cb.setChecked(False)  # mặc định tắt
        self.bgm_overlay_cb.setChecked(True)        # mặc định bật lồng BGM
        idx_bgm = self.bgm_vol_combo.findData(0.12)
        if idx_bgm >= 0:
            self.bgm_vol_combo.setCurrentIndex(idx_bgm)
        self.settings.bgm_file_path = ""
        self.lbl_bgm_current.setText(self._format_bgm_label())
        self.meta_cb.setChecked(True)
        self.marquee_cb.setChecked(True)
        self.marquee_text_edit.setText("VIURECAP")
        self.radio_dir_rtl.setChecked(True)
        idx_def = self.marquee_speed_combo.findData(70)
        if idx_def >= 0:
            self.marquee_speed_combo.setCurrentIndex(idx_def)

    def _save_and_close(self):
        self.settings.enabled = True
        self.settings.continuous_mode = True
        if self.radio_flip_none.isChecked():
            self.settings.allow_horizontal_flip = False
            self.settings.flip_mode = "none"
        elif self.radio_flip_always.isChecked():
            self.settings.allow_horizontal_flip = True
            self.settings.flip_mode = "always"
        else:
            self.settings.allow_horizontal_flip = True
            self.settings.flip_mode = "periodic"

        if self.radio_color_none.isChecked():
            self.settings.random_color_grade = False
            self.settings.color_grading_mode = "none"
        elif self.radio_color_random.isChecked():
            self.settings.random_color_grade = True
            self.settings.color_grading_mode = "random"
        else:
            self.settings.random_color_grade = True
            self.settings.color_grading_mode = "periodic"

        if self.radio_layout_none.isChecked():
            self.settings.visual_layout_mode = "none"
        elif self.radio_layout_ambient.isChecked():
            self.settings.visual_layout_mode = "ambient_frame"
        elif self.radio_layout_kenburns.isChecked():
            self.settings.visual_layout_mode = "ken_burns"
        elif self.radio_layout_lightleak.isChecked():
            self.settings.visual_layout_mode = "light_leak"
        else:
            self.settings.visual_layout_mode = "letterbox"

        self.settings.add_zoom = self.zoom_cb.isChecked()
        self.settings.add_punch_zoom = self.punch_zoom_cb.isChecked()
        self.settings.geometric_mode = "both" if self.vignette_cb.isChecked() else "none"
        self.settings.add_grain_noise = self.grain_cb.isChecked()
        self.settings.add_unsharp = self.unsharp_cb.isChecked()
        self.settings.add_micro_speed = self.speed_cb.isChecked()
        self.settings.add_pitch_shift = self.pitch_cb.isChecked()
        self.settings.add_eq_audio = self.eq_cb.isChecked()
        self.settings.add_volume_level = self.vol_cb.isChecked()
        self.settings.add_music_camouflage = self.music_camouflage_cb.isChecked()
        self.settings.add_bgm_overlay = self.bgm_overlay_cb.isChecked()
        self.settings.bgm_volume = float(self.bgm_vol_combo.currentData() or 0.12)
        # bgm_file_path is already set when user picks or resets
        self.settings.poison_metadata = self.meta_cb.isChecked()

        self.settings.marquee_enabled = self.marquee_cb.isChecked()
        self.settings.marquee_text = self.marquee_text_edit.text().strip() or "VIURECAP"
        self.settings.marquee_direction = "left_to_right" if self.radio_dir_ltr.isChecked() else "right_to_left"
        self.settings.marquee_speed = int(self.marquee_speed_combo.currentData() or 70)

        self.settings_saved.emit(self.settings)
        self.accept()
