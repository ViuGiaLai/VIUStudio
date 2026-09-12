
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def _section_title(text):
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def _section_card():
    card = QFrame()
    card.setObjectName("statusCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)
    return card, layout


def _build_collapsible_section(title: str, start_expanded: bool = True):
    wrapper = QFrame()
    wrapper.setObjectName("statusCard")
    wrapper_layout = QVBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(10, 8, 10, 8)
    wrapper_layout.setSpacing(6)

    toggle_btn = QToolButton()
    toggle_btn.setText(("▼ " if start_expanded else "▶ ") + title)
    toggle_btn.setCheckable(True)
    toggle_btn.setChecked(start_expanded)
    toggle_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    toggle_btn.setStyleSheet("QToolButton { text-align: left; font-weight: 600; font-size: 12px; color: #93c5fd; border: none; padding: 2px 0; }")

    content = QWidget()
    content_layout = QVBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(8)
    content.setVisible(start_expanded)

    def _toggle_section(checked: bool):
        toggle_btn.setText(("▼ " if checked else "▶ ") + title)
        content.setVisible(checked)
        content.setMaximumHeight(16777215 if checked else 0)

    toggle_btn.toggled.connect(_toggle_section)
    wrapper_layout.addWidget(toggle_btn)
    wrapper_layout.addWidget(content)
    return wrapper, content_layout


def _build_hidden_status_widgets(gui):
    gui.workflow_hint_label = QLabel()
    gui.workflow_hint_label.setObjectName("helperLabel")
    gui.workflow_hint_label.setWordWrap(True)
    gui.workflow_hint_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    gui.workflow_hint_label.setTextInteractionFlags(Qt.NoTextInteraction)


def _build_style_preset_card(title: str, line_one: str, line_two: str, radio: QRadioButton):
    card = QFrame()
    card.setObjectName("statusCard")
    card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    card.setStyleSheet(
        "QFrame#statusCard { background-color: #141824; border: 1px solid #23293a; border-radius: 10px; }"
        "QFrame#statusCard:hover { border-color: #3b82f6; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(4)
    layout.addWidget(radio, 0, Qt.AlignTop)

    title_label = QLabel(title)
    title_label.setObjectName("sectionTitle")
    title_label.setAlignment(Qt.AlignCenter)

    style_key = title.strip().lower()
    preview_frame = QFrame()
    preview_frame.setFixedHeight(88)
    preview_frame.setStyleSheet(
        "QFrame {"
        "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #1a2030, stop:1 #0e1118);"
        "border:1px solid #252b3d; border-radius: 8px; }"
    )
    preview_layout = QVBoxLayout(preview_frame)
    preview_layout.setContentsMargins(10, 10, 10, 10)
    preview_layout.setSpacing(2)

    preview_top = QLabel(line_one)
    preview_bottom = QLabel(line_two)
    preview_top.setAlignment(Qt.AlignCenter)
    preview_bottom.setAlignment(Qt.AlignCenter)

    if style_key == "tiktok":
        preview_top.setStyleSheet("font-size: 18px; font-weight: 900; color: #ffffff;")
        preview_bottom.setStyleSheet("font-size: 16px; font-weight: 900; color: #ffd400;")
    elif style_key == "youtube":
        preview_top.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #ffffff; "
            "background-color: rgba(0, 0, 0, 255); padding: 4px 8px; border-radius: 6px;"
        )
        preview_bottom.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #ffffff; "
            "background-color: rgba(0, 0, 0, 255); padding: 4px 8px; border-radius: 6px;"
        )
    elif style_key == "short":
        preview_top.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff; letter-spacing: 1px;")
        preview_bottom.setStyleSheet("font-size: 13px; color: #cbd5e1;")
    else:
        preview_top.setStyleSheet("font-size: 15px; font-weight: 800; color: #ffffff;")
        preview_bottom.setStyleSheet(
            "font-size: 13px; color: #ffffff; background-color: rgba(0, 0, 0, 120); "
            "padding: 3px 8px; border-radius: 6px;"
        )

    preview_layout.addStretch(1)
    preview_layout.addWidget(preview_top)
    preview_layout.addWidget(preview_bottom)
    preview_layout.addStretch(1)

    layout.addWidget(title_label, 0, Qt.AlignCenter)
    layout.addWidget(preview_frame)
    return card


def _build_filter_preset_button(label: str):
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setObjectName("workflowTabBtn")
    btn.setMinimumHeight(28)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return btn


def _build_filter_slider_row(title: str, slider: QSlider, value_label: QLabel):
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    header = QHBoxLayout()
    header.setContentsMargins(0, 0, 0, 0)
    header.setSpacing(8)
    title_label = QLabel(title)
    title_label.setObjectName("helperLabel")
    value_label.setObjectName("helperLabel")
    value_label.setMinimumWidth(42)
    value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    header.addWidget(title_label)
    header.addStretch(1)
    header.addWidget(value_label)
    layout.addLayout(header)
    layout.addWidget(slider)
    return wrapper


def _update_device_label(gui):
    import os
    cpu_mode = os.getenv("VIUSTUDIO_DEVICE", "cuda").strip().lower() == "cpu"
    if cpu_mode:
        gui.device_mode_label.setText("⚙ CPU Mode")
        gui.device_mode_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #f59e0b;")
    else:
        gpu_name = os.getenv("VIUSTUDIO_GPU_NAME", "").strip()
        if gpu_name:
            gui.device_mode_label.setText(f"⚡ {gpu_name}")
        else:
            gui.device_mode_label.setText("⚡ GPU Accelerated")
        gui.device_mode_label.setStyleSheet("font-size: 11px; font-weight: 600; color: #10b981;")


def build_start_group(gui, left_layout):
    _build_hidden_status_widgets(gui)

    gui.video_path_edit = QLineEdit()
    gui.video_path_edit.setPlaceholderText("Choose one video to process...")
    gui.video_path_edit.hide()

    # Empty means "next to the source". The actual destination is always
    # confirmed by Save As; do not silently default to the repository output.
    gui.final_output_folder_edit = QLineEdit("")
    gui.final_output_folder_edit.setPlaceholderText("Folder to save final results...")
    gui.final_output_folder_edit.hide()

    gui.run_all_btn = QToolButton()
    gui.run_all_btn.setObjectName("mainActionBtn")
    gui.run_all_btn.setPopupMode(QToolButton.InstantPopup)
    gui.run_all_btn.setText("Generate")
    gui._generate_menu = None

    gui.export_btn = QPushButton("Export")
    gui.export_btn.setObjectName("mainActionBtn")
    # clicked emits a bool, while export_final_video's automatic flag is
    # keyword-only. Do not forward the signal argument.
    gui.export_btn.clicked.connect(lambda _checked=False: gui.export_final_video())

    gui.preview_5s_btn = QPushButton("Fast Preview")
    gui.preview_5s_btn.clicked.connect(gui.preview_five_seconds)
    gui.preview_frame_btn = QPushButton("Open Large Frame Preview")
    gui.preview_frame_btn.clicked.connect(gui.preview_exact_frame)
    gui.open_output_btn = QPushButton("Open Results Folder")
    gui.open_output_btn.clicked.connect(lambda: gui.open_folder(gui.final_output_folder_edit.text()))

    gui.stabilize_button(gui.run_all_btn, min_width=240)
    gui.stabilize_button(gui.export_btn, min_width=180)

    workflow_shell, workflow_shell_layout = _section_card()
    workflow_shell_layout.setContentsMargins(12, 10, 12, 10)
    workflow_shell_layout.setSpacing(8)

    workflow_header_row = QHBoxLayout()
    workflow_title = QLabel("Workflow")
    workflow_title.setObjectName("statusHeadline")
    workflow_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #f8fafc;")
    workflow_header_row.addWidget(workflow_title)
    workflow_header_row.addStretch(1)

    gui.device_mode_label = QLabel()
    gui.device_mode_label.setObjectName("helperLabel")
    _update_device_label(gui)
    workflow_header_row.addWidget(gui.device_mode_label)
    workflow_shell_layout.addLayout(workflow_header_row)

    # Generation milestones remain visible while users work through the
    # configuration pages below.
    gui.workflow_stage_badges = {}
    gui.workflow_stage_labels = {}
    stage_box = QFrame()
    stage_box.setObjectName("statusCard")
    stage_box.setStyleSheet(
        "QFrame#statusCard { background-color: #11141d; border: 1px solid #1e2433; border-radius: 8px; }"
    )
    stage_layout = QVBoxLayout(stage_box)
    stage_layout.setContentsMargins(8, 6, 8, 6)
    stage_layout.setSpacing(4)
    for key, title in (("prepare", "Prepare"), ("transcript", "Transcript"),
                       ("translate", "Translate"), ("tts", "Voice / TTS (Optional)"),
                       ("export", "Export")):
        row = QHBoxLayout()
        label = QLabel(title)
        label.setStyleSheet("font-size: 11px; color: #cbd5e1;")
        status = QLabel("Not started")
        status.setObjectName("helperLabel")
        status.setStyleSheet("font-size: 11px; color: #64748b;")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(status)
        stage_layout.addLayout(row)
        gui.workflow_stage_badges[key] = status
        gui.workflow_stage_labels[key] = label
    workflow_shell_layout.addWidget(stage_box)

    tab_bar = QWidget()
    # The redesigned editor uses the persistent navigation rail. Keep this
    # legacy tab container available for compatibility, but do not render a
    # second competing navigation control in the new shell.
    tab_bar.setObjectName("legacyWorkflowTabBar")
    tab_bar_layout = QGridLayout(tab_bar)
    tab_bar_layout.setContentsMargins(0, 0, 0, 0)
    tab_bar_layout.setHorizontalSpacing(6)
    tab_bar_layout.setVerticalSpacing(6)
    tab_bar_layout.setColumnStretch(0, 1)
    tab_bar_layout.setColumnStretch(1, 1)
    tab_group = QButtonGroup(gui)
    tab_group.setExclusive(True)
    gui.left_panel_stack = QStackedWidget()
    gui.left_panel_stack.setObjectName("leftPanelStack")

    gui.workflow_page_containers = {}
    gui.workflow_page_hints = {}
    gui.workflow_tab_buttons = {}

    def _make_page(page_key: str):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        lock_hint = QLabel("")
        lock_hint.setObjectName("helperLabel")
        lock_hint.setWordWrap(True)
        lock_hint.setVisible(False)
        layout.addWidget(lock_hint)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        layout.addWidget(content)

        gui.workflow_page_containers[page_key] = content
        gui.workflow_page_hints[page_key] = lock_hint
        return page, content_layout

    pages = []
    media_page, media_layout = _make_page("media")
    audio_page, audio_layout = _make_page("audio")
    gui.workflow_audio_layout = audio_layout
    language_page, language_layout = _make_page("language")
    voice_page, voice_layout = _make_page("voice")
    style_page, style_layout = _make_page("style")
    advanced_page, advanced_layout = _make_page("advanced")
    gui.workflow_advanced_layout = advanced_layout
    pages.extend([media_page, audio_page, language_page, voice_page, style_page, advanced_page])

    def _add_tab(label: str, page_index: int, page_key: str, checked: bool = False):
        btn = QPushButton(label)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setMinimumHeight(28)
        btn.setMinimumWidth(0)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setObjectName("workflowTabBtn")
        tab_group.addButton(btn)
        row = page_index // 2
        col = page_index % 2
        tab_bar_layout.addWidget(btn, row, col)
        btn.toggled.connect(lambda active, idx=page_index: active and gui.left_panel_stack.setCurrentIndex(idx))
        gui.workflow_tab_buttons[page_key] = btn
        return btn

    _add_tab("Media", 0, "media", checked=True)
    gui.audio_tab_btn = _add_tab("Audio", 1, "audio")
    gui.audio_tab_btn.setEnabled(False)
    _add_tab("Language", 2, "language")
    _add_tab("Voice", 3, "voice")
    _add_tab("Style", 4, "style")
    _add_tab("Advanced", 5, "advanced")
    gui.show_progress_btn = QPushButton("Show Progress")
    gui.show_progress_btn.clicked.connect(gui.show_active_progress_dialog)
    gui.show_progress_btn.setVisible(False)
    gui.show_progress_btn.setEnabled(False)
    gui.show_progress_btn.setObjectName("workflowTabBtn")
    gui.show_progress_btn.setMinimumHeight(28)
    gui.show_progress_btn.setMinimumWidth(0)
    gui.show_progress_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    tab_bar_layout.addWidget(gui.show_progress_btn, 3, 0, 1, 2)
    gui.workflow_tab_bar = tab_bar
    tab_bar.setVisible(False)
    workflow_shell_layout.addWidget(tab_bar)

    upload_card, upload_layout = _build_collapsible_section("Video")
    upload_card.hide()

    output_card, output_layout = _build_collapsible_section("Output")
    output_mode_card, output_mode_layout = _section_card()
    output_mode_title = QLabel("Output Mode")
    output_mode_title.setObjectName("sectionTitle")
    output_mode_layout.addWidget(output_mode_title)
    gui.output_mode_combo = QComboBox(gui)
    gui.output_mode_combo.addItem("Vietnamese subtitles + voice")
    gui.output_mode_combo.addItem("Vietnamese voice only")
    gui.output_mode_combo.addItem("Vietnamese subtitles only")
    gui.output_mode_combo.setCurrentText("Vietnamese subtitles + voice")
    output_mode_layout.addWidget(gui.output_mode_combo)
    output_layout.addWidget(output_mode_card)

    output_quality_card, output_quality_layout = _section_card()
    output_quality_title = QLabel("Quality")
    output_quality_title.setObjectName("sectionTitle")
    output_quality_layout.addWidget(output_quality_title)
    gui.output_quality_combo = QComboBox()
    # Keep controls readable when the left workbench is vertically compact.
    # Nested rows otherwise allow Qt to squeeze combo boxes down to a few
    # pixels while the scroll area is resolving its minimum height.
    gui.output_quality_combo.setMinimumHeight(32)
    gui.output_quality_combo.addItem("Max (source)", "source")
    gui.output_quality_combo.addItem("720p", "720p")
    gui.output_quality_combo.addItem("1080p (Full HD)", "1080p")
    gui.output_quality_combo.addItem("1440p (2K)", "1440p")
    gui.output_quality_combo.addItem("2160p (4K)", "2160p")
    output_quality_layout.addWidget(gui.output_quality_combo)
    output_preset_row = QVBoxLayout()
    output_preset_row.addWidget(QLabel("Export preset"))
    gui.output_preset_combo = QComboBox()
    gui.output_preset_combo.addItem("Fast (stream copy / ultrafast)", "fast")
    gui.output_preset_combo.addItem("Balanced (veryfast)", "balanced")
    gui.output_preset_combo.addItem("Maximum quality (medium)", "max")
    gui.output_preset_combo.setCurrentIndex(0)
    gui.output_preset_combo.setToolTip(
        "Fast copies unchanged video whenever possible. Visual effects and burned subtitles still require rendering."
    )
    output_preset_row.addWidget(gui.output_preset_combo)
    output_quality_layout.addLayout(output_preset_row)
    bitrate_row = QHBoxLayout()
    bitrate_row.addWidget(QLabel("Video bitrate"))
    gui.output_bitrate_spin = QSpinBox()
    gui.output_bitrate_spin.setRange(500, 50000)
    gui.output_bitrate_spin.setSingleStep(500)
    gui.output_bitrate_spin.setValue(2000)
    gui.output_bitrate_spin.setSuffix(" kbps")
    gui.output_bitrate_spin.setToolTip("Target bitrate; 2000 kbps is a good Auto Recap starting point.")
    bitrate_row.addWidget(gui.output_bitrate_spin)
    output_quality_layout.addLayout(bitrate_row)
    output_fps_row = QVBoxLayout()
    output_fps_row.addWidget(QLabel("Frame rate"))
    gui.output_fps_combo = QComboBox()
    gui.output_fps_combo.setMinimumHeight(32)
    gui.output_fps_combo.addItem("Source (Recommended)", "source")
    gui.output_fps_combo.addItem("24 FPS", "24")
    gui.output_fps_combo.addItem("30 FPS", "30")
    gui.output_fps_combo.addItem("60 FPS", "60")
    output_fps_row.addWidget(gui.output_fps_combo)
    output_quality_layout.addLayout(output_fps_row)
    output_ratio_row = QVBoxLayout()
    output_ratio_row.addWidget(QLabel("Ratio"))
    gui.output_ratio_combo = QComboBox()
    gui.output_ratio_combo.setMinimumHeight(32)
    gui.output_ratio_combo.addItem("Source (Recommended)", "source")
    gui.output_ratio_combo.addItem("16:9", "16:9")
    gui.output_ratio_combo.addItem("9:16", "9:16")
    gui.output_ratio_combo.addItem("1:1", "1:1")
    gui.output_ratio_combo.addItem("4:3", "4:3")
    gui.output_ratio_combo.currentIndexChanged.connect(gui.on_output_ratio_changed)
    output_ratio_row.addWidget(gui.output_ratio_combo)
    output_quality_layout.addLayout(output_ratio_row)
    output_scale_row = QVBoxLayout()
    output_scale_row.addWidget(QLabel("Canvas"))
    gui.output_scale_mode_combo = QComboBox()
    gui.output_scale_mode_combo.setMinimumHeight(32)
    gui.output_scale_mode_combo.addItem("Fit", "fit")
    gui.output_scale_mode_combo.addItem("Fill", "fill")
    gui.output_scale_mode_combo.currentIndexChanged.connect(gui.on_output_scale_mode_changed)
    output_scale_row.addWidget(gui.output_scale_mode_combo)
    gui.reset_framing_btn = QPushButton("Reset Framing")
    gui.reset_framing_btn.setMinimumHeight(30)
    gui.reset_framing_btn.setToolTip("Reset the fill focus to center")
    gui.reset_framing_btn.hide()
    output_scale_row.addWidget(gui.reset_framing_btn)
    output_quality_layout.addLayout(output_scale_row)

    # --- Anti-Duplicate Mode (chong nhan dien Content ID) ---
    _ad_sep = QFrame()
    _ad_sep.setFrameShape(QFrame.HLine)
    _ad_row = QHBoxLayout()
    _ad_row.setSpacing(6)
    gui.anti_duplicate_cb = QCheckBox("🛡️ Chế độ Chống trùng lặp")
    gui.anti_duplicate_cb.setChecked(True)
    gui.anti_duplicate_cb.setToolTip(
        "Bật chế độ chống nhận diện video trùng lặp (Content ID):\n"
        "  - 4 phong cách làm mới (Letterbox 2.05:1, Ambient 92%, Ken Burns Pan, Vệt sáng)\n"
        "  - Xen kẽ 4p xuôi / 1p lật thông minh\n"
        "  - Xoay vòng 4 tone màu điện ảnh mỗi 4 phút\n"
        "  - Zoom 105% & Punch Zoom, Grain noise, Unsharp, Pitch shift\n\n"
        "Nên bật khi upload video recap/dịch lên YouTube / TikTok / Facebook."
    )
    _ad_row.addWidget(gui.anti_duplicate_cb)
    _ad_row.addStretch(1)

    gui.anti_duplicate_config_btn = QPushButton("⚙️ Tùy chỉnh...")
    gui.anti_duplicate_config_btn.setToolTip("Mở bảng tùy chỉnh: Chọn 4 phong cách làm mới khung hình, chế độ lật gương, tone màu...")
    gui.anti_duplicate_config_btn.setStyleSheet("""
        QPushButton {
            background-color: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
            border-radius: 5px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #334155;
            color: #ffffff;
            border-color: #38bdf8;
        }
    """)

    def _open_ad_custom():
        from app.anti_duplicate import AntiDuplicateSettings
        from ui.dialogs.anti_duplicate_custom_dialog import AntiDuplicateCustomDialog
        ad_settings = getattr(gui, "_anti_duplicate_settings", None)
        if ad_settings is None and hasattr(gui, "current_project_state") and gui.current_project_state:
            ps = gui.current_project_state
            saved = None
            if hasattr(ps, "get_setting"):
                saved = ps.get_setting("anti_duplicate_custom_settings", None)
            elif hasattr(ps, "settings") and isinstance(getattr(ps, "settings", None), dict):
                saved = ps.settings.get("anti_duplicate_custom_settings", None)
            if saved and isinstance(saved, dict):
                ad_settings = AntiDuplicateSettings.from_dict(saved)
        if ad_settings is None:
            ad_settings = AntiDuplicateSettings(enabled=True, continuous_mode=True, allow_horizontal_flip=True)
        dlg = AntiDuplicateCustomDialog(ad_settings, parent=gui)
        if dlg.exec():
            gui._anti_duplicate_settings = dlg.settings
            gui.anti_duplicate_cb.setChecked(True)
            if hasattr(gui, "current_project_state") and gui.current_project_state:
                ps = gui.current_project_state
                if hasattr(ps, "set_setting"):
                    ps.set_setting("anti_duplicate_custom_settings", dlg.settings.to_dict())
                elif hasattr(ps, "settings") and isinstance(getattr(ps, "settings", None), dict):
                    ps.settings["anti_duplicate_custom_settings"] = dlg.settings.to_dict()

    gui.anti_duplicate_config_btn.clicked.connect(_open_ad_custom)
    _ad_row.addWidget(gui.anti_duplicate_config_btn)
    output_quality_layout.addLayout(_ad_row)

    gui.run_anti_duplicate_btn = QPushButton("⚡ Phân tích && Tạo video Chống trùng\n(Xem trước ngay)")
    gui.run_anti_duplicate_btn.setMinimumHeight(44)
    gui.run_anti_duplicate_btn.setToolTip(
        "Tự động phân tích cảnh (Scene Detection), áp dụng Zoom kháng hash (≥105%), chỉnh màu tự động per-shot, "
        "dịch cao độ audio (±2%) và tạo video xem trước ngay trên Preview Player & Timeline!"
    )
    gui.run_anti_duplicate_btn.setStyleSheet("""
        QPushButton {
            background-color: #1e3a5f;
            color: #93c5fd;
            border: 1px solid #3b82f6;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 8px;
            text-align: center;
        }
        QPushButton:hover {
            background-color: #2563eb;
            color: #ffffff;
            border-color: #60a5fa;
        }
        QPushButton:pressed {
            background-color: #1d4ed8;
        }
    """)
    def _on_run_anti_dup_clicked():
        gui.anti_duplicate_cb.setChecked(True)
        if hasattr(gui, "auto_recap_config") and gui.auto_recap_config:
            gui.auto_recap_config.anti_duplicate = True
            gui.auto_recap_config.enabled = True
        if hasattr(gui, "run_auto_recap_workflow"):
            gui.run_auto_recap_workflow()
        elif hasattr(gui, "pipeline_controller") and hasattr(gui.pipeline_controller, "run_auto_recap_pipeline"):
            gui.pipeline_controller.run_auto_recap_pipeline()
    gui.run_anti_duplicate_btn.clicked.connect(_on_run_anti_dup_clicked)
    output_quality_layout.addWidget(gui.run_anti_duplicate_btn)

    gui.compare_anti_duplicate_btn = QPushButton("🔍 So sánh Video Gốc vs Đã xử lý")
    gui.compare_anti_duplicate_btn.setMinimumHeight(34)
    gui.compare_anti_duplicate_btn.setToolTip("Mở cửa sổ so sánh song song 2 video để trực tiếp kiểm tra hình ảnh và âm thanh thay đổi.")
    gui.compare_anti_duplicate_btn.setStyleSheet("""
        QPushButton {
            background-color: #0f172a;
            color: #38bdf8;
            border: 1px dashed #0284c7;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            padding: 4px;
        }
        QPushButton:hover {
            background-color: #1e293b;
            color: #7dd3fc;
            border-style: solid;
        }
    """)
    if hasattr(gui, "open_video_compare_dialog"):
        gui.compare_anti_duplicate_btn.clicked.connect(gui.open_video_compare_dialog)
    output_quality_layout.addWidget(gui.compare_anti_duplicate_btn)

    gui.anti_duplicate_hint = QLabel(
        "Khi bật: Bấm nút bên trên để xử lý ngay (0% ➔ 100%), xem trước trên Preview và xem chi tiết hiệu ứng trên Timeline; hoặc áp dụng khi 'Export'.",
        gui,
    )
    gui.anti_duplicate_hint.setObjectName("helperLabel")
    gui.anti_duplicate_hint.setWordWrap(True)
    output_quality_layout.addWidget(gui.anti_duplicate_hint)

    def _on_ad_toggled(checked: bool):
        if checked:
            gui.anti_duplicate_hint.setText(
                "🛡️ ĐÃ BẬT: Bấm nút 'Phân tích && Tạo video' để xem trước ngay hoặc bấm 'Export' để xuất file cuối."
            )
            gui.anti_duplicate_hint.setStyleSheet("color: #4ade80; font-weight: 500;")
            if hasattr(gui, "auto_recap_config") and gui.auto_recap_config:
                gui.auto_recap_config.anti_duplicate = True
            if hasattr(gui, "log"):
                gui.log("[Chống trùng lặp] Đã bật chế độ chống trùng lặp (Anti-Duplicate Mode).")
        else:
            gui.anti_duplicate_hint.setText(
                "Khi bật: Bấm nút bên trên để xử lý ngay (0% ➔ 100%), xem trước trên Preview và xem chi tiết hiệu ứng trên Timeline; hoặc áp dụng khi 'Export'."
            )
            gui.anti_duplicate_hint.setStyleSheet("")
            if hasattr(gui, "auto_recap_config") and gui.auto_recap_config:
                gui.auto_recap_config.anti_duplicate = False
            if hasattr(gui, "log"):
                gui.log("[Chống trùng lặp] Đã tắt chế độ chống trùng lặp.")

    gui.anti_duplicate_cb.toggled.connect(_on_ad_toggled)
    _on_ad_toggled(gui.anti_duplicate_cb.isChecked())
    # --- het Anti-Duplicate Mode ---

    output_layout.addWidget(output_quality_card)


    audio_cleanup_card, audio_cleanup_layout = _section_card()
    audio_cleanup_title = QLabel("Audio Processing")
    audio_cleanup_title.setObjectName("sectionTitle")
    audio_cleanup_layout.addWidget(audio_cleanup_title)
    gui.audio_handling_combo = QComboBox()
    gui.audio_handling_combo.addItem("Fast (recommended)", "fast")
    gui.audio_handling_combo.addItem("Cleaner voice (remove original voice)", "clean")
    gui.audio_handling_combo.setCurrentIndex(0)
    audio_cleanup_layout.addWidget(gui.audio_handling_combo)
    gui.audio_handling_hint_label = QLabel("Fast keeps original audio with voice. Cleaner removes original voice, keeping only background music.", gui)
    gui.audio_handling_hint_label.setObjectName("helperLabel")
    gui.audio_handling_hint_label.setWordWrap(True)
    audio_cleanup_layout.addWidget(gui.audio_handling_hint_label)

    diarization_card, diarization_layout = _section_card()
    gui.speaker_diarization_card = diarization_card
    diarization_title = QLabel("Speaker Diarization")
    diarization_title.setObjectName("sectionTitle")
    diarization_layout.addWidget(diarization_title)
    gui.speaker_diarization_cb = QCheckBox("Enable speaker diarization")
    # Opt-in by default: diarization is an additional analysis pass and
    # should never add work to a new project unless the user enables it.
    gui.speaker_diarization_cb.setChecked(False)
    gui.speaker_diarization_cb.setToolTip(
        "Detect speakers offline with Sherpa-ONNX and color TS1 segments. Available for audio transcription only."
    )
    diarization_layout.addWidget(gui.speaker_diarization_cb)
    expected_speakers_row = QVBoxLayout()
    expected_speakers_row.addWidget(QLabel("Expected speakers"))
    gui.speaker_diarization_speakers_combo = QComboBox()
    gui.speaker_diarization_speakers_combo.addItem("Auto detect", -1)
    for count in range(2, 9):
        gui.speaker_diarization_speakers_combo.addItem(f"{count} speakers", count)
    gui.speaker_diarization_speakers_combo.setToolTip(
        "Choose a count when you know the number of people speaking. "
        "Auto detect uses similarity-based clustering."
    )
    expected_speakers_row.addWidget(gui.speaker_diarization_speakers_combo)
    diarization_layout.addLayout(expected_speakers_row)
    gui.speaker_diarization_hint_label = QLabel(
        "Optional: detects speaker turns after extraction and colors TS1 segments. "
        "Requires local Sherpa-ONNX diarization models."
    )
    gui.speaker_diarization_hint_label.setObjectName("helperLabel")
    gui.speaker_diarization_hint_label.setWordWrap(True)
    diarization_layout.addWidget(gui.speaker_diarization_hint_label)
    output_layout.addWidget(audio_cleanup_card)
    output_layout.addWidget(diarization_card)

    # --- Auto Edit Recap Card (Tier 1 & Tier 2) ---
    recap_card, recap_layout = _section_card()
    recap_title = QLabel("Tự động cắt ghép Recap")
    recap_title.setObjectName("sectionTitle")
    recap_layout.addWidget(recap_title)

    recap_row = QHBoxLayout()
    gui.auto_recap_cb = QCheckBox("✨ Tự động cắt ghép Recap (Tối ưu tốc độ)")
    gui.auto_recap_cb.setChecked(True)
    gui.auto_recap_cb.setToolTip(
        "Giữ nguyên toàn bộ nội dung video gốc. Sử dụng ranh giới cảnh để áp dụng Zoom, Pan, Crop, Đổi màu, Tốc độ, Đổi góc an toàn và chống lặp hiệu ứng."
    )
    recap_row.addWidget(gui.auto_recap_cb, 1)

    gui.auto_recap_customize_btn = QPushButton("⚙ Tùy chỉnh")
    gui.auto_recap_customize_btn.setObjectName("secondaryActionBtn")
    gui.auto_recap_customize_btn.setToolTip("Tùy chỉnh chi tiết 12 quy tắc cắt ghép Recap")
    if hasattr(gui, "open_auto_recap_settings_dialog"):
        gui.auto_recap_customize_btn.clicked.connect(gui.open_auto_recap_settings_dialog)
    recap_row.addWidget(gui.auto_recap_customize_btn)
    recap_layout.addLayout(recap_row)

    recap_hint = QLabel("Giữ nguyên nội dung và tự động áp dụng hiệu ứng Zoom, Pan, Crop, chỉnh màu, đổi góc an toàn. Bấm 'Tùy chỉnh' để thay đổi chi tiết.", gui)
    recap_hint.setObjectName("helperLabel")
    recap_hint.setWordWrap(True)
    recap_layout.addWidget(recap_hint)
    output_layout.addWidget(recap_card)

    media_layout.addWidget(output_card)
    if hasattr(gui, "update_speaker_diarization_availability"):
        gui.update_speaker_diarization_availability()

    language_card, language_layout = _build_collapsible_section("Language")
    gui.lang_whisper_combo = QComboBox()
    gui.lang_whisper_combo.addItem("Auto Detect", "auto")
    gui.lang_whisper_combo.addItem("Chinese", "zh")
    gui.lang_whisper_combo.addItem("Japanese", "ja")
    gui.lang_whisper_combo.addItem("Korean", "ko")
    gui.lang_whisper_combo.addItem("English", "en")
    gui.lang_whisper_combo.addItem("Vietnamese", "vi")
    gui.lang_whisper_combo.addItem("Thai", "th")
    gui.lang_whisper_combo.addItem("Indonesian", "id")
    gui.lang_whisper_combo.addItem("Spanish", "es")
    gui.lang_whisper_combo.addItem("French", "fr")
    gui.lang_whisper_combo.addItem("German", "de")
    gui.lang_whisper_combo.addItem("Portuguese", "pt")
    gui.lang_whisper_combo.addItem("Russian", "ru")
    gui.lang_whisper_combo.addItem("Arabic", "ar")
    gui.lang_target_combo = QComboBox()
    gui.lang_target_combo.addItem("Vietnamese", "vi")
    gui.lang_target_combo.addItem("English", "en")
    gui.lang_target_combo.addItem("Japanese", "ja")
    gui.lang_target_combo.addItem("Korean", "ko")
    gui.lang_target_combo.addItem("Thai", "th")
    gui.lang_target_combo.addItem("Indonesian", "id")
    gui.lang_target_combo.addItem("Spanish", "es")
    gui.lang_target_combo.addItem("French", "fr")
    gui.lang_target_combo.addItem("German", "de")
    gui.lang_target_combo.addItem("Portuguese", "pt")
    gui.lang_target_combo.addItem("Russian", "ru")
    gui.lang_target_combo.addItem("Arabic", "ar")
    gui.lang_target_combo.addItem("Simplified Chinese", "zh-CN")
    gui.lang_target_combo.addItem("Traditional Chinese", "zh-TW")
    gui.lang_target_combo.setCurrentIndex(0)
    language_pair_card, language_pair_layout = _section_card()
    language_pair_title = QLabel("Language Pair")
    language_pair_title.setObjectName("sectionTitle")
    language_pair_layout.addWidget(language_pair_title)
    source_row = QVBoxLayout()
    source_row.addWidget(QLabel("Original language"))
    source_row.addWidget(gui.lang_whisper_combo)
    target_row = QVBoxLayout()
    target_row.addWidget(QLabel("Translate to"))
    target_row.addWidget(gui.lang_target_combo)
    language_pair_layout.addLayout(source_row)
    language_pair_layout.addLayout(target_row)

    language_layout.addWidget(language_pair_card)
    gui.lang_target_combo.currentIndexChanged.connect(gui.on_target_language_changed)

    # --- Translation Engine Section ---
    trans_engine_card, trans_engine_layout = _section_card()
    trans_engine_title = QLabel("Translation Engine")
    trans_engine_title.setObjectName("sectionTitle")
    trans_engine_layout.addWidget(trans_engine_title)

    gui.translation_engine_combo = QComboBox()
    gui.translation_engine_combo.addItem("🌐 Google Translate (Free, no API key)", "google")
    gui.translation_engine_combo.addItem("⚡ Google Gemini (Recommended, free API key)", "google_ai_studio")
    gui.translation_engine_combo.addItem("🐉 DeepSeek AI (Film and contextual translation)", "deepseek")
    gui.translation_engine_combo.addItem("🤖 ChatGPT / OpenAI", "openai")
    gui.translation_engine_combo.addItem("💻 Ollama (Local Offline)", "ollama")
    gui.translation_engine_combo.addItem("🧠 Llama.cpp (App Engine / GGUF)", "llama_app")
    gui.translation_engine_combo.addItem("⚙️ Custom API (OpenAI Compatible)", "custom")

    trans_engine_layout.addWidget(QLabel("Translation Provider"))
    trans_engine_layout.addWidget(gui.translation_engine_combo)

    # Config panel for API Key & Model
    gui.translation_config_panel = QWidget()
    trans_config_layout = QVBoxLayout(gui.translation_config_panel)
    trans_config_layout.setContentsMargins(0, 4, 0, 0)
    trans_config_layout.setSpacing(6)

    gui.translation_key_label = QLabel("API Key:")
    gui.translation_api_key_edit = QLineEdit()
    gui.translation_api_key_edit.setEchoMode(QLineEdit.Password)
    gui.translation_api_key_edit.setPlaceholderText("Enter the API key here...")

    gui.translation_model_label = QLabel("AI Model:")
    gui.translation_model_edit = QLineEdit()
    gui.translation_model_edit.setPlaceholderText("Example: gemini-2.5-flash")

    gui.translation_polish_model_label = QLabel("Quality Model (fix / review sentences):")
    gui.translation_polish_model_edit = QLineEdit()
    gui.translation_polish_model_edit.setPlaceholderText("Blank = use AI Model above (e.g. gemini-2.5-pro)")

    gui.translation_base_url_label = QLabel("API URL:")
    gui.translation_base_url_edit = QLineEdit()
    gui.translation_base_url_edit.setPlaceholderText("https://...")

    gui.translation_link_label = QLabel("")
    gui.translation_link_label.setObjectName("helperLabel")
    gui.translation_link_label.setWordWrap(True)
    gui.translation_link_label.setOpenExternalLinks(True)

    test_action_layout = QHBoxLayout()
    test_action_layout.setSpacing(8)
    gui.translation_test_btn = QPushButton("Test Connection")
    gui.translation_test_btn.setFixedHeight(26)
    gui.translation_test_status = QLabel("")
    gui.translation_test_status.setObjectName("helperLabel")
    test_action_layout.addWidget(gui.translation_test_btn)
    test_action_layout.addWidget(gui.translation_test_status, 1)

    trans_config_layout.addWidget(gui.translation_key_label)
    trans_config_layout.addWidget(gui.translation_api_key_edit)
    trans_config_layout.addWidget(gui.translation_model_label)
    trans_config_layout.addWidget(gui.translation_model_edit)
    trans_config_layout.addWidget(gui.translation_polish_model_label)
    trans_config_layout.addWidget(gui.translation_polish_model_edit)
    trans_config_layout.addWidget(gui.translation_base_url_label)
    trans_config_layout.addWidget(gui.translation_base_url_edit)
    trans_config_layout.addWidget(gui.translation_link_label)
    trans_config_layout.addLayout(test_action_layout)

    trans_engine_layout.addWidget(gui.translation_config_panel)

    # Llama App Engine Panel (Local GGUF)
    gui.llama_app_config_panel = QWidget()
    llama_layout = QVBoxLayout(gui.llama_app_config_panel)
    llama_layout.setContentsMargins(0, 4, 0, 0)
    llama_layout.setSpacing(6)
    
    llama_layout.addWidget(QLabel("Local Model (.gguf):"))
    
    gui.llama_model_combo = QComboBox()
    llama_layout.addWidget(gui.llama_model_combo)

    gui.llama_recommended_models = {}
    recommended_title = QLabel("Recommended models")
    recommended_title.setObjectName("helperLabel")
    llama_layout.addWidget(recommended_title)
    recommended_models = (
        ("hy_mt_1_8b", "HY-MT 1.8B", "Translation specialist · Recommended"),
        ("qwen3_4b", "Qwen3 4B", "Better context · Slower"),
        ("qwen2_5_1_5b", "Qwen2.5 1.5B", "Lightweight · Faster on low-end PCs"),
    )
    for model_id, title, description in recommended_models:
        row = QWidget(gui.llama_app_config_panel)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 4, 4)
        row_layout.setSpacing(8)
        text_label = QLabel(f"{title}\n{description}")
        text_label.setWordWrap(True)
        status_label = QLabel("Checking...")
        status_label.setObjectName("helperLabel")
        download_btn = QPushButton("Download")
        download_btn.setFixedHeight(26)
        download_btn.setProperty("llamaModelId", model_id)
        row_layout.addWidget(text_label, 1)
        row_layout.addWidget(status_label)
        row_layout.addWidget(download_btn)
        llama_layout.addWidget(row)
        gui.llama_recommended_models[model_id] = {
            "row": row,
            "status": status_label,
            "download": download_btn,
        }
    
    llama_action_layout = QHBoxLayout()
    llama_action_layout.setSpacing(8)
    
    gui.llama_engine_download_btn = QPushButton("Download llama.cpp Engine")
    gui.llama_engine_download_btn.setFixedHeight(26)
    gui.llama_engine_scan_btn = QPushButton("Scan for llama-server.exe")
    gui.llama_engine_scan_btn.setFixedHeight(26)
    # Shown automatically while llama-server.exe is missing from the app.
    gui.llama_engine_download_btn.hide()
    gui.llama_engine_scan_btn.hide()
    gui.llama_scan_btn = QPushButton("Scan Entire PC")
    gui.llama_scan_btn.setFixedHeight(26)
    gui.llama_download_btn = QPushButton("Download Model")
    gui.llama_download_btn.setFixedHeight(26)
    # Kept for compatibility with older settings/tests. Per-model download
    # buttons above are now the visible download controls.
    gui.llama_download_btn.hide()
    
    llama_action_layout.addWidget(gui.llama_engine_download_btn)
    llama_action_layout.addWidget(gui.llama_engine_scan_btn)
    llama_action_layout.addWidget(gui.llama_scan_btn)
    llama_action_layout.addWidget(gui.llama_download_btn)
    llama_layout.addLayout(llama_action_layout)
    
    gui.llama_status_label = QLabel("")
    gui.llama_status_label.setObjectName("helperLabel")
    gui.llama_status_label.setWordWrap(True)
    llama_layout.addWidget(gui.llama_status_label)
    
    llama_test_action_layout = QHBoxLayout()
    llama_test_action_layout.setSpacing(8)
    gui.llama_test_btn = QPushButton("Test Connection")
    gui.llama_test_btn.setFixedHeight(26)
    gui.llama_test_status = QLabel("")
    gui.llama_test_status.setObjectName("helperLabel")
    llama_test_action_layout.addWidget(gui.llama_test_btn)
    llama_test_action_layout.addWidget(gui.llama_test_status, 1)
    llama_layout.addLayout(llama_test_action_layout)
    
    trans_engine_layout.addWidget(gui.llama_app_config_panel)
    gui.llama_app_config_panel.setVisible(False)

    # Style Preset for Tu Tien / Recap
    trans_style_row = QVBoxLayout()
    trans_style_row.setSpacing(4)
    trans_style_row.addWidget(QLabel("Translation Style"))
    gui.translation_style_preset_combo = QComboBox()
    gui.translation_style_preset_combo.addItem("Standard / Natural", "standard")
    gui.translation_style_preset_combo.addItem("Cultivation / Wuxia Recap (Concise, consistent honorifics)", "tutien_recap")
    gui.translation_style_preset_combo.addItem("Anime / Manga (Youthful and lively)", "anime")
    gui.translation_style_preset_combo.addItem("Cinematic / Dramatic", "drama")
    trans_style_row.addWidget(gui.translation_style_preset_combo)
    trans_engine_layout.addLayout(trans_style_row)

    language_layout.addWidget(trans_engine_card)

    language_page.layout().addWidget(language_card)

    voice_card, voice_layout = _build_collapsible_section("Voice")
    gui.voice_section_card = voice_card
    gui.voice_engine_combo = QComboBox()
    # Keep the legacy ``fast`` value for project compatibility; it now means
    # the offline Piper engine. Default to Piper as requested.
    gui.voice_engine_combo.addItem("Select TTS engine…", "")
    gui.voice_engine_combo.addItem("Piper [VI/EN] · Fast · Offline", "fast")
    gui.voice_engine_combo.addItem("Edge TTS [VI/EN] · Natural · Online", "edge")
    gui.voice_engine_combo.addItem("ZeroTTS [VI] · Natural · Not installed", "zerotts")
    gui.voice_engine_combo.addItem("KorvaTTS [VI/EN] · Natural / Local · Not installed", "korvatts")
    gui.voice_engine_combo.addItem("Kokoro-82M [EN] · Natural · Not installed", "kokoro")
    idx_piper = gui.voice_engine_combo.findData("fast")
    if idx_piper >= 0:
        gui.voice_engine_combo.setCurrentIndex(idx_piper)
    gui.voice_engine_combo.setToolTip(
        "Choose the engine explicitly. Edge TTS requires Internet; engines marked Not installed require their runtime/model."
    )
    gui.voice_language_label = QLabel("Output language follows Language → Translate to")
    gui.voice_language_label.setObjectName("helperLabel")
    gui.voice_language_label.setWordWrap(True)
    gui.free_voice_combo = QComboBox()
    gui.voice_gender_combo = QComboBox()
    gui.voice_gender_combo.addItems(["Any", "Male", "Female"])
    gui.voice_gender_combo.setCurrentText("Female")
    gui.voice_gender_combo.currentTextChanged.connect(gui.on_voice_gender_changed)

    gui.voice_speed_spin = QComboBox(gui)
    gui.voice_speed_spin.setEditable(True)
    gui.voice_speed_spin.addItems(["0.8x", "0.9x", "1.0x", "1.1x", "1.2x", "1.3x", "1.4x", "1.5x", "1.6x", "1.8x", "2.0x"])
    gui.voice_speed_spin.setCurrentText("1.0x")
    gui.voice_speed_spin.hide()
    gui.voice_timing_sync_combo = QComboBox()
    gui.voice_timing_sync_combo.addItems(["Off", "Smart", "Timeline Priority", "Force Fit"])
    gui.voice_timing_sync_combo.setCurrentText("Smart")

    def _sync_voice_speed_enabled(_value: str = ""):
        mode = gui.voice_timing_sync_combo.currentText().strip().lower()
        gui.voice_speed_spin.setEnabled(mode != "off")
    gui.voice_timing_sync_combo.currentTextChanged.connect(_sync_voice_speed_enabled)
    _sync_voice_speed_enabled()

    def _on_voice_timing_sync_changed(_value: str = ""):
        if hasattr(gui, "timeline") and gui.timeline is not None:
            gui.timeline.set_voice_sync_mode(gui.voice_timing_sync_combo.currentText())
    _on_voice_timing_sync_changed()
    # This is a media-generation policy, not an editor action. Keep it in
    # Media Workflow so the timeline toolbar stays focused on editing.
    media_workflow_card, media_workflow_layout = _build_collapsible_section("Media Workflow")
    source_card, source_layout = _section_card()
    source_header = QHBoxLayout()
    source_title = QLabel("SOURCE VIDEOS · V1")
    source_title.setObjectName("sectionTitle")
    gui.source_video_summary_label = QLabel("1 video")
    gui.source_video_summary_label.setObjectName("helperLabel")
    source_header.addWidget(source_title)
    source_header.addStretch(1)
    source_header.addWidget(gui.source_video_summary_label)
    source_layout.addLayout(source_header)
    source_hint = QLabel("Videos are placed back-to-back on V1. Generate uses this exact order and each clip's current trim.")
    source_hint.setObjectName("helperLabel")
    source_hint.setWordWrap(True)
    source_layout.addWidget(source_hint)
    gui.source_video_list = QListWidget()
    gui.source_video_list.setObjectName("sourceVideoList")
    gui.source_video_list.setMaximumHeight(118)
    gui.source_video_list.currentRowChanged.connect(gui._update_source_video_buttons)
    gui.source_video_list.itemClicked.connect(lambda _item: gui.select_source_video_in_timeline())
    gui.source_video_list.itemDoubleClicked.connect(lambda _item: gui.select_source_video_in_timeline())
    source_layout.addWidget(gui.source_video_list)
    source_buttons = QHBoxLayout()
    source_buttons.setSpacing(6)
    gui.add_video_btn = QPushButton("+ Add Video")
    gui.add_video_btn.setToolTip("Add one or more videos after the current V1 clips")
    gui.add_video_btn.clicked.connect(gui.add_videos_to_timeline)
    gui.source_video_up_btn = QPushButton("↑")
    gui.source_video_up_btn.setToolTip("Move selected video earlier")
    gui.source_video_up_btn.clicked.connect(lambda: gui.move_selected_source_video(-1))
    gui.source_video_down_btn = QPushButton("↓")
    gui.source_video_down_btn.setToolTip("Move selected video later")
    gui.source_video_down_btn.clicked.connect(lambda: gui.move_selected_source_video(1))
    gui.source_video_remove_btn = QPushButton("Remove")
    gui.source_video_remove_btn.clicked.connect(gui.remove_selected_source_video)
    source_buttons.addWidget(gui.add_video_btn, 1)
    source_buttons.addWidget(gui.source_video_up_btn)
    source_buttons.addWidget(gui.source_video_down_btn)
    source_buttons.addWidget(gui.source_video_remove_btn)
    source_layout.addLayout(source_buttons)
    media_workflow_layout.addWidget(source_card)
    timing_card, timing_layout = _section_card()
    timing_title = QLabel("Voice timing synchronization")
    timing_title.setObjectName("sectionTitle")
    timing_hint = QLabel("Controls how generated voice timing follows the subtitle timeline.")
    timing_hint.setObjectName("helperLabel")
    timing_hint.setWordWrap(True)
    timing_layout.addWidget(timing_title)
    timing_layout.addWidget(timing_hint)
    timing_layout.addWidget(gui.voice_timing_sync_combo)
    media_workflow_layout.addWidget(timing_card)
    media_layout.addWidget(media_workflow_card)
    gui.free_voice_combo.currentIndexChanged.connect(gui.on_selected_voice_changed)
    gui.voice_engine_combo.currentIndexChanged.connect(gui.on_voice_engine_changed)
    gui.preview_voice_btn = QPushButton("Preview Selected Voice")
    gui.preview_voice_btn.clicked.connect(gui.preview_selected_voice_sample)
    gui.manage_voice_engines_btn = QPushButton("Install / Manage Voice Engines")
    gui.manage_voice_engines_btn.setToolTip("Install the selected TTS runtime or manage local voice models.")
    gui.manage_voice_engines_btn.clicked.connect(gui.open_resource_manager_dialog)
    gui.voice_preview_meta_label = QLabel("Listen to a short sample before generating the full voice track.", gui)
    gui.voice_preview_meta_label.setObjectName("helperLabel")
    gui.voice_preview_meta_label.setWordWrap(True)
    gui.voice_preview_meta_label.hide()
    voice_setup_card, voice_setup_layout = _section_card()
    voice_setup_title = QLabel("Voice Setup")
    voice_setup_title.setObjectName("sectionTitle")
    voice_setup_layout.addWidget(voice_setup_title)
    voice_setup_layout.addWidget(gui.voice_language_label)
    voice_setup_layout.addWidget(QLabel("Voice engine"))
    voice_setup_layout.addWidget(gui.voice_engine_combo)
    gui.fast_voice_panel = QWidget()
    fast_voice_layout = QVBoxLayout(gui.fast_voice_panel)
    fast_voice_layout.setContentsMargins(0, 0, 0, 0)
    fast_voice_layout.setSpacing(8)
    gui.voice_choice_label = QLabel("Voice")
    fast_voice_layout.addWidget(gui.voice_choice_label)
    fast_voice_layout.addWidget(gui.free_voice_combo)
    fast_voice_layout.addWidget(QLabel("Voice type"))
    fast_voice_layout.addWidget(gui.voice_gender_combo)
    voice_setup_layout.addWidget(gui.fast_voice_panel)
    # Voice preview belongs to the global/default voice configuration.  It is
    # deliberately kept outside the per-speaker diarization controls below.
    voice_setup_layout.addWidget(gui.preview_voice_btn)
    voice_setup_layout.addWidget(gui.manage_voice_engines_btn)
    voice_setup_layout.addWidget(gui.voice_preview_meta_label)
    # These legacy tuning controls are retained for internal compatibility
    # after removing the Voice Tuning panel, but must never become orphaned
    # top-level widgets.
    gui.ai_dubbing_rewrite_cb = QCheckBox("Use AI Rewrite Dubbing for voice timing", gui)
    gui.ai_dubbing_rewrite_cb.setChecked(False)
    gui.ai_dubbing_rewrite_cb.hide()
    gui.ai_dubbing_rewrite_hint_label = QLabel(
        "Keeps subtitle text readable, but lets AI create a shorter spoken version for TTS when timing is tight.",
        gui,
    )
    gui.ai_dubbing_rewrite_hint_label.setObjectName("helperLabel")
    gui.ai_dubbing_rewrite_hint_label.setWordWrap(True)
    gui.ai_dubbing_rewrite_hint_label.hide()
    voice_layout.addWidget(voice_setup_card)

    gui.detected_speakers_card, detected_speakers_layout = _section_card()
    detected_speakers_title = QLabel("Detected Speakers")
    detected_speakers_title.setObjectName("sectionTitle")
    detected_speakers_layout.addWidget(detected_speakers_title)
    gui.detected_speakers_hint_label = QLabel(
        "Run Speaker Diarization to assign a dedicated voice to each detected speaker. "
        "Unassigned speakers use the default voice above."
    )
    gui.detected_speakers_hint_label.setObjectName("helperLabel")
    gui.detected_speakers_hint_label.setWordWrap(True)
    detected_speakers_layout.addWidget(gui.detected_speakers_hint_label)
    gui.detected_speakers_list = QWidget()
    gui.detected_speakers_list_layout = QVBoxLayout(gui.detected_speakers_list)
    gui.detected_speakers_list_layout.setContentsMargins(0, 0, 0, 0)
    gui.detected_speakers_list_layout.setSpacing(8)
    detected_speakers_layout.addWidget(gui.detected_speakers_list)
    gui.detected_speakers_card.hide()
    voice_layout.addWidget(gui.detected_speakers_card)

    voice_page.layout().addWidget(voice_card)

    subtitle_card, subtitle_layout = _build_collapsible_section("Subtitle Style", start_expanded=True)
    base_style_label = QLabel("Presets")
    base_style_label.setObjectName("sectionTitle")
    subtitle_layout.addWidget(base_style_label)
    gui.subtitle_preset_tiktok_radio = QRadioButton("TikTok")
    gui.subtitle_preset_youtube_radio = QRadioButton("YouTube")
    gui.subtitle_preset_minimal_radio = QRadioButton("Short")
    gui.subtitle_preset_custom_radio = QRadioButton("Custom")
    gui.subtitle_preset_youtube_radio.setChecked(True)
    gui.subtitle_preset_group = QButtonGroup(gui)
    gui.subtitle_preset_group.addButton(gui.subtitle_preset_tiktok_radio)
    gui.subtitle_preset_group.addButton(gui.subtitle_preset_youtube_radio)
    gui.subtitle_preset_group.addButton(gui.subtitle_preset_minimal_radio)
    gui.subtitle_preset_group.addButton(gui.subtitle_preset_custom_radio)

    preset_grid = QGridLayout()
    preset_grid.setContentsMargins(0, 0, 0, 0)
    preset_grid.setHorizontalSpacing(8)
    preset_grid.setVerticalSpacing(8)
    preset_grid.setColumnStretch(0, 1)
    preset_grid.setColumnStretch(1, 1)
    preset_grid.addWidget(_build_style_preset_card("TikTok", "TRENDING", "WORDS POP", gui.subtitle_preset_tiktok_radio), 0, 0)
    preset_grid.addWidget(_build_style_preset_card("YouTube", "Clean subtitle", "with solid box", gui.subtitle_preset_youtube_radio), 0, 1)
    preset_grid.addWidget(_build_style_preset_card("Short", "HELLO", "world", gui.subtitle_preset_minimal_radio), 1, 0)
    preset_grid.addWidget(_build_style_preset_card("Custom", "My", "style", gui.subtitle_preset_custom_radio), 1, 1)
    subtitle_layout.addLayout(preset_grid)

    style_library_card, style_library_layout = _section_card()
    style_library_title = QLabel("Saved Styles")
    style_library_title.setObjectName("sectionTitle")
    style_library_layout.addWidget(style_library_title)
    gui.save_subtitle_style_btn = QPushButton("+ Save This Style")
    gui.save_subtitle_style_btn.clicked.connect(gui.save_current_subtitle_style_preset)
    gui.saved_subtitle_style_combo = QComboBox()
    gui.saved_subtitle_style_combo.addItem("My Presets")
    gui.saved_subtitle_style_combo.currentIndexChanged.connect(gui.load_selected_subtitle_style_preset)
    style_library_layout.addWidget(gui.save_subtitle_style_btn)
    style_library_layout.addWidget(gui.saved_subtitle_style_combo)
    subtitle_layout.addWidget(style_library_card)
    gui.style_library_card = style_library_card

    highlight_card, highlight_card_layout = _build_collapsible_section("Keyword Highlight", start_expanded=False)
    gui.subtitle_keyword_highlight_cb = QCheckBox("Highlight key words")
    gui.subtitle_keyword_highlight_cb.setChecked(False)
    gui.subtitle_highlight_color_combo = QComboBox()
    gui.subtitle_highlight_color_combo.addItems(["Yellow", "Cyan", "Green", "Pink"])
    gui.subtitle_highlight_mode_combo = QComboBox()
    gui.subtitle_highlight_mode_combo.addItems(["Auto", "Manual", "Auto + Manual"])
    highlight_card_layout.addWidget(gui.subtitle_keyword_highlight_cb)

    highlight_color_row = QHBoxLayout()
    highlight_color_row.addWidget(QLabel("Color:"))
    highlight_color_row.addWidget(gui.subtitle_highlight_color_combo, 1)
    highlight_card_layout.addLayout(highlight_color_row)

    highlight_mode_row = QHBoxLayout()
    highlight_mode_row.addWidget(QLabel("Source:"))
    highlight_mode_row.addWidget(gui.subtitle_highlight_mode_combo, 1)
    highlight_card_layout.addLayout(highlight_mode_row)
    subtitle_layout.addWidget(highlight_card)
    gui.highlight_card = highlight_card

    position_card, position_layout = _build_collapsible_section("Text Position", start_expanded=False)
    position_wrapper = QFrame()
    position_wrapper.setObjectName("statusCard")
    position_wrapper_layout = QVBoxLayout(position_wrapper)
    position_wrapper_layout.setContentsMargins(12, 12, 12, 12)
    position_wrapper_layout.setSpacing(10)

    position_grid = QGridLayout()
    position_grid.setContentsMargins(0, 0, 0, 0)
    position_grid.setHorizontalSpacing(10)
    position_grid.setVerticalSpacing(8)

    gui.subtitle_position_mode_combo = QComboBox()
    gui.subtitle_position_mode_combo.addItem("Quick placement", "anchor")
    gui.subtitle_position_mode_combo.addItem("Custom X/Y", "custom")
    gui.subtitle_align_label = QLabel("Placement:")
    gui.subtitle_align_combo = QComboBox()
    gui.subtitle_align_combo.addItems(["Bottom", "Bottom Left", "Bottom Right", "Center", "Top"])
    gui.subtitle_align_combo.setCurrentText("Bottom")
    gui.subtitle_custom_x_label = QLabel("Custom X:")
    gui.subtitle_custom_x_spin = QSpinBox()
    gui.subtitle_custom_x_spin.setRange(0, 100)
    gui.subtitle_custom_x_spin.setValue(50)
    gui.subtitle_custom_x_spin.setSuffix(" %")
    gui.subtitle_custom_y_label = QLabel("Custom Y:")
    gui.subtitle_custom_y_spin = QSpinBox()
    gui.subtitle_custom_y_spin.setRange(0, 100)
    gui.subtitle_custom_y_spin.setValue(86)
    gui.subtitle_custom_y_spin.setSuffix(" %")
    gui.subtitle_bottom_offset_label = QLabel("Vertical Offset:")
    gui.subtitle_bottom_offset_spin = QSpinBox()
    gui.subtitle_bottom_offset_spin.setRange(0, 300)
    gui.subtitle_bottom_offset_spin.setValue(30)
    gui.subtitle_bottom_offset_spin.setSuffix(" px")

    position_grid.addWidget(QLabel("Placement mode:"), 0, 0)
    position_grid.addWidget(gui.subtitle_position_mode_combo, 0, 1)
    position_grid.addWidget(gui.subtitle_align_label, 1, 0)
    position_grid.addWidget(gui.subtitle_align_combo, 1, 1)
    position_grid.addWidget(gui.subtitle_custom_x_label, 2, 0)
    position_grid.addWidget(gui.subtitle_custom_x_spin, 2, 1)
    position_grid.addWidget(gui.subtitle_custom_y_label, 3, 0)
    position_grid.addWidget(gui.subtitle_custom_y_spin, 3, 1)
    position_grid.addWidget(gui.subtitle_bottom_offset_label, 4, 0)
    position_grid.addWidget(gui.subtitle_bottom_offset_spin, 4, 1)

    position_wrapper_layout.addLayout(position_grid)
    position_layout.addWidget(position_wrapper)
    subtitle_layout.addWidget(position_card)
    gui.subtitle_position_card = position_card

    timing_card, timing_layout = _build_collapsible_section("Animation", start_expanded=False)
    timing_wrapper = QFrame()
    timing_wrapper.setObjectName("statusCard")
    timing_wrapper_layout = QVBoxLayout(timing_wrapper)
    timing_wrapper_layout.setContentsMargins(12, 12, 12, 12)
    timing_wrapper_layout.setSpacing(10)

    timing_grid = QGridLayout()
    timing_grid.setContentsMargins(0, 0, 0, 0)
    timing_grid.setHorizontalSpacing(10)
    timing_grid.setVerticalSpacing(8)

    custom_title_card, custom_title_layout = _build_collapsible_section("Text Style", start_expanded=False)
    custom_wrapper = QFrame()
    custom_wrapper.setObjectName("statusCard")
    custom_wrapper_layout = QVBoxLayout(custom_wrapper)
    custom_wrapper_layout.setContentsMargins(12, 12, 12, 12)
    custom_wrapper_layout.setSpacing(10)
    gui.custom_settings_toggle_btn = QToolButton()
    gui.custom_settings_toggle_btn.setText("▼ Style Details")
    gui.custom_settings_toggle_btn.setCheckable(True)
    gui.custom_settings_toggle_btn.setChecked(True)
    gui.custom_settings_toggle_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    gui.custom_settings_toggle_btn.setStyleSheet("QToolButton { text-align: left; font-weight: 700; color: #dbe5f3; border: none; padding: 0; }")
    custom_wrapper_layout.addWidget(gui.custom_settings_toggle_btn)

    gui.custom_settings_content = QWidget()
    custom_controls_layout = QGridLayout(gui.custom_settings_content)
    custom_controls_layout.setContentsMargins(0, 0, 0, 0)
    custom_controls_layout.setHorizontalSpacing(10)
    custom_controls_layout.setVerticalSpacing(8)

    gui.subtitle_font_combo = QComboBox()
    gui.subtitle_font_combo.setEditable(True)
    gui.subtitle_font_combo.addItems(["Montserrat", "Roboto", "Inter", "Poppins", "Arial", "Segoe UI", "Tahoma", "Verdana", "Times New Roman"])
    gui.subtitle_font_combo.setCurrentText("Segoe UI")
    gui.subtitle_font_size_spin = QSpinBox()
    # Retained as the canonical source-video size for projects/export. The
    # percentage picker below is the user-facing control.
    gui.subtitle_font_size_spin.setRange(30, 90)
    gui.subtitle_font_size_spin.setValue(60)
    gui.subtitle_font_scale_combo = QComboBox()
    for percent in (50, 75, 100, 125, 150):
        gui.subtitle_font_scale_combo.addItem(f"{percent}%", percent)
    gui.subtitle_font_scale_combo.setCurrentIndex(2)
    gui.subtitle_color_btn = QPushButton("White")
    gui.subtitle_color_hex = "#FFFFFF"
    gui.subtitle_color_btn.clicked.connect(gui.choose_subtitle_color)
    gui.subtitle_background_color_btn = QPushButton("#000000")
    gui.subtitle_background_color_hex = "#000000"
    gui.subtitle_background_color_btn.clicked.connect(gui.choose_subtitle_background_color)
    gui.subtitle_background_cb = QCheckBox("Background Box")
    gui.subtitle_background_cb.setChecked(False)
    gui.subtitle_outline_cb = QCheckBox("Text Outline")
    gui.subtitle_outline_cb.setChecked(True)
    gui.subtitle_bold_cb = QCheckBox("Bold")
    gui.subtitle_bold_cb.setChecked(True)
    gui.subtitle_speaker_colors_cb = QCheckBox("Use speaker colors")
    gui.subtitle_speaker_colors_cb.setToolTip(
        "Use each diarized speaker's TS1 color for their subtitle text."
    )
    gui.subtitle_single_line_cb = QCheckBox("Single-line subtitle (Netflix)")
    gui.subtitle_single_line_cb.setChecked(False)
    gui.subtitle_animation_combo = QComboBox()
    gui.subtitle_animation_combo.addItems(
        ["Static", "Pop In", "Slide Up", "Fade In", "Fade Out", "Pulse", "Background Appear", "Typewriter", "Word Highlight Karaoke"]
    )
    gui.subtitle_animation_combo.setCurrentText("Pop In")
    gui.subtitle_animation_combo.currentTextChanged.connect(lambda _value: gui.on_subtitle_animation_changed())
    gui.subtitle_animation_time_spin = QDoubleSpinBox()
    gui.subtitle_animation_time_spin.setRange(0.1, 2.5)
    gui.subtitle_animation_time_spin.setSingleStep(0.05)
    gui.subtitle_animation_time_spin.setDecimals(2)
    gui.subtitle_animation_time_spin.setValue(0.22)
    gui.subtitle_animation_time_spin.setSuffix(" s")
    gui.subtitle_animation_time_label = QLabel("Duration")
    gui.subtitle_bg_alpha_spin = QDoubleSpinBox()
    gui.subtitle_bg_alpha_spin.setRange(0.0, 1.0)
    gui.subtitle_bg_alpha_spin.setSingleStep(0.05)
    gui.subtitle_bg_alpha_spin.setDecimals(2)
    gui.subtitle_bg_alpha_spin.setValue(0.6)
    gui.subtitle_bg_alpha_spin.setSuffix(" alpha")
    gui.subtitle_karaoke_timing_label = QLabel("Text Timing")
    gui.subtitle_karaoke_timing_combo = QComboBox()
    gui.subtitle_karaoke_timing_combo.addItem("Vietnamese pacing", "vietnamese")
    gui.subtitle_karaoke_timing_combo.addItem("Source speech timing", "source")
    gui.subtitle_karaoke_timing_combo.setCurrentIndex(0)
    gui.subtitle_karaoke_timing_combo.currentTextChanged.connect(lambda _value: gui.update_subtitle_preview_style())

    custom_controls_layout.addWidget(QLabel("Font:"), 0, 0)
    custom_controls_layout.addWidget(gui.subtitle_font_combo, 0, 1)
    custom_controls_layout.addWidget(QLabel("Size:"), 1, 0)
    custom_controls_layout.addWidget(gui.subtitle_font_scale_combo, 1, 1)
    custom_controls_layout.addWidget(QLabel("Text Color:"), 2, 0)
    custom_controls_layout.addWidget(gui.subtitle_color_btn, 2, 1)
    custom_controls_layout.addWidget(gui.subtitle_outline_cb, 3, 0)
    custom_controls_layout.addWidget(gui.subtitle_bold_cb, 3, 1)
    custom_controls_layout.addWidget(gui.subtitle_speaker_colors_cb, 4, 0, 1, 2)
    custom_wrapper_layout.addWidget(gui.custom_settings_content)
    custom_title_layout.addWidget(custom_wrapper)
    subtitle_layout.addWidget(custom_title_card)
    gui.custom_title_card = custom_title_card

    single_line_card, single_line_layout = _build_collapsible_section("Single Line Subtitle", start_expanded=False)
    single_line_wrapper = QFrame()
    single_line_wrapper.setObjectName("statusCard")
    single_line_grid = QGridLayout(single_line_wrapper)
    single_line_grid.setContentsMargins(12, 12, 12, 12)
    gui.subtitle_single_line_cb.setText("Enable Netflix-style single-line subtitles")
    gui.subtitle_words_per_segment_spin = QSpinBox()
    gui.subtitle_words_per_segment_spin.setRange(1, 20)
    gui.subtitle_words_per_segment_spin.setValue(4)
    gui.subtitle_words_per_segment_spin.setSuffix(" words")
    single_line_grid.addWidget(gui.subtitle_single_line_cb, 0, 0, 1, 2)
    single_line_grid.addWidget(QLabel("Words per segment:"), 1, 0)
    single_line_grid.addWidget(gui.subtitle_words_per_segment_spin, 1, 1)
    single_line_layout.addWidget(single_line_wrapper)
    subtitle_layout.addWidget(single_line_card)

    background_card, background_layout = _build_collapsible_section("Background", start_expanded=False)
    background_wrapper = QFrame()
    background_wrapper.setObjectName("statusCard")
    background_wrapper_layout = QGridLayout(background_wrapper)
    background_wrapper_layout.setContentsMargins(12, 12, 12, 12)
    background_wrapper_layout.setHorizontalSpacing(10)
    background_wrapper_layout.setVerticalSpacing(8)
    background_wrapper_layout.addWidget(gui.subtitle_background_cb, 0, 0, 1, 2)
    gui.subtitle_background_width_combo = QComboBox()
    gui.subtitle_background_width_combo.addItem("Fit Text (per line)", "fit_text")
    gui.subtitle_background_width_combo.addItem("Full Subtitle Block (Exact)", "full_area")
    gui.subtitle_background_width_combo.setToolTip(
        "Fit Text is the fast default and wraps each subtitle line.\n"
        "Full Subtitle Block is an advanced exact-layout option; it measures libass after editing settles."
    )
    background_wrapper_layout.addWidget(QLabel("Width:"), 1, 0)
    background_wrapper_layout.addWidget(gui.subtitle_background_width_combo, 1, 1)
    gui.subtitle_background_exact_hint = QLabel(
        "Exact layout updates after editing stops. Fit Text is recommended for fastest editing."
    )
    gui.subtitle_background_exact_hint.setObjectName("subtleHint")
    gui.subtitle_background_exact_hint.setWordWrap(True)
    gui.subtitle_background_exact_hint.setVisible(False)
    background_wrapper_layout.addWidget(gui.subtitle_background_exact_hint, 2, 0, 1, 2)
    gui.subtitle_background_shape_label = QLabel("Shape:")
    gui.subtitle_background_shape_combo = QComboBox()
    gui.subtitle_background_shape_combo.addItem("Rectangle", "rectangle")
    gui.subtitle_background_shape_combo.setToolTip("Subtitle background shape.")
    gui.subtitle_background_shape_label.setVisible(False)
    gui.subtitle_background_shape_combo.setVisible(False)
    background_wrapper_layout.addWidget(gui.subtitle_background_shape_label, 3, 0)
    background_wrapper_layout.addWidget(gui.subtitle_background_shape_combo, 3, 1)
    gui.subtitle_background_padding_spin = QSpinBox()
    gui.subtitle_background_padding_spin.setRange(0, 30)
    gui.subtitle_background_padding_spin.setValue(6)
    gui.subtitle_background_padding_spin.setSuffix(" px")
    background_wrapper_layout.addWidget(QLabel("Padding:"), 4, 0)
    background_wrapper_layout.addWidget(gui.subtitle_background_padding_spin, 4, 1)
    gui.subtitle_background_radius_spin = QSpinBox()
    gui.subtitle_background_radius_spin.setRange(0, 80)
    gui.subtitle_background_radius_spin.setValue(0)
    gui.subtitle_background_radius_spin.setSuffix(" px")
    gui.subtitle_background_radius_spin.setToolTip("Round the subtitle background corners.")
    background_wrapper_layout.addWidget(QLabel("Corner radius:"), 5, 0)
    background_wrapper_layout.addWidget(gui.subtitle_background_radius_spin, 5, 1)
    background_wrapper_layout.addWidget(QLabel("Color:"), 6, 0)
    background_wrapper_layout.addWidget(gui.subtitle_background_color_btn, 6, 1)
    background_wrapper_layout.addWidget(QLabel("Opacity:"), 7, 0)
    background_wrapper_layout.addWidget(gui.subtitle_bg_alpha_spin, 7, 1)
    background_layout.addWidget(background_wrapper)
    subtitle_layout.addWidget(background_card)
    gui.subtitle_background_card = background_card

    timing_grid.addWidget(QLabel("Animation:"), 0, 0)
    timing_grid.addWidget(gui.subtitle_animation_combo, 0, 1)
    timing_grid.addWidget(gui.subtitle_animation_time_label, 1, 0)
    timing_grid.addWidget(gui.subtitle_animation_time_spin, 1, 1)
    timing_grid.addWidget(gui.subtitle_karaoke_timing_label, 2, 0)
    timing_grid.addWidget(gui.subtitle_karaoke_timing_combo, 2, 1)

    timing_wrapper_layout.addLayout(timing_grid)
    timing_layout.addWidget(timing_wrapper)
    subtitle_layout.addWidget(timing_card)
    gui.subtitle_timing_card = timing_card

    gui.subtitle_preset_summary_label = QLabel()
    gui.subtitle_preset_summary_label.setObjectName("helperLabel")
    gui.subtitle_preset_summary_label.setWordWrap(True)
    gui.subtitle_preset_summary_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    gui.subtitle_preset_summary_label.setTextInteractionFlags(Qt.NoTextInteraction)
    subtitle_layout.addWidget(gui.subtitle_preset_summary_label)

    gui.subtitle_x_offset_spin = QSpinBox()
    gui.subtitle_x_offset_spin.setRange(-400, 400)
    gui.subtitle_x_offset_spin.setValue(0)
    gui.subtitle_x_offset_spin.hide()

    def _toggle_custom_section(checked: bool):
        gui.custom_settings_toggle_btn.setText(("▼ " if checked else "▶ ") + "Style Details")
        gui.custom_settings_content.setVisible(checked)

    gui.custom_settings_toggle_btn.toggled.connect(_toggle_custom_section)
    style_page.layout().addWidget(subtitle_card)

    audio_mix_card, audio_mix_layout = _build_collapsible_section("Audio Mix", start_expanded=True)
    audio_mix_inner_card, audio_mix_inner_layout = _section_card()
    audio_mix_title = QLabel("Mix Style")
    audio_mix_title.setObjectName("sectionTitle")
    audio_mix_inner_layout.addWidget(audio_mix_title)
    gui.audio_mix_preset_combo = QComboBox()
    gui.audio_mix_preset_combo.addItem("Original Only", "original_only")
    gui.audio_mix_preset_combo.addItem("Prefer Original", "prefer_original")
    gui.audio_mix_preset_combo.addItem("Balanced", "balanced")
    gui.audio_mix_preset_combo.addItem("Prefer Dub", "prefer_dub")
    gui.audio_mix_preset_combo.addItem("Dub Only", "dub_only")
    gui.audio_mix_preset_combo.addItem("Custom", "custom")
    gui.audio_mix_preset_combo.setCurrentIndex(2)
    audio_mix_inner_layout.addWidget(gui.audio_mix_preset_combo)
    gui.audio_mix_preset_hint_label = QLabel("Presets set both track volumes. Manual adjustment switches to Custom.", gui)
    gui.audio_mix_preset_hint_label.setObjectName("helperLabel")
    gui.audio_mix_preset_hint_label.setWordWrap(True)
    audio_mix_inner_layout.addWidget(gui.audio_mix_preset_hint_label)
    audio_mix_layout.addWidget(audio_mix_inner_card)

    audio_tracks_card, audio_tracks_layout = _section_card()
    tracks_title = QLabel("Track Volumes")
    tracks_title.setObjectName("sectionTitle")
    audio_tracks_layout.addWidget(tracks_title)

    a1_row = QHBoxLayout()
    a1_label = QLabel("A1 Original")
    a1_label.setMinimumWidth(100)
    a1_row.addWidget(a1_label)
    gui.audio_a1_volume_slider = QSlider(Qt.Horizontal)
    gui.audio_a1_volume_slider.setMinimum(0)
    gui.audio_a1_volume_slider.setMaximum(200)
    gui.audio_a1_volume_slider.setValue(50)
    gui.audio_a1_volume_slider.setTickInterval(50)
    gui.audio_a1_volume_slider.setTickPosition(QSlider.TicksBelow)
    a1_row.addWidget(gui.audio_a1_volume_slider, 1)
    gui.audio_a1_volume_label = QLabel("50%")
    gui.audio_a1_volume_label.setObjectName("helperLabel")
    gui.audio_a1_volume_label.setMinimumWidth(40)
    gui.audio_a1_volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    a1_row.addWidget(gui.audio_a1_volume_label)
    audio_tracks_layout.addLayout(a1_row)

    a2_row = QHBoxLayout()
    a2_label = QLabel("A2 Dub")
    a2_label.setMinimumWidth(100)
    a2_row.addWidget(a2_label)
    gui.audio_a2_volume_slider = QSlider(Qt.Horizontal)
    gui.audio_a2_volume_slider.setMinimum(0)
    gui.audio_a2_volume_slider.setMaximum(200)
    gui.audio_a2_volume_slider.setValue(100)
    gui.audio_a2_volume_slider.setTickInterval(50)
    gui.audio_a2_volume_slider.setTickPosition(QSlider.TicksBelow)
    a2_row.addWidget(gui.audio_a2_volume_slider, 1)
    gui.audio_a2_volume_label = QLabel("100%")
    gui.audio_a2_volume_label.setObjectName("helperLabel")
    gui.audio_a2_volume_label.setMinimumWidth(40)
    gui.audio_a2_volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    a2_row.addWidget(gui.audio_a2_volume_label)
    audio_tracks_layout.addLayout(a2_row)

    audio_mix_layout.addWidget(audio_tracks_card)

    separation_card, separation_layout = _section_card()
    separation_layout.addWidget(QLabel("Voice / Music Separation"), 0)
    separation_hint = QLabel(
        "Separate audio with the installed local model. Choose a stem, then add Voice.wav or Music.wav to the timeline."
    )
    separation_hint.setObjectName("helperLabel")
    separation_hint.setWordWrap(True)
    separation_layout.addWidget(separation_hint)
    gui.audio_separation_mode_combo = QComboBox()
    gui.audio_separation_mode_combo.addItem("Keep music, remove voice", "music")
    gui.audio_separation_mode_combo.addItem("Keep voice, remove music", "voice")
    gui.audio_separation_mode_combo.addItem("Create both Voice.wav + Music.wav", "both")
    gui.audio_separation_mode_combo.setCurrentIndex(2)
    separation_layout.addWidget(gui.audio_separation_mode_combo)
    gui.audio_separation_btn = QPushButton("Separate Voice and Music")
    separation_layout.addWidget(gui.audio_separation_btn)
    stem_buttons = QHBoxLayout()
    gui.add_music_stem_btn = QPushButton("Add Music.wav to timeline")
    gui.add_voice_stem_btn = QPushButton("Add Voice.wav to timeline")
    gui.add_music_stem_btn.setEnabled(False)
    gui.add_voice_stem_btn.setEnabled(False)
    stem_buttons.addWidget(gui.add_music_stem_btn)
    stem_buttons.addWidget(gui.add_voice_stem_btn)
    separation_layout.addLayout(stem_buttons)
    gui.audio_stem_status_label = QLabel("No separated stems yet")
    gui.audio_stem_status_label.setObjectName("helperLabel")
    gui.audio_stem_status_label.setWordWrap(True)
    separation_layout.addWidget(gui.audio_stem_status_label)

    for title, attr, default in (("Music volume", "audio_music_volume_slider", 100), ("Voice volume", "audio_voice_volume_slider", 100)):
        row = QHBoxLayout()
        row.addWidget(QLabel(title))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 200)
        slider.setValue(default)
        slider.setTickInterval(50)
        setattr(gui, attr, slider)
        row.addWidget(slider, 1)
        label = QLabel(f"{default}%")
        label.setObjectName("helperLabel")
        label.setMinimumWidth(40)
        label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        setattr(gui, attr.replace("_slider", "_label"), label)
        row.addWidget(label)
        separation_layout.addLayout(row)

    audio_mix_layout.addWidget(separation_card)
    audio_page.layout().addWidget(audio_mix_card)

    for page in pages:
        page.layout().addStretch()
        gui.left_panel_stack.addWidget(page)

    workflow_shell_layout.addWidget(gui.left_panel_stack, 1)
    left_layout.addWidget(workflow_shell)


def build_workflow_group(left_layout):
    return None







