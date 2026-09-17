"""Shared, project-owned preview/export controls."""
from PySide6.QtWidgets import (QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
    QLineEdit, QPushButton, QDialogButtonBox, QFileDialog, QComboBox, QCheckBox)


class ReviewPresentationDialog(QDialog):
    def __init__(self, settings, export_config=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Âm thanh, phụ đề và nhận diện")
        self.resize(560, 760)
        self.form = QFormLayout(self)
        self.fields = {}
        for key, title, default, maximum in (
            ("voice_gain", "Âm lượng giọng (%)", 100, 200),
            ("original_gain", "Âm lượng phim gốc (%)", 0, 100),
            ("music_gain", "Âm lượng nhạc (%)", 100, 200),
            ("font_percent", "Cỡ phụ đề (% chiều cao hình)", 3.2, 8),
            ("bottom_percent", "Cách đáy hình (%)", 9, 40),
            ("words_per_caption", "Số từ tối đa mỗi cụm phụ đề", 8, 20),
            ("max_chars_per_line", "Ký tự tối đa mỗi dòng", 42, 80),
            ("max_caption_lines", "Số dòng phụ đề tối đa", 2, 2),
            ("logo_percent", "Kích thước logo (% chiều rộng)", 12, 35),
            ("source_overlay_x", "Overlay nguồn: X (%)", 70, 100),
            ("source_overlay_y", "Overlay nguồn: Y (%)", 2, 100),
            ("source_overlay_width", "Overlay nguồn: rộng (%)", 27, 100),
            ("source_overlay_height", "Overlay nguồn: cao (%)", 12, 100),
        ):
            spin = QDoubleSpinBox(self)
            positive = {"font_percent", "words_per_caption", "max_chars_per_line", "max_caption_lines",
                        "logo_percent", "source_overlay_width", "source_overlay_height"}
            spin.setRange(1 if key in positive else 0, maximum)
            spin.setDecimals(1 if key == "font_percent" else 0)
            spin.setValue(float(settings.get(key, default)))
            self.fields[key] = spin
            self.form.addRow(title, spin)
        self.logo = QLineEdit(str(settings.get("logo_path", "")))
        self.watermark_enabled = QCheckBox("Bật watermark kênh")
        self.watermark_enabled.setChecked(bool(settings.get("watermark_enabled", False)))
        self.form.addRow(self.watermark_enabled)
        self.watermark_position = QComboBox()
        for label, value in (("Dưới trái", "bottom-left"), ("Dưới phải", "bottom-right"),
                             ("Trên trái", "top-left"), ("Trên phải", "top-right")):
            self.watermark_position.addItem(label, value)
        self.watermark_position.setCurrentIndex(max(0, self.watermark_position.findData(settings.get("watermark_position", "bottom-left"))))
        self.form.addRow("Vị trí watermark", self.watermark_position)
        self.watermark_opacity = QDoubleSpinBox()
        self.watermark_opacity.setRange(0, 100)
        self.watermark_opacity.setValue(float(settings.get("watermark_opacity", 60)))
        self.form.addRow("Độ mờ watermark (%)", self.watermark_opacity)
        self.form.addRow("File logo (để trống để xóa)", self.logo)
        choose = QPushButton("Chọn ảnh logo…")
        choose.clicked.connect(self.choose_logo)
        self.form.addRow(choose)
        self.title = QLineEdit(str(settings.get("title", "")))
        self.title_enabled = QCheckBox("Bật title overlay")
        self.title_enabled.setChecked(bool(settings.get("title_enabled", False)))
        self.form.addRow(self.title_enabled)
        self.title_persistent = QCheckBox("Hiện title suốt video")
        self.title_persistent.setChecked(bool(settings.get("title_persistent", True)))
        self.form.addRow(self.title_persistent)
        self.form.addRow("Chữ đầu video / tên kênh", self.title)
        self.title_position = QComboBox()
        self.title_position.addItem("Trên trái", "top-left")
        self.title_position.addItem("Trên phải", "top-right")
        self.title_position.setCurrentIndex(max(0, self.title_position.findData(settings.get("title_position", "top-left"))))
        self.form.addRow("Vị trí title", self.title_position)
        self.source_overlay = QComboBox()
        for label, value in (("Giữ nguyên overlay nguồn", "keep"), ("Làm mờ", "blur"),
                             ("Crop", "crop"), ("Che phủ", "cover")):
            self.source_overlay.addItem(label, value)
        self.source_overlay.setCurrentIndex(max(0, self.source_overlay.findData(settings.get("source_overlay_mode", "keep"))))
        self.form.addRow("Overlay có sẵn trong phim", self.source_overlay)
        self.intro_enabled = QCheckBox("Bật intro bumper")
        self.intro_enabled.setChecked(bool(settings.get("intro_bumper_enabled", False)))
        self.form.addRow(self.intro_enabled)
        self.intro = QLineEdit(str(settings.get("intro_bumper_path", "")))
        self.form.addRow("File intro bumper", self.intro)
        intro_choose = QPushButton("Chọn video intro…")
        intro_choose.clicked.connect(self.choose_intro)
        self.form.addRow(intro_choose)
        self.canvas = QComboBox()
        for label, value in (("Giữ tỷ lệ nguồn", "KEEP_SOURCE"), ("Đệm nền dọc 9:16", "PAD_VERTICAL"),
                             ("Crop dọc 9:16", "CROP_VERTICAL"), ("Crop vuông 1:1", "CROP_SQUARE"),
                             ("Tùy chỉnh", "CUSTOM")):
            self.canvas.addItem(label, value)
        config = export_config or {}
        self.canvas.setCurrentIndex(max(0, self.canvas.findData(config.get("canvas_mode", "KEEP_SOURCE"))))
        self.form.addRow("Tỷ lệ khung xuất", self.canvas)
        self.custom_width = QSpinBox()
        self.custom_width.setRange(320, 7680)
        self.custom_width.setValue(int(config.get("custom_width", 1920) or 1920))
        self.form.addRow("Custom width", self.custom_width)
        self.custom_height = QSpinBox()
        self.custom_height.setRange(320, 7680)
        self.custom_height.setValue(int(config.get("custom_height", 1080) or 1080))
        self.form.addRow("Custom height", self.custom_height)
        self.platform = QComboBox()
        for label, value in (("YouTube ngang", "youtube_landscape"), ("YouTube Shorts", "youtube_shorts"),
                             ("TikTok", "tiktok"), ("Tùy chỉnh", "custom")):
            self.platform.addItem(label, value)
        self.platform.setCurrentIndex(max(0, self.platform.findData(config.get("target_platform", "youtube_landscape"))))
        self.form.addRow("Nền tảng", self.platform)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn logo", "", "Ảnh (*.png *.jpg *.webp)")
        if path:
            self.logo.setText(path)

    def choose_intro(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn intro bumper", "", "Video (*.mp4 *.mov *.mkv)")
        if path:
            self.intro.setText(path)

    def values(self):
        presentation = {**{key: spin.value() for key, spin in self.fields.items()},
                "logo_path": self.logo.text().strip(), "title": self.title.text().strip(),
                "title_enabled": self.title_enabled.isChecked(),
                "title_persistent": self.title_persistent.isChecked(),
                "watermark_enabled": self.watermark_enabled.isChecked(),
                "watermark_position": self.watermark_position.currentData(),
                "watermark_opacity": self.watermark_opacity.value(),
                "title_position": self.title_position.currentData(),
                "source_overlay_mode": self.source_overlay.currentData(),
                "intro_bumper_enabled": self.intro_enabled.isChecked(),
                "intro_bumper_path": self.intro.text().strip()}
        return presentation, {"canvas_mode": self.canvas.currentData(),
                              "output_resolution": "auto", "target_platform": self.platform.currentData(),
                              "custom_width": self.custom_width.value(),
                              "custom_height": self.custom_height.value()}
