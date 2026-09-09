import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .advanced_tabs import build_advanced_group
from .preview_panel import build_preview_panel
from .start_panel import build_start_group


class _TitleBar(QFrame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_pos = None

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)


def build_main_window_ui(gui):
    central_widget = QWidget()
    central_widget.setObjectName("centralWidget")
    gui.setCentralWidget(central_widget)
    root_layout = QVBoxLayout(central_widget)
    root_layout.setContentsMargins(10, 10, 10, 10)
    root_layout.setSpacing(10)
    gui.root_layout = root_layout

    scroll_area = _build_left_panel(gui)

    # New cockpit shell: workflow navigation is persistent on the rail and
    # the command header/media workspace share one visual column. The legacy
    # stacked pages remain the state source so controllers and shortcuts are
    # unchanged.
    workspace_layout = QVBoxLayout()
    workspace_layout.setContentsMargins(0, 0, 0, 0)
    workspace_layout.setSpacing(12)
    workspace_layout.addWidget(_build_header_bar(gui))

    content_layout = QHBoxLayout()
    content_layout.setSpacing(10)
    gui.content_layout = content_layout
    right_panel = build_preview_panel(gui)

    content_layout.addWidget(scroll_area)
    content_layout.addWidget(right_panel, 1)
    gui.right_panel = right_panel
    workspace_layout.addLayout(content_layout, 1)

    from widgets.progress_dialog import MiniProgressStatusBar
    gui.mini_status_bar = MiniProgressStatusBar(gui)
    workspace_layout.addWidget(gui.mini_status_bar)

    body_layout = QHBoxLayout()
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(14)
    body_layout.addWidget(_build_navigation_rail(gui))
    body_layout.addLayout(workspace_layout, 1)
    root_layout.addLayout(body_layout, 1)

    _connect_ui_signals(gui)
    if hasattr(gui, "left_panel_stack"):
        gui.left_panel_stack.currentChanged.connect(gui.sync_runtime_log_view)
        gui.left_panel_stack.currentChanged.connect(lambda index: _sync_navigation_selection(gui, index))
    _initialize_ui_state(gui)
    QTimer.singleShot(0, gui.sync_left_panel_container_width)
    QTimer.singleShot(0, gui.sync_runtime_log_view)
    # Configure the static responsive profile before the editor is shown.
    # The first show event only finalizes geometry that Qt cannot know until
    # the window has a real viewport.
    gui.prepare_responsive_layout()


def _build_navigation_rail(gui):
    """Build the persistent workflow rail for the redesigned editor shell.

    Buttons proxy the existing ``left_panel_stack`` rather than introducing a
    second navigation state machine. This preserves page locks, shortcuts and
    controller behaviour while making the production flow explicit.
    """
    rail = QFrame()
    rail.setObjectName("navigationRail")
    rail.setFixedWidth(92)
    rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
    layout = QVBoxLayout(rail)
    layout.setContentsMargins(8, 14, 8, 12)
    layout.setSpacing(8)

    mark = QLabel("V")
    mark.setObjectName("navigationMark")
    mark.setAlignment(Qt.AlignCenter)
    mark.setFixedSize(44, 44)
    layout.addWidget(mark, 0, Qt.AlignHCenter)

    brand = QLabel("VIU\nSTUDIO")
    brand.setObjectName("navigationBrand")
    brand.setAlignment(Qt.AlignCenter)
    layout.addWidget(brand, 0, Qt.AlignHCenter)

    divider = QFrame()
    divider.setObjectName("navigationDivider")
    divider.setFrameShape(QFrame.HLine)
    divider.setFixedHeight(1)
    divider.setFixedWidth(70)
    layout.addWidget(divider, 0, Qt.AlignHCenter)

    nav_group = QButtonGroup(rail)
    nav_group.setExclusive(True)
    navigation = (
        ("01", "Source", 0),
        ("02", "Audio", 1),
        ("03", "Captions", 2),
        ("04", "Voice", 3),
        ("05", "Style", 4),
        ("06", "Advanced", 5),
    )
    gui.navigation_buttons = {}
    for number, label, page_index in navigation:
        button = QToolButton(rail)
        button.setObjectName("navigationButton")
        button.setText(f"{number}\n{label}")
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedSize(70, 52)
        button.setToolTip(f"Open {label} controls")
        nav_group.addButton(button)
        layout.addWidget(button, 0, Qt.AlignHCenter)
        key = label.lower()
        gui.navigation_buttons[key] = button

        def _select_page(_checked=False, index=page_index, key=key):
            legacy_key = {"source": "media", "captions": "language"}.get(key, key)
            legacy = getattr(gui, "workflow_tab_buttons", {}).get(legacy_key)
            if legacy is not None and not legacy.isEnabled():
                _sync_navigation_selection(gui, gui.left_panel_stack.currentIndex())
                return
            stack = getattr(gui, "left_panel_stack", None)
            if stack is not None:
                stack.setCurrentIndex(index)
            if legacy is not None and not legacy.isChecked():
                legacy.setChecked(True)

        button.clicked.connect(_select_page)

    layout.addStretch(1)
    progress_button = QToolButton(rail)
    progress_button.setObjectName("navigationUtilityButton")
    progress_button.setText("◎\nProgress")
    progress_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    progress_button.setAutoRaise(True)
    progress_button.setCursor(Qt.PointingHandCursor)
    progress_button.setFixedSize(70, 44)
    progress_button.setToolTip("Show active pipeline progress")
    progress_button.clicked.connect(gui.show_active_progress_dialog)
    layout.addWidget(progress_button, 0, Qt.AlignHCenter)

    project_button = QToolButton(rail)
    project_button.setObjectName("navigationUtilityButton")
    project_button.setText("📁\nProjects")
    project_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    project_button.setAutoRaise(True)
    project_button.setCursor(Qt.PointingHandCursor)
    project_button.setFixedSize(70, 44)
    project_button.setToolTip("Return to Projects")
    project_button.clicked.connect(lambda: getattr(gui, "header_home_btn", None).click())
    layout.addWidget(project_button, 0, Qt.AlignHCenter)

    settings_button = QToolButton(rail)
    settings_button.setObjectName("navigationUtilityButton")
    settings_button.setText("⚙\nSettings")
    settings_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
    settings_button.setAutoRaise(True)
    settings_button.setCursor(Qt.PointingHandCursor)
    settings_button.setFixedSize(70, 44)
    settings_button.setToolTip("Open application settings")
    settings_button.clicked.connect(gui.open_model_settings_dialog)
    layout.addWidget(settings_button, 0, Qt.AlignHCenter)

    gui.navigation_group = nav_group
    gui.navigation_buttons["source"].setChecked(True)
    return rail


def _sync_navigation_selection(gui, index: int):
    """Reflect stack changes made by legacy workflow code on the rail."""
    order = ("source", "audio", "captions", "voice", "style", "advanced")
    for position, key in enumerate(order):
        button = getattr(gui, "navigation_buttons", {}).get(key)
        if button is not None:
            button.setChecked(position == int(index))


def _build_header_bar(gui):
    header = _TitleBar()
    header.setObjectName("commandHeader")
    layout = QHBoxLayout(header)
    layout.setContentsMargins(14, 8, 14, 8)
    layout.setSpacing(10)
    gui.header_bar = header
    gui.header_layout = layout

    logo_label = QLabel()
    logo_label.setFixedSize(30, 30)
    logo_label.setAlignment(Qt.AlignCenter)
    if os.path.exists(getattr(gui, "logo_path", "")):
        logo_pixmap = QPixmap(gui.logo_path)
        if not logo_pixmap.isNull():
            logo_label.setPixmap(logo_pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    layout.addWidget(logo_label)
    gui.header_logo_label = logo_label

    brand_label = QLabel("VIUStudio")
    brand_label.setObjectName("heroTitle")
    brand_label.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: 700;")
    layout.addWidget(brand_label)
    gui.header_brand_label = brand_label

    gui.header_context_label = QLabel("EDITOR / WORKSPACE")
    gui.header_context_label.setObjectName("commandContext")
    layout.addWidget(gui.header_context_label)

    gui.project_title_label = QLabel("Project: No video selected")
    gui.project_title_label.setObjectName("commandProject")
    layout.addWidget(gui.project_title_label, 1)

    gui.run_all_btn.setFixedSize(132, 40)
    gui.run_all_btn.setCursor(Qt.PointingHandCursor)
    layout.addWidget(gui.run_all_btn)

    gui.export_btn.setObjectName("headerActionBtn")
    gui.export_btn.setProperty("accent", True)
    gui.export_btn.setFixedSize(92, 40)
    gui.export_btn.setCursor(Qt.PointingHandCursor)
    layout.addWidget(gui.export_btn)

    gui.preview_5s_btn.setObjectName("headerActionBtn")
    gui.preview_5s_btn.setFixedSize(124, 40)
    gui.preview_5s_btn.setCursor(Qt.PointingHandCursor)
    gui.preview_5s_btn.setToolTip("Render five seconds with final export subtitle styling")
    layout.addWidget(gui.preview_5s_btn)

    gui.toggle_panel_btn = QPushButton("Control")
    gui.toggle_panel_btn.setObjectName("secondaryActionBtn")
    gui.toggle_panel_btn.setMinimumHeight(36)
    gui.toggle_panel_btn.setMinimumWidth(80)
    gui.toggle_panel_btn.setToolTip("Toggle side panel")
    gui.toggle_panel_btn.setText("Controls")
    gui.toggle_panel_btn.clicked.connect(gui.toggle_controls_panel)
    # Hide the toggle button - the workflow panel is always visible.
    gui.toggle_panel_btn.setVisible(False)
    layout.addWidget(gui.toggle_panel_btn)

    gui.more_actions_btn = QPushButton("More")
    gui.more_actions_btn.setObjectName("headerMenuBtn")
    gui.more_actions_btn.setFixedSize(86, 40)
    gui.more_actions_btn.setCursor(Qt.PointingHandCursor)
    more_menu = QMenu(gui.more_actions_btn)
    more_menu.setObjectName("headerMoreMenu")

    gui.import_subtitle_action = more_menu.addAction("Import Translated SRT…")
    gui.import_subtitle_action.triggered.connect(gui.import_translated_srt)
    gui.import_original_action = more_menu.addAction("Import Source SRT…")
    gui.import_original_action.triggered.connect(gui.import_original_srt)
    gui.download_subtitle_action = more_menu.addAction("Export Translated SRT…")
    gui.download_subtitle_action.triggered.connect(gui.download_subtitle)
    gui.download_original_action = more_menu.addAction("Export Source SRT…")
    gui.download_original_action.triggered.connect(gui.download_original_script)
    gui.export_voice_action = more_menu.addAction("Export Voice Audio (MP3)…")
    gui.export_voice_action.triggered.connect(gui.export_voice_audio)
    gui.preview_5s_action = more_menu.addAction("Fast Preview (5 seconds)")
    gui.preview_5s_action.triggered.connect(gui.preview_5s_btn.click)
    more_menu.addSeparator()
    gui.rename_project_action = more_menu.addAction("Rename Project…")
    gui.rename_project_action.triggered.connect(gui.rename_current_project)
    gui.clean_project_action = more_menu.addAction("Clean")
    gui.clean_project_action.triggered.connect(gui.clean_current_project)
    gui.exit_project_action = more_menu.addAction("Exit")
    gui.exit_project_action.triggered.connect(gui.exit_to_launcher)
    gui.settings_action = more_menu.addAction("Settings")
    gui.settings_action.triggered.connect(gui.open_model_settings_dialog)
    gui.normalizer_dict_action = more_menu.addAction("Normalizer Dictionary")
    gui.normalizer_dict_action.triggered.connect(gui.open_normalizer_dict_dialog)
    gui.auto_recap_action = more_menu.addAction("⚡ Auto Edit Recap Settings")
    if hasattr(gui, "open_auto_recap_settings_dialog"):
        gui.auto_recap_action.triggered.connect(gui.open_auto_recap_settings_dialog)
    gui.check_updates_action = more_menu.addAction("🔄 Check for Updates…")
    if hasattr(gui, "check_for_updates"):
        gui.check_updates_action.triggered.connect(lambda: gui.check_for_updates(verbose=True))
    gui.more_actions_btn.setMenu(more_menu)

    gui.header_home_btn = QPushButton("Projects")
    gui.header_home_btn.setObjectName("headerNavBtn")
    gui.header_home_btn.setFixedSize(96, 40)
    gui.header_home_btn.setCursor(Qt.PointingHandCursor)
    gui.header_home_btn.setToolTip("Return to Projects Launcher")
    gui.header_home_btn.clicked.connect(gui.exit_to_launcher)
    layout.addWidget(gui.header_home_btn)

    layout.addWidget(gui.more_actions_btn)
    layout.addSpacing(4)

    gui.titlebar_min_btn = QPushButton("—")
    gui.titlebar_min_btn.setObjectName("titleBarButton")
    gui.titlebar_min_btn.setFixedSize(36, 36)
    gui.titlebar_min_btn.setToolTip("Minimize")
    gui.titlebar_min_btn.setCursor(Qt.PointingHandCursor)
    gui.titlebar_min_btn.clicked.connect(gui.showMinimized)
    layout.addWidget(gui.titlebar_min_btn)

    window_is_maximized = bool(gui.windowState() & Qt.WindowMaximized)
    gui.titlebar_max_btn = QPushButton("❐" if window_is_maximized else "□")
    gui.titlebar_max_btn.setObjectName("titleBarButton")
    gui.titlebar_max_btn.setFixedSize(36, 36)
    gui.titlebar_max_btn.setToolTip("Restore" if window_is_maximized else "Maximize")
    gui.titlebar_max_btn.setAccessibleName("Maximize or restore window")
    gui.titlebar_max_btn.setCursor(Qt.PointingHandCursor)
    gui.titlebar_max_btn.clicked.connect(lambda: _toggle_window_maximized(gui))
    layout.addWidget(gui.titlebar_max_btn)

    gui.titlebar_close_btn = QPushButton("✕")
    gui.titlebar_close_btn.setObjectName("titleBarCloseButton")
    gui.titlebar_close_btn.setFixedSize(36, 36)
    gui.titlebar_close_btn.setToolTip("Close Project and Return to Launcher")
    gui.titlebar_close_btn.setCursor(Qt.PointingHandCursor)
    gui.titlebar_close_btn.clicked.connect(gui.exit_to_launcher)
    layout.addWidget(gui.titlebar_close_btn)
    return header


def _toggle_window_maximized(gui):
    """Toggle only the native window state; editor/project state is untouched."""
    is_maximized = bool(gui.windowState() & Qt.WindowMaximized) or gui.isMaximized()
    if is_maximized:
        restore_geometry = getattr(gui, "_titlebar_restore_geometry", None)
        gui.showNormal()
        if restore_geometry is not None and restore_geometry.isValid():
            gui.setGeometry(restore_geometry)
        else:
            # The initial responsive-layout pass intentionally sizes the
            # hidden maximized window to the whole available screen. Qt can
            # then retain that as normalGeometry(), making showNormal() look
            # as if it did nothing. Give the first restore a real centered
            # window; subsequent maximize clicks remember the user's size.
            screen = gui.screen()
            available = screen.availableGeometry() if screen is not None else None
            if available is not None and available.isValid():
                width = max(gui.minimumWidth(), int(available.width() * 0.84))
                height = max(gui.minimumHeight(), int(available.height() * 0.84))
                width = min(width, available.width())
                height = min(height, available.height())
                left = available.left() + (available.width() - width) // 2
                top = available.top() + (available.height() - height) // 2
                gui.setGeometry(left, top, width, height)
        gui.titlebar_max_btn.setText("□")
        gui.titlebar_max_btn.setToolTip("Maximize")
    else:
        gui._titlebar_restore_geometry = gui.geometry()
        gui.showMaximized()
        gui.titlebar_max_btn.setText("❐")
        gui.titlebar_max_btn.setToolTip("Restore")


def _tint_pixmap(pixmap: QPixmap, color: QColor) -> QPixmap:
    image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    tinted = QImage(image.size(), QImage.Format_ARGB32)
    tinted.fill(Qt.transparent)

    for y in range(image.height()):
        for x in range(image.width()):
            pixel = image.pixelColor(x, y)
            alpha = pixel.alpha()
            if alpha <= 0:
                continue
            pixel.setRed(color.red())
            pixel.setGreen(color.green())
            pixel.setBlue(color.blue())
            pixel.setAlpha(alpha)
            tinted.setPixelColor(x, y, pixel)
    return QPixmap.fromImage(tinted)


def _build_left_panel(gui):
    scroll_area = QScrollArea()
    gui.left_panel_scroll_area = scroll_area
    scroll_area.setObjectName("leftPanelArea")
    scroll_area.setWidgetResizable(True)
    scroll_area.setFixedWidth(380)
    scroll_area.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll_area.setFrameShape(QFrame.NoFrame)

    left_panel_container = QWidget()
    left_panel_container.setObjectName("leftPanelContainer")
    gui.left_panel_container = left_panel_container
    left_layout = QVBoxLayout(left_panel_container)
    left_layout.setContentsMargins(8, 0, 8, 0)
    left_layout.setSpacing(10)
    scroll_area.setWidget(left_panel_container)
    scroll_area.installEventFilter(gui)
    scroll_area.viewport().installEventFilter(gui)
    scroll_area.verticalScrollBar().installEventFilter(gui)

    build_start_group(gui, left_layout)
    build_advanced_group(gui, left_layout)
    return scroll_area


def _connect_ui_signals(gui):
    gui.extract_btn.clicked.connect(gui.run_extraction)
    gui.vocal_sep_btn.clicked.connect(gui.run_vocal_separation)
    if hasattr(gui, "audio_separation_btn"):
        gui.audio_separation_btn.clicked.connect(gui.run_vocal_separation)
    if hasattr(gui, "add_music_stem_btn"):
        gui.add_music_stem_btn.clicked.connect(gui.add_music_stem_to_timeline)
    if hasattr(gui, "add_voice_stem_btn"):
        gui.add_voice_stem_btn.clicked.connect(gui.add_voice_stem_to_timeline)
    if hasattr(gui, "audio_music_volume_slider"):
        gui.audio_music_volume_slider.valueChanged.connect(gui.on_audio_music_volume_changed)
    if hasattr(gui, "audio_voice_volume_slider"):
        gui.audio_voice_volume_slider.valueChanged.connect(gui.on_audio_voice_volume_changed)
    gui.transcribe_btn.clicked.connect(gui.run_transcription)
    gui.import_original_srt_btn.clicked.connect(gui.import_original_srt)
    gui.translate_btn.clicked.connect(gui.run_translation)
    gui.rewrite_translation_btn.clicked.connect(gui.run_rewrite_translation)
    gui.import_translation_btn.clicked.connect(gui.import_translated_srt)
    gui.preview_btn.clicked.connect(gui.preview_video)
    if hasattr(gui, "reset_framing_btn"):
        gui.reset_framing_btn.clicked.connect(gui.reset_preview_framing)
    if hasattr(gui, "left_panel_stack"):
        gui.left_panel_stack.currentChanged.connect(gui.on_left_panel_workflow_changed)
    gui.output_mode_combo.currentTextChanged.connect(gui.on_output_mode_changed)
    if hasattr(gui, "output_quality_combo"):
        gui.output_quality_combo.currentIndexChanged.connect(gui.refresh_ui_state)
    gui.audio_handling_combo.currentTextChanged.connect(gui.refresh_ui_state)
    if hasattr(gui, "audio_mix_preset_combo"):
        gui.audio_mix_preset_combo.currentIndexChanged.connect(
            gui.on_audio_mix_preset_changed
        )
    if hasattr(gui, "audio_a1_volume_slider"):
        gui.audio_a1_volume_slider.valueChanged.connect(
            gui.on_audio_a1_volume_changed
        )
    if hasattr(gui, "audio_a2_volume_slider"):
        gui.audio_a2_volume_slider.valueChanged.connect(
            gui.on_audio_a2_volume_changed
        )
    if hasattr(gui, "audio_inspector_gain_spin"):
        gui.audio_inspector_gain_spin.valueChanged.connect(
            gui.on_audio_inspector_gain_changed
        )
    if hasattr(gui, "audio_inspector_speed_spin"):
        gui.audio_inspector_speed_spin.valueChanged.connect(
            gui.on_audio_inspector_speed_changed
        )
    if hasattr(gui, "audio_inspector_fade_in_spin"):
        gui.audio_inspector_fade_in_spin.valueChanged.connect(
            gui.on_audio_inspector_fade_in_changed
        )
    if hasattr(gui, "audio_inspector_fade_out_spin"):
        gui.audio_inspector_fade_out_spin.valueChanged.connect(
            gui.on_audio_inspector_fade_out_changed
        )
    if hasattr(gui, "audio_inspector_mute_btn"):
        gui.audio_inspector_mute_btn.toggled.connect(
            gui.on_audio_inspector_mute_toggled
        )
    if hasattr(gui, "audio_inspector_solo_btn"):
        gui.audio_inspector_solo_btn.toggled.connect(
            gui.on_audio_inspector_solo_toggled
        )
    if hasattr(gui, "audio_inspector_regenerate_voice_btn"):
        gui.audio_inspector_regenerate_voice_btn.clicked.connect(
            gui.on_audio_inspector_regenerate_voice_clicked
        )
    if hasattr(gui, "blur_inspector_show_cb"):
        gui.blur_inspector_show_cb.toggled.connect(
            gui.on_blur_inspector_show_toggled
        )
    if hasattr(gui, "preview_speed_combo"):
        gui.preview_speed_combo.currentIndexChanged.connect(gui.on_preview_speed_changed)
    gui.final_output_folder_edit.textChanged.connect(gui.voice_output_folder_edit.setText)
    gui.final_output_folder_edit.textChanged.connect(gui.srt_output_folder_edit.setText)
    gui.video_path_edit.textChanged.connect(gui.refresh_ui_state)
    gui.video_path_edit.textChanged.connect(gui.update_project_header)
    gui.audio_source_edit.textChanged.connect(gui.refresh_ui_state)
    gui.bg_music_edit.textChanged.connect(gui.refresh_ui_state)
    gui.mixed_audio_edit.textChanged.connect(gui.refresh_ui_state)
    gui.use_generated_audio_radio.toggled.connect(gui.on_audio_source_mode_changed)
    if hasattr(gui, "subtitle_single_line_cb"):
        gui.subtitle_single_line_cb.toggled.connect(gui.on_single_line_toggled)
    if hasattr(gui, "subtitle_words_per_segment_spin"):
        gui.subtitle_words_per_segment_spin.valueChanged.connect(lambda _value: gui.on_single_line_toggled(gui.subtitle_single_line_cb.isChecked()))
    gui.use_existing_audio_radio.toggled.connect(gui.on_audio_source_mode_changed)
    if hasattr(gui, "translation_engine_combo"):
        gui.translation_engine_combo.currentIndexChanged.connect(gui.on_translation_engine_changed)
    if hasattr(gui, "translation_test_btn"):
        gui.translation_test_btn.clicked.connect(gui.on_translation_engine_test_connection)
    # Write the visible API credentials through as soon as the user finishes
    # editing a field, so a pasted/new key applies immediately instead of only
    # after a successful Test Connection or Generate.
    for _edit_name in (
        "translation_api_key_edit",
        "translation_model_edit",
        "translation_polish_model_edit",
        "translation_base_url_edit",
    ):
        _edit = getattr(gui, _edit_name, None)
        if _edit is not None:
            _edit.editingFinished.connect(gui.on_translation_credentials_edited)
    gui.blur_area_btn.toggled.connect(gui.toggle_blur_effect_enabled)
    # The visible Blur button creates a timeline-backed B1 layer.  Keeping
    # creation in one path ensures multiple Blur layers receive independent
    # timing, selection, persistence, and preview state.
    gui.blur_add_btn.clicked.connect(lambda: gui.on_add_timeline_layer("blur"))
    gui.ocr_region_btn.clicked.connect(gui.toggle_ocr_overlay_visibility)
    if hasattr(gui, "ocr_translator_btn"):
        gui.ocr_translator_btn.toggled.connect(gui.toggle_ocr_translator)
    if hasattr(gui, "ocr_translator_overlay"):
        gui.ocr_translator_overlay.captureRequested.connect(gui.capture_ocr_translator_region)
        gui.ocr_translator_overlay.rectChanged.connect(gui._on_ocr_translator_rect_changed)
    if hasattr(gui, "video_view") and hasattr(gui.video_view, "framingChanged"):
        gui.video_view.framingChanged.connect(gui.on_preview_framing_changed)
    gui.transcript_text.textChanged.connect(gui.refresh_ui_state)
    gui.transcript_text.textChanged.connect(gui.schedule_live_subtitle_preview_refresh)
    gui.transcript_text.textChanged.connect(gui.sync_segment_editor_from_hidden_text)
    gui.translated_text.textChanged.connect(gui.refresh_ui_state)
    gui.translated_text.textChanged.connect(gui.schedule_live_subtitle_preview_refresh)
    gui.translated_text.textChanged.connect(gui.sync_segment_editor_from_hidden_text)
    if hasattr(gui, "anchor_inspector_cb"):
        gui.anchor_inspector_cb.toggled.connect(gui.on_anchor_inspector_toggled)
    gui.subtitle_font_combo.currentTextChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_font_size_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_font_scale_combo"):
        gui.subtitle_font_scale_combo.currentIndexChanged.connect(gui.on_subtitle_font_scale_changed)
        gui.subtitle_font_size_spin.valueChanged.connect(gui.sync_subtitle_font_scale_control)
    gui.subtitle_animation_combo.currentTextChanged.connect(gui.on_subtitle_animation_changed)
    gui.subtitle_bold_cb.toggled.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_speaker_colors_cb"):
        gui.subtitle_speaker_colors_cb.toggled.connect(gui.update_subtitle_preview_style)
    gui.subtitle_preset_tiktok_radio.toggled.connect(gui.on_subtitle_preset_changed)
    gui.subtitle_preset_youtube_radio.toggled.connect(gui.on_subtitle_preset_changed)
    gui.subtitle_preset_minimal_radio.toggled.connect(gui.on_subtitle_preset_changed)
    gui.subtitle_preset_custom_radio.toggled.connect(gui.on_subtitle_preset_changed)
    gui.subtitle_keyword_highlight_cb.toggled.connect(gui.update_subtitle_preview_style)
    gui.subtitle_highlight_color_combo.currentTextChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_highlight_mode_combo.currentTextChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_animation_time_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_position_mode_combo.currentTextChanged.connect(gui.on_subtitle_position_mode_changed)
    gui.subtitle_align_combo.currentTextChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_custom_x_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_custom_y_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_x_offset_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_bottom_offset_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    gui.subtitle_background_cb.toggled.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_outline_cb"):
        gui.subtitle_outline_cb.toggled.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_bg_alpha_spin"):
        gui.subtitle_bg_alpha_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_background_padding_spin"):
        gui.subtitle_background_padding_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_background_radius_spin"):
        gui.subtitle_background_radius_spin.valueChanged.connect(gui.update_subtitle_preview_style)
    if hasattr(gui, "subtitle_background_width_combo"):
        gui.subtitle_background_width_combo.currentIndexChanged.connect(gui.on_subtitle_background_width_changed)
        gui.subtitle_background_shape_combo.currentIndexChanged.connect(gui.update_subtitle_preview_style)

    gui.subtitle_font_combo.currentTextChanged.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_font_size_spin.valueChanged.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_animation_combo.currentTextChanged.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_bold_cb.toggled.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_keyword_highlight_cb.toggled.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_highlight_color_combo.currentTextChanged.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_highlight_mode_combo.currentTextChanged.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_animation_time_spin.valueChanged.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_background_cb.toggled.connect(gui.on_subtitle_style_control_edited)
    gui.subtitle_karaoke_timing_combo.currentTextChanged.connect(gui.on_subtitle_style_control_edited)
    if hasattr(gui, "subtitle_outline_cb"):
        gui.subtitle_outline_cb.toggled.connect(gui.on_subtitle_style_control_edited)
    if hasattr(gui, "subtitle_bg_alpha_spin"):
        gui.subtitle_bg_alpha_spin.valueChanged.connect(gui.on_subtitle_style_control_edited)
    if hasattr(gui, "subtitle_background_padding_spin"):
        gui.subtitle_background_padding_spin.valueChanged.connect(gui.on_subtitle_style_control_edited)
    if hasattr(gui, "subtitle_background_radius_spin"):
        gui.subtitle_background_radius_spin.valueChanged.connect(gui.on_subtitle_style_control_edited)
    if hasattr(gui, "subtitle_background_width_combo"):
        gui.subtitle_background_width_combo.currentIndexChanged.connect(gui.on_subtitle_style_control_edited)
        gui.subtitle_background_shape_combo.currentIndexChanged.connect(gui.on_subtitle_style_control_edited)
    if hasattr(gui, "subtitle_single_line_cb"):
        gui.subtitle_single_line_cb.toggled.connect(gui.on_subtitle_style_control_edited)

    # add_layer_btn uses QMenu (connected via actions in preview_panel.py)

    gui.on_advanced_toggled(bool(getattr(gui, "toggle_advanced_btn", None) and gui.toggle_advanced_btn.isChecked()))

    if hasattr(gui, "mini_status_bar") and gui.mini_status_bar is not None:
        def _on_mini_show_dialog():
            pc = getattr(gui, "pipeline_controller", None)
            if pc and getattr(pc, "progress_dialog", None):
                pc.progress_dialog.show()
                pc.progress_dialog.raise_()
                pc.progress_dialog.activateWindow()

        def _on_mini_stop_requested():
            pc = getattr(gui, "pipeline_controller", None)
            if pc and hasattr(pc, "_on_pipeline_stop"):
                pc._on_pipeline_stop()
            vocal_thread = getattr(gui, "vocal_thread", None)
            if vocal_thread and getattr(vocal_thread, "isRunning", lambda: False)():
                try:
                    vocal_thread.stop()
                except Exception:
                    pass

        gui.mini_status_bar.show_dialog_requested.connect(_on_mini_show_dialog)
        gui.mini_status_bar.stop_requested.connect(_on_mini_stop_requested)


def _initialize_ui_state(gui):
    QTimer.singleShot(100, gui.video_view.reposition_subtitle)

    gui.current_segments = []
    gui.current_translated_segments = []
    gui._frame_preview_running = False
    gui._pending_auto_frame_preview = False
    gui._show_dialog_on_frame_preview = False
    gui.auto_frame_preview_timer = QTimer(gui)
    gui.auto_frame_preview_timer.setSingleShot(True)
    gui.auto_frame_preview_timer.setInterval(700)
    gui.auto_frame_preview_timer.timeout.connect(gui.trigger_auto_frame_preview)
    gui.seek_frame_preview_timer = QTimer(gui)
    gui.seek_frame_preview_timer.setSingleShot(True)
    gui.seek_frame_preview_timer.setInterval(300)
    gui.seek_frame_preview_timer.timeout.connect(gui.trigger_seek_frame_preview)
    gui.live_subtitle_preview_timer = QTimer(gui)
    gui.live_subtitle_preview_timer.setSingleShot(True)
    gui.live_subtitle_preview_timer.setInterval(250)
    gui.live_subtitle_preview_timer.timeout.connect(gui.refresh_live_subtitle_preview)
    gui.subtitle_ass_debounce_timer = QTimer(gui)
    gui.subtitle_ass_debounce_timer.setSingleShot(True)
    # Font and size controls can emit many intermediate values while being
    # dragged.  Only the settled value needs an exact libass layout pass.
    gui.subtitle_ass_debounce_timer.setInterval(360)
    gui.subtitle_ass_debounce_timer.timeout.connect(gui._start_deferred_subtitle_ass_build)
    gui.video_filter_preview_timer = QTimer(gui)
    gui.video_filter_preview_timer.setSingleShot(True)
    gui.video_filter_preview_timer.setInterval(350)
    gui.video_filter_preview_timer.timeout.connect(gui.run_live_video_filter_preview)
    # Inspector shell starts collapsed (handle only). The shell expands
    # when the user clicks a track layer or toggles the inspector open.
    gui._inspector_collapsed = True
    gui.last_extracted_audio = ""
    gui.last_vocals_path = ""
    gui.last_music_path = ""
    gui.last_original_srt_path = ""
    gui.last_translated_srt_path = ""
    gui.last_voice_vi_path = ""
    gui.last_mixed_vi_path = ""
    gui.last_preview_video_path = ""
    gui.last_styled_preview_path = ""
    gui.last_styled_preview_signature = ""
    gui.last_exported_video_path = ""
    gui.last_exact_preview_5s_path = ""
    gui.last_exact_preview_frame_path = ""
    gui._preview_video_has_burned_subtitles = False
    # Regular preview uses MPV/libass just like Fast Preview and export. The
    # Qt subtitle widget remains as an invisible drag target only.
    gui._use_libass_live_preview = True
    gui._preview_audio_track_mode = "both"
    gui._mute_original = False
    gui._mute_dubbed = False
    gui._preview_audio_track_switching = False
    gui.live_preview_subtitle_path = ""
    gui.live_preview_ass_path = ""
    gui.live_preview_segments = []
    gui.live_preview_editor_name = ""
    gui._live_preview_signature = None
    gui._styled_preview_running = False
    gui._suspend_live_subtitle_sync = False
    gui._syncing_segment_editor = False
    gui._syncing_hidden_editor_text = False
    gui._segment_editor_rows = []
    gui._selected_segment_index = -1
    # Export-only calibration. Keep it at 1.0 for the authored size; raise
    # it when the burned ASS text needs to match a larger Qt preview.
    gui.subtitle_export_font_scale = 1
    gui.use_exact_subtitle_preview = True

    gui.update_subtitle_preview_style()
    gui.refresh_ui_state()
    gui.on_subtitle_preset_changed()
    gui.on_output_mode_changed(gui.output_mode_combo.currentText())
    gui.update_project_header()
    gui.refresh_ui_state()
    # Restore anchor preference from settings. If user previously had
    # the inspector anchored, keep it open; otherwise start collapsed.
    if gui.is_subtitle_inspector_anchored():
        gui._inspector_collapsed = False
    else:
        gui._inspector_collapsed = True
    gui.set_inspector_collapsed(gui._inspector_collapsed)
    # If collapsed on startup, switch the stack to default (no card) so
    # only the handle is visible.
    if gui._inspector_collapsed and hasattr(gui, "inspector_stack"):
        gui.inspector_stack.setCurrentIndex(2)
    # Sync shell width to current collapsed state
    if hasattr(gui, "_sync_subtitle_inspector_shell_width"):
        try:
            gui._sync_subtitle_inspector_shell_width(visible=not gui._inspector_collapsed)
        except Exception:
            pass
    gui.sync_segment_editor_rows()
    gui.set_controls_panel_visible(False)

