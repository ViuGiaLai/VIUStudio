from PySide6.QtWidgets import (
    QApplication, QScrollArea)
from PySide6.QtCore import Qt, QTimer

from helpers import (
    extract_subtitle_text_entries,
    format_segments_to_srt,
    format_timestamp,
    normalize_subtitle_timing,
    parse_srt_to_segments,
    validate_srt_text,
)
from views import build_main_window_ui



class WindowUiMixin:
    def get_selected_subtitle_preset(self) -> str:
        if getattr(self, "subtitle_preset_custom_radio", None) and self.subtitle_preset_custom_radio.isChecked():
            return "custom"
        if getattr(self, "subtitle_preset_tiktok_radio", None) and self.subtitle_preset_tiktok_radio.isChecked():
            return "tiktok"
        if getattr(self, "subtitle_preset_youtube_radio", None) and self.subtitle_preset_youtube_radio.isChecked():
            return "youtube"
        if getattr(self, "subtitle_preset_minimal_radio", None) and self.subtitle_preset_minimal_radio.isChecked():
            return "minimal"
        return "youtube"

    def get_subtitle_preset_config(self, preset_key: str | None = None) -> dict:
        preset = (preset_key or self.get_selected_subtitle_preset()).lower()
        presets = {
            "tiktok": {
                "label": "TikTok",
                "font_name": "Montserrat",
                "font_size": 56,
                "font_color": "#FFFFFF",
                "highlight_color": "#FFD400",
                "outline_color": "#000000",
                "outline_width": 7,
                "shadow_color": "#000000",
                "shadow_depth": 2,
                "shadow_alpha": 0.7,
                "background_box": False,
                "background_color": "#000000",
                "background_alpha": 0.0,
                "animation": "Word Highlight Karaoke",
                "bold": True,
                "auto_keyword_highlight": True,
                "highlight_mode": "Auto + Manual",
                "summary": "Large subtitle with karaoke-style word timing and highlighted keywords for short-form videos.",
            },
            "youtube": {
                "label": "YouTube",
                "font_name": "Roboto",
                "font_size": 48,
                "font_color": "#FFFFFF",
                "highlight_color": "#FFFFFF",
                "outline_color": "#000000",
                "outline_width": 3,
                "shadow_color": "#000000",
                "shadow_depth": 1,
                "shadow_alpha": 0.35,
                "background_box": True,
                "background_color": "#000000",
                "background_alpha": 1.0,
                "animation": "Fade In",
                "bold": False,
                "auto_keyword_highlight": False,
                "highlight_mode": "Manual",
                "summary": "Clean subtitle with a solid background box for long-form readability.",
            },
            "minimal": {
                "label": "Short",
                "font_name": "Inter",
                "font_size": 44,
                "font_color": "#FFFFFF",
                "highlight_color": "#FFFFFF",
                "outline_color": "#000000",
                "outline_width": 0,
                "shadow_color": "#000000",
                "shadow_depth": 1,
                "shadow_alpha": 0.15,
                "background_box": False,
                "background_color": "#000000",
                "background_alpha": 0.0,
                "animation": "Slide Up",
                "bold": False,
                "summary": "Light, modern caption with almost no stroke and a gentle slide/fade entrance.",
            },
            "custom": {
                "label": "Custom",
                "font_name": "Segoe UI",
                "font_size": 52,
                "font_color": "#FFFFFF",
                "highlight_color": "#FFD400",
                "outline_color": "#000000",
                "outline_width": 3,
                "shadow_color": "#000000",
                "shadow_depth": 1,
                "shadow_alpha": 0.3,
                "background_box": False,
                "background_color": "#000000",
                "background_alpha": 0.6,
                "animation": "Pop In",
                "bold": True,
                "auto_keyword_highlight": False,
                "highlight_mode": "Auto",
                "summary": "Your editable working preset. Manual style changes can switch here automatically.",
            },
        }
        return presets.get(preset, presets["tiktok"]).copy()

    def parse_srt_to_segments(self, srt_text):
        return parse_srt_to_segments(srt_text)

    def normalize_subtitle_timing(self, segments, gap_seconds=0.04):
        return normalize_subtitle_timing(segments, gap_seconds=gap_seconds)

    def validate_srt_text(self, srt_text, expected_len=None):
        return validate_srt_text(srt_text, expected_len=expected_len)

    def extract_subtitle_text_entries(self, srt_text):
        return extract_subtitle_text_entries(srt_text)

    def format_to_srt(self, segments):
        return format_segments_to_srt(segments)

    def format_timestamp(self, seconds):
        return format_timestamp(seconds)

    def setup_ui(self):
        build_main_window_ui(self)

    def prepare_responsive_layout(self):
        """Apply only the target-screen responsive profile while hidden."""
        screen = self.screen() or QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        if geometry is None:
            self.apply_responsive_layout()
            return
        self.apply_responsive_layout(geometry.width(), geometry.height())

    def prepare_initial_editor_layout(self):
        """Resolve the complete first editor layout while the window is hidden.

        Unlike the old post-show timers, this gives the central widget and
        splitter their final screen-sized geometry first, activates Qt's
        layouts, and then applies the initial 45/55 workspace allocation.
        The first visible paint is therefore already the settled layout.
        """
        if getattr(self, "_initial_layout_finalized", False):
            return
        screen = self.screen() or QApplication.primaryScreen()
        geometry = screen.availableGeometry() if screen is not None else None
        if geometry is not None:
            self.setGeometry(geometry)
        self.ensurePolished()
        central = self.centralWidget()
        if central is not None:
            central.setGeometry(self.contentsRect())
            layout = central.layout()
            if layout is not None:
                layout.activate()
        self.prepare_responsive_layout()
        if central is not None and central.layout() is not None:
            central.layout().activate()
        set_default_splitter = getattr(self, "_set_default_preview_timeline_sizes", None)
        if callable(set_default_splitter):
            set_default_splitter()
        self._initial_layout_finalized = True

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_initial_layout_finalized", False):
            return
        # Fallback for non-launcher entry points. The normal Launcher flow
        # calls prepare_initial_editor_layout() before show().
        self.prepare_initial_editor_layout()

    def resizeEvent(self, event):
        """Apply responsive layout changes after Qt settles a resize/DPI move."""
        super().resizeEvent(event)
        if not getattr(self, "_initial_layout_finalized", False):
            return
        if not getattr(self, "_responsive_layout_pending", False):
            self._responsive_layout_pending = True
            QTimer.singleShot(0, self.apply_responsive_layout)

    def apply_responsive_layout(self, available_width=None, available_height=None):
        """Keep the editor usable from 1280x720 upward without altering
        the normal desktop composition.

        Width controls the two side panels; available height controls the
        Preview/Timeline minimums.  Content remains reachable through the
        existing inspector and timeline scroll areas instead of being clipped.
        """
        self._responsive_layout_pending = False
        central = self.centralWidget()
        width = int(available_width or (central.width() if central is not None else self.width()) or self.width())
        height = int(available_height or (central.height() if central is not None else self.height()) or self.height())
        compact_width = width < 1500
        compact_height = height < 850
        tight_height = height < 760
        mode = "compact" if (compact_width or compact_height) else "desktop"
        self._responsive_layout_mode = mode

        root_layout = getattr(self, "root_layout", None)
        content_layout = getattr(self, "content_layout", None)
        header_layout = getattr(self, "header_layout", None)
        if root_layout is not None:
            margin = 8 if compact_height else 15
            root_layout.setContentsMargins(margin, margin, margin, margin)
            root_layout.setSpacing(8 if compact_height else 15)
        if content_layout is not None:
            content_layout.setSpacing(8 if compact_width else 15)
        if header_layout is not None:
            header_layout.setContentsMargins(10 if compact_width else 18, 8 if compact_height else 14,
                                             10 if compact_width else 18, 8 if compact_height else 14)
            header_layout.setSpacing(6 if compact_width else 12)

        # Narrower side panels leave a meaningful preview width on 1366/1280
        # laptops while the cards themselves remain scrollable.
        left_panel = getattr(self, "left_panel_scroll_area", None)
        if left_panel is not None:
            # The rail now carries navigation, so the controls column should
            # stay a focused workbench rather than consuming half the screen.
            # Its contents remain scrollable and all controls are reachable.
            left_panel.setFixedWidth(286 if compact_width else 348)
        inspector_width = 292 if compact_width else 340
        inspector_max = 410 if compact_width else 480
        self._responsive_inspector_width = inspector_width
        studio_inspector = getattr(self, "studio_inspector", None)
        for attr in (
            "subtitle_inspector_card", "audio_inspector_card", "blur_inspector_card",
            "logo_inspector_card", "mask_inspector_card", "text_inspector_card",
            "default_inspector_card", "video_inspector_card",
        ):
            card = getattr(self, attr, None)
            if card is not None:
                if studio_inspector is not None:
                    card.setMinimumWidth(0)
                    card.setMaximumWidth(16777215)
                else:
                    card.setMinimumWidth(inspector_width)
                    card.setMaximumWidth(inspector_max)
        self._sync_subtitle_inspector_shell_width()
        stack = getattr(self, "inspector_stack", None)
        if stack is not None:
            for index in range(stack.count()):
                scroll = stack.widget(index)
                if isinstance(scroll, QScrollArea):
                    scroll.setHorizontalScrollBarPolicy(
                        Qt.ScrollBarAsNeeded if compact_width else Qt.ScrollBarAlwaysOff
                    )

        # The fixed minimums are intentionally reduced only on short displays.
        # Timeline tracks remain available through their own scrollbars.
        workspace_min = 350
        timeline_min = 360
        video_min = 270
        if compact_height:
            workspace_min, timeline_min, video_min = 260, 255, 190
        if tight_height:
            workspace_min, timeline_min, video_min = 220, 210, 170
        self._responsive_workspace_minimum_height = workspace_min
        self._responsive_timeline_minimum_height = timeline_min
        workspace = getattr(self, "preview_workspace_widget", None)
        timeline_card = getattr(self, "timeline_card", None)
        video_view = getattr(self, "video_view", None)
        if workspace is not None:
            workspace.setMinimumHeight(workspace_min)
        if timeline_card is not None:
            timeline_card.setMinimumHeight(timeline_min)
        if video_view is not None:
            video_view.setMinimumHeight(video_min)

        # Keep the action group balanced at every DPI.  Fixed, coordinated
        # widths prevent the overflow button from stretching into a large
        # empty rectangle when the project title has little room.
        header_height = 36 if compact_height else 40
        header_sizes = (
            ("run_all_btn", 118 if compact_width else 132),
            ("export_btn", 82 if compact_width else 92),
            ("preview_5s_btn", 110 if compact_width else 124),
            ("header_home_btn", 86 if compact_width else 96),
            ("more_actions_btn", 78 if compact_width else 86),
        )
        for attr, button_width in header_sizes:
            button = getattr(self, attr, None)
            if button is not None:
                button.setFixedSize(button_width, header_height)
        preview_button = getattr(self, "preview_5s_btn", None)
        if preview_button is not None:
            preview_button.setVisible(not compact_width)
        logo = getattr(self, "header_logo_label", None)
        if logo is not None:
            logo.setVisible(not compact_width)
        brand = getattr(self, "header_brand_label", None)
        if brand is not None:
            brand.setVisible(not compact_width)

        # Ensure altered minimums are immediately reflected in splitter bounds
        # and native preview overlay geometry.
        splitter = getattr(self, "preview_timeline_splitter", None)
        if splitter is not None:
            sizes = splitter.sizes()
            if len(sizes) == 2 and sum(sizes) > timeline_min and sizes[1] < timeline_min:
                splitter.setSizes([max(1, sum(sizes) - timeline_min), timeline_min])
        self.sync_left_panel_container_width()
        QTimer.singleShot(0, self._resync_preview_region_overlays)

    def _run_deferred_startup_stage1(self):
        if getattr(self, "_deferred_startup_stage1_done", False):
            return
        self._deferred_startup_stage1_done = True
        self.setup_audio_preview_player()
        self.load_user_settings()
        self.refresh_saved_subtitle_style_presets()

    def _run_deferred_startup_stage2(self):
        if getattr(self, "_deferred_startup_stage2_done", False):
            return
        self._deferred_startup_stage2_done = True
        self.load_voice_preview_catalog()

    def ensure_media_backend_ready(self):
        if getattr(self, "_media_backend_ready", False):
            return
        self.setup_media_player()
        if hasattr(self, "video_view") and hasattr(self.video_view, "blurRegionChanged"):
            if getattr(self, "_blur_region_signal_bound", False):
                try:
                    self.video_view.blurRegionChanged.disconnect(self.on_preview_blur_region_changed)
                except Exception:
                    pass
            self.video_view.blurRegionChanged.connect(self.on_preview_blur_region_changed)
            self._blur_region_signal_bound = True
        if hasattr(self, "video_view") and hasattr(self.video_view, "blurEditFinished"):
            if getattr(self, "_blur_edit_finished_signal_bound", False):
                try:
                    self.video_view.blurEditFinished.disconnect(self.on_blur_edit_finished)
                except Exception:
                    pass
            self.video_view.blurEditFinished.connect(self.on_blur_edit_finished)
            self._blur_edit_finished_signal_bound = True
        if hasattr(self, "video_view") and hasattr(self.video_view, "subtitlePositionChanged"):
            if not getattr(self, "_subtitle_position_drag_signal_bound", False):
                self.video_view.subtitlePositionChanged.connect(self.on_subtitle_position_dragged)
                self._subtitle_position_drag_signal_bound = True
        if hasattr(self, "video_view") and hasattr(self.video_view, "subtitleFontSizeChanged"):
            if not getattr(self, "_subtitle_font_scale_signal_bound", False):
                self.video_view.subtitleFontSizeChanged.connect(self.on_subtitle_font_size_scaled)
                self._subtitle_font_scale_signal_bound = True
        if hasattr(self, "video_view") and hasattr(self.video_view, "subtitleClicked"):
            if not getattr(self, "_subtitle_clicked_signal_bound", False):
                self.video_view.subtitleClicked.connect(self.on_preview_subtitle_clicked)
                self._subtitle_clicked_signal_bound = True
        if hasattr(self, "video_view") and hasattr(self.video_view, "textLayerSelected"):
            if not getattr(self, "_text_layer_signal_bound", False):
                self.video_view.textLayerSelected.connect(self._on_text_layer_selected_from_preview)
                self.video_view.textLayerMoved.connect(self._on_text_layer_moved)
                self._text_layer_signal_bound = True

    def _on_text_layer_selected_from_preview(self, layer_id):
        if hasattr(self, "timeline"):
            self.timeline._selected_layer_id = str(layer_id)
            self.timeline._redraw()
        self.on_timeline_layer_selected(str(layer_id))

    def _on_text_layer_moved(self, layer_id, x, y):
        if self._preview_is_playing():
            return
        layer = next((item for item in self._text_layers() if item.id == layer_id), None)
        if layer is None:
            return
        layer.transform.x, layer.transform.y = float(x), float(y)
        self.schedule_timeline_project_persist()

    def _configure_local_voice_mode_ui(self):
        if hasattr(self, "use_free_voice_radio"):
            try:
                self.use_free_voice_radio.setChecked(True)
                self.use_free_voice_radio.setVisible(False)
                self.use_free_voice_radio.setEnabled(False)
            except Exception:
                pass
        if hasattr(self, "use_premium_voice_radio"):
            try:
                self.use_premium_voice_radio.setChecked(False)
                self.use_premium_voice_radio.setVisible(False)
                self.use_premium_voice_radio.setEnabled(False)
            except Exception:
                pass
        if hasattr(self, "premium_voice_combo"):
            try:
                self.premium_voice_combo.clear()
                self.premium_voice_combo.setVisible(False)
                self.premium_voice_combo.setEnabled(False)
            except Exception:
                pass
        if hasattr(self, "preview_voice_btn"):
            try:
                self.preview_voice_btn.setText("Preview voice")
            except Exception:
                pass
        if hasattr(self, "voice_preview_meta_label"):
            try:
                self.voice_preview_meta_label.setText("Generate a short preview audio clip with the selected local voice.")
            except Exception:
                pass
