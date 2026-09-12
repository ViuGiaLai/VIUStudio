import os
import json
from PySide6.QtWidgets import (
    QInputDialog)
from PySide6.QtCore import QUrl

from utils.settings_utils import load_user_settings as load_user_settings_impl, save_user_settings as save_user_settings_impl



class FilterSubtitleStyleMixin:
    def on_audio_source_mode_changed(self):
        if not hasattr(self, "audio_source_hint_label"):
            return
        using_existing = bool(hasattr(self, "use_existing_audio_radio") and self.use_existing_audio_radio.isChecked())
        if using_existing:
            self.audio_source_hint_label.setText(
                "Use a completed audio file for preview and export. TTS and background-audio settings are not used."
            )
        else:
            self.audio_source_hint_label.setText(
                "Create a voice from translated subtitles. You can optionally mix in background audio."
            )
        generated_panel = getattr(self, "generated_audio_source_panel", None)
        if generated_panel:
            generated_panel.setVisible(not using_existing)
        existing_panel = getattr(self, "existing_audio_source_panel", None)
        if existing_panel:
            existing_panel.setVisible(using_existing)
        generated_widgets = [
            "generated_audio_section_label",
            "generated_audio_section_hint",
            "bg_music_label",
            "bg_music_edit",
            "browse_bg_music_btn",
            "voiceover_btn",
        ]
        existing_widgets = [
            "existing_audio_section_label",
            "existing_audio_section_hint",
            "mixed_audio_label",
            "mixed_audio_edit",
            "browse_mixed_audio_btn",
        ]
        for name in generated_widgets:
            widget = getattr(self, name, None)
            if widget:
                widget.setEnabled(not using_existing)
        for name in existing_widgets:
            widget = getattr(self, name, None)
            if widget:
                widget.setEnabled(using_existing)
        self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)
        self.refresh_ui_state()

    def on_advanced_toggled(self, checked: bool):
        if hasattr(self, "tabs"):
            self.tabs.setVisible(True)
        if hasattr(self, "workflow_advanced_layout"):
            checked = True
        if hasattr(self, "toggle_advanced_btn"):
            self.toggle_advanced_btn.setText(("▼ " if checked else "▶ ") + "Advanced Settings")
        if hasattr(self, "advanced_section_content"):
            self.advanced_section_content.setVisible(bool(checked))

    def on_auto_preview_toggled(self, checked: bool):
        if checked:
            self.schedule_auto_frame_preview()
        else:
            self.auto_frame_preview_timer.stop()
            self.seek_frame_preview_timer.stop()

    def schedule_live_subtitle_preview_refresh(self):
        if not hasattr(self, "live_subtitle_preview_timer"):
            return
        self.live_subtitle_preview_timer.start()

    def refresh_live_subtitle_preview(self):
        self.live_preview_segments, self.live_preview_editor_name = self._resolve_live_preview_segments()
        self.sync_live_subtitle_preview()

    def schedule_live_video_filter_preview(self):
        if self._is_realtime_color_filter_state():
            self._pending_video_filter_preview = False
            self._apply_realtime_color_filter_preview()
            return
        if not hasattr(self, "video_filter_preview_timer"):
            return
        self._pending_video_filter_preview = True
        if getattr(self, "_styled_preview_running", False):
            return
        self.video_filter_preview_timer.start()

    def _is_realtime_color_filter_state(self) -> bool:
        """Return whether the current state is safe for MPV live preview."""
        try:
            state = self.get_video_filter_state()
            # LUT preview is realtime only when the active MPV backend has
            # native gpu-next/libplacebo LUT support. The stable gpu backend
            # continues using the debounced FFmpeg preview path.
            if (
                state.get("lut_path")
                and float(state.get("lut_strength", 0) or 0) > 0.001
                and not bool(getattr(self.media_player, "supports_native_lut", False))
            ):
                return False
            return bool(getattr(self.media_player, "backend_name", "") == "libmpv") and hasattr(
                self.media_player, "set_color_filter_state"
            )
        except Exception:
            return False

    def _apply_realtime_color_filter_preview(self) -> bool:
        if not self._is_realtime_color_filter_state():
            return False
        try:
            source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
            if not source_path or not os.path.exists(source_path):
                return False
            current_source = str(getattr(self.media_player, "_source_path", "") or "")
            was_playing = bool(self.media_player.is_playing())
            position = int(self.media_player.position() or 0)
            if os.path.abspath(current_source) != os.path.abspath(source_path):
                self.media_player.setSource(QUrl.fromLocalFile(source_path))
                if position > 0:
                    self.media_player.setPosition(position)
                if was_playing:
                    self.media_player.play()
            self.media_player.set_color_filter_state(self.get_video_filter_state())
            self._video_filter_preview_dirty = False
            self._video_filter_apply_requested = False
            self._play_video_filter_preview_when_ready = False
            return True
        except Exception as exc:
            self.log(f"[Filter] MPV realtime preview failed: {exc}")
            return False

    def _is_video_filter_slider_interacting(self):
        sliders = [getattr(self, "video_filter_intensity_slider", None)]
        sliders.extend(list(getattr(self, "video_filter_adjust_sliders", {}).values()))
        for slider in sliders:
            if slider is not None and slider.isSliderDown():
                return True
        return False

    def on_video_filter_slider_released(self):
        self.schedule_live_video_filter_preview()

    def is_filter_workflow_active(self) -> bool:
        stack = getattr(self, "left_panel_stack", None)
        if stack is None:
            return False
        try:
            return int(stack.currentIndex()) == 4
        except Exception:
            return False

    def _mark_video_filter_preview_dirty(self):
        if self._is_realtime_color_filter_state():
            self._video_filter_preview_dirty = False
            self._video_filter_apply_requested = False
            self._apply_realtime_color_filter_preview()
            return
        self._video_filter_preview_dirty = self.has_active_video_filters()
        self._video_filter_apply_requested = False
        self.refresh_ui_state()

    def apply_current_video_filter(self):
        self.log(f"[Filter] apply_current_video_filter called, has_active={self.has_active_video_filters()}")
        if self._is_realtime_color_filter_state():
            self.log("[Filter] Applying Brightness/Contrast/Saturation through MPV realtime preview")
            self._apply_realtime_color_filter_preview()
            self.refresh_ui_state()
            return
        if not self.has_active_video_filters():
            self.log("[Filter] No active filters, returning early")
            self._video_filter_preview_dirty = False
            self._video_filter_apply_requested = False
            self.hide_filter_thumbnail_preview()
            self.refresh_ui_state()
            return
        self._video_filter_apply_requested = True
        self.refresh_ui_state()
        self.log("[Filter] Calling preview_controller.preview_video()")
        self.preview_controller.preview_video()

    def revert_video_filter_preview_to_source(self):
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        if not video_path or not os.path.exists(video_path):
            return
        self._play_video_filter_preview_when_ready = False
        self.hide_filter_thumbnail_preview()
        try:
            current_position = int(self.media_player.position())
        except Exception:
            current_position = 0
        try:
            self.media_player.pause()
        except Exception:
            pass
        try:
            self.media_player.setSource(QUrl.fromLocalFile(video_path))
            if current_position > 0:
                self.media_player.setPosition(current_position)
        except Exception:
            pass
        self.refresh_video_dimensions(video_path)
        self._preview_video_has_burned_subtitles = False
        self.sync_live_subtitle_preview()
        if hasattr(self, "timeline"):
            self.timeline.set_playing(False)
        self.refresh_ui_state()

    def _can_auto_render_filter_preview(self):
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        if not video_path or not os.path.exists(video_path):
            return False
        if getattr(self, "_styled_preview_running", False) or getattr(self, "_pipeline_active", False):
            return False
        if self.has_active_video_filters():
            return True
        mode = self.get_output_mode_key()
        if mode == "subtitle":
            return bool(self.last_translated_srt_path and os.path.exists(self.last_translated_srt_path))
        if mode == "voice":
            audio_path = self.resolve_selected_audio_path()
            return bool(audio_path and os.path.exists(audio_path))
        if mode == "both":
            audio_path = self.resolve_selected_audio_path()
            return bool(
                audio_path
                and os.path.exists(audio_path)
                and self.last_translated_srt_path
                and os.path.exists(self.last_translated_srt_path)
            )
        return False

    def run_live_video_filter_preview(self):
        if self._is_realtime_color_filter_state():
            self._pending_video_filter_preview = False
            return
        if getattr(self, "_styled_preview_running", False) or getattr(self, "_frame_preview_running", False):
            return
        if not getattr(self, "_pending_video_filter_preview", False):
            return
        if not self.has_active_video_filters():
            self._pending_video_filter_preview = False
            self.hide_filter_thumbnail_preview()
            return
        if not self._can_auto_render_filter_preview():
            self._pending_video_filter_preview = False
            return
        self._pending_video_filter_preview = False
        try:
            self.preview_controller.start_exact_frame_preview(show_dialog=False)
        except Exception as exc:
            self.log(f"[Filter Preview] skipped: {exc}")

    def save_user_settings(self):
        save_user_settings_impl(self)
        try:
            self.settings.setValue("premium_voice_name", "")
            self.settings.setValue("premium_voice_value", "")
            self.settings.setValue("voice_tier", "free")
        except Exception:
            pass

    def load_user_settings(self):
        load_user_settings_impl(self)
        if hasattr(self, "use_premium_voice_radio"):
            try:
                self.use_premium_voice_radio.setChecked(False)
            except Exception:
                pass
        if hasattr(self, "use_free_voice_radio"):
            try:
                self.use_free_voice_radio.setChecked(True)
            except Exception:
                pass

    @staticmethod
    def _preload_tts_voice_impl(voice_name: str):
        from tts_processor import preload_tts_voice

        return preload_tts_voice(voice_name)

    @staticmethod
    def _test_remote_api_connection(base_url: str, token: str) -> dict:
        previous_url = os.environ.get("VIUSTUDIO_REMOTE_API_URL", "")
        previous_token = os.environ.get("VIUSTUDIO_REMOTE_API_TOKEN", "")
        try:
            os.environ["VIUSTUDIO_REMOTE_API_URL"] = (base_url or "").strip()
            if token:
                os.environ["VIUSTUDIO_REMOTE_API_TOKEN"] = token.strip()
            else:
                os.environ.pop("VIUSTUDIO_REMOTE_API_TOKEN", None)
            from remote_api import remote_api_get

            return remote_api_get("/health", timeout=10)
        finally:
            if previous_url:
                os.environ["VIUSTUDIO_REMOTE_API_URL"] = previous_url
            else:
                os.environ.pop("VIUSTUDIO_REMOTE_API_URL", None)
            if previous_token:
                os.environ["VIUSTUDIO_REMOTE_API_TOKEN"] = previous_token
            else:
                os.environ.pop("VIUSTUDIO_REMOTE_API_TOKEN", None)

    def _highlight_color_hex(self) -> str:
        mapping = {
            "Yellow": "#FFD400",
            "Cyan": "#00E5FF",
            "Green": "#5CFF95",
            "Pink": "#FF6BD6",
        }
        return mapping.get(self.subtitle_highlight_color_combo.currentText().strip(), "#FFD400")

    def is_custom_subtitle_position_mode(self) -> bool:
        if not hasattr(self, "subtitle_position_mode_combo"):
            return False
        return str(self.subtitle_position_mode_combo.currentData() or "anchor").strip().lower() == "custom"

    def on_subtitle_position_mode_changed(self, *_args):
        is_custom = self.is_custom_subtitle_position_mode()
        if hasattr(self, "subtitle_align_label"):
            self.subtitle_align_label.setVisible(not is_custom)
        if hasattr(self, "subtitle_align_combo"):
            self.subtitle_align_combo.setVisible(not is_custom)
        if hasattr(self, "subtitle_custom_x_label"):
            self.subtitle_custom_x_label.setVisible(is_custom)
        if hasattr(self, "subtitle_custom_x_spin"):
            self.subtitle_custom_x_spin.setVisible(is_custom)
        if hasattr(self, "subtitle_custom_y_label"):
            self.subtitle_custom_y_label.setVisible(is_custom)
        if hasattr(self, "subtitle_custom_y_spin"):
            self.subtitle_custom_y_spin.setVisible(is_custom)
        if hasattr(self, "subtitle_bottom_offset_label"):
            self.subtitle_bottom_offset_label.setVisible(not is_custom)
        if hasattr(self, "subtitle_bottom_offset_spin"):
            self.subtitle_bottom_offset_spin.setVisible(not is_custom)
        self.update_subtitle_preview_style()
        if getattr(self, "current_project_state", None) is not None:
            self.schedule_timeline_project_persist()

    def on_subtitle_drag_started(self):
        """Swap to the Qt layer only while dragging for immediate feedback."""
        if self._preview_is_playing():
            return
        if getattr(self, "_preview_video_has_burned_subtitles", False):
            return
        if hasattr(self, "media_player"):
            self.media_player.clear_subtitle()
        if hasattr(self, "video_view"):
            self.video_view.subtitle_item.set_text_rendering(True)

    def on_subtitle_position_dragged(self, x_percent: int, y_percent: int):
        """Commit a drag from the live subtitle overlay to style controls."""
        if self._preview_is_playing():
            return
        x_percent = max(0, min(100, int(x_percent)))
        y_percent = max(0, min(100, int(y_percent)))
        if hasattr(self, "subtitle_position_mode_combo"):
            self.subtitle_position_mode_combo.blockSignals(True)
            index = self.subtitle_position_mode_combo.findData("custom")
            if index >= 0:
                self.subtitle_position_mode_combo.setCurrentIndex(index)
            self.subtitle_position_mode_combo.blockSignals(False)
        for widget, value in (
            (getattr(self, "subtitle_custom_x_spin", None), x_percent),
            (getattr(self, "subtitle_custom_y_spin", None), y_percent),
        ):
            if widget is not None:
                widget.blockSignals(True)
                widget.setValue(value)
                widget.blockSignals(False)
        self.on_subtitle_position_mode_changed()

    def on_subtitle_font_size_scaled(self, font_size: int):
        """Commit a scale gesture from the live subtitle overlay to font size controls."""
        if self._preview_is_playing():
            return
        font_size = max(12, min(140, int(font_size)))
        if hasattr(self, "subtitle_font_size_spin"):
            self.subtitle_font_size_spin.blockSignals(True)
            self.subtitle_font_size_spin.setValue(font_size)
            self.subtitle_font_size_spin.blockSignals(False)
        self.on_subtitle_style_control_edited()
        self.update_subtitle_preview_style()
        if getattr(self, "current_project_state", None) is not None:
            self.schedule_timeline_project_persist()

    def get_subtitle_position_config(self) -> dict:
        alignment_map = {
            "Bottom Left": 1,
            "Bottom Center": 2,
            "Bottom": 2,
            "Bottom Right": 3,
            "Center": 5,
            "Top Center": 8,
            "Top": 8,
        }
        return {
            "position_mode": "custom" if self.is_custom_subtitle_position_mode() else "anchor",
            "alignment_label": self.subtitle_align_combo.currentText().strip(),
            "alignment": alignment_map.get(self.subtitle_align_combo.currentText(), 2),
            "margin_v": int(self.subtitle_bottom_offset_spin.value()),
            "x_offset": int(self.subtitle_x_offset_spin.value()),
            "custom_position_enabled": self.is_custom_subtitle_position_mode(),
            "custom_position_x": int(self.subtitle_custom_x_spin.value()),
            "custom_position_y": int(self.subtitle_custom_y_spin.value()),
        }

    def _saved_subtitle_style_payload(self) -> dict:
        return {
            "preset": self.get_selected_subtitle_preset(),
            "font": self.subtitle_font_combo.currentText().strip(),
            "size": int(self.subtitle_font_size_spin.value()),
            "color": self.subtitle_color_hex,
            "background_color": getattr(self, "subtitle_background_color_hex", "#000000"),
            "animation": self.subtitle_animation_combo.currentText().strip(),
            "animation_time": float(self.subtitle_animation_time_spin.value()),
            "karaoke_timing_mode": str(self.subtitle_karaoke_timing_combo.currentData() or "vietnamese"),
            "background": bool(self.subtitle_background_cb.isChecked()),
            "background_width": str(self.subtitle_background_width_combo.currentData() if hasattr(self, "subtitle_background_width_combo") else "fit_text"),
            "background_shape": str(self.subtitle_background_shape_combo.currentData() if hasattr(self, "subtitle_background_shape_combo") else "rectangle"),
            "outline": bool(getattr(self, "subtitle_outline_cb", None) and self.subtitle_outline_cb.isChecked()),
            "background_alpha": float(self.subtitle_bg_alpha_spin.value()) if hasattr(self, "subtitle_bg_alpha_spin") else 0.6,
            "background_padding": int(self.subtitle_background_padding_spin.value()) if hasattr(self, "subtitle_background_padding_spin") else 6,
            "background_radius": int(self.subtitle_background_radius_spin.value()) if hasattr(self, "subtitle_background_radius_spin") else 0,
            "bold": bool(self.subtitle_bold_cb.isChecked()),
            "speaker_colors": self._uses_speaker_subtitle_colors(),
            "auto_keyword_highlight": bool(self.subtitle_keyword_highlight_cb.isChecked()),
            "highlight_color": self.subtitle_highlight_color_combo.currentText().strip(),
            "highlight_mode": self.subtitle_highlight_mode_combo.currentText().strip(),
        }

    def _current_subtitle_style_controls_state(self) -> dict:
        return {
            "preset": self.get_selected_subtitle_preset(),
            "font": self.subtitle_font_combo.currentText().strip(),
            "size": int(self.subtitle_font_size_spin.value()),
            "color": self.subtitle_color_hex,
            "background_color": getattr(self, "subtitle_background_color_hex", "#000000"),
            "animation": self.subtitle_animation_combo.currentText().strip(),
            "animation_time": float(self.subtitle_animation_time_spin.value()),
            "karaoke_timing_mode": str(self.subtitle_karaoke_timing_combo.currentData() or "vietnamese"),
            "background": bool(self.subtitle_background_cb.isChecked()),
            "background_width": str(self.subtitle_background_width_combo.currentData() if hasattr(self, "subtitle_background_width_combo") else "fit_text"),
            "background_shape": str(self.subtitle_background_shape_combo.currentData() if hasattr(self, "subtitle_background_shape_combo") else "rectangle"),
            "outline": bool(getattr(self, "subtitle_outline_cb", None) and self.subtitle_outline_cb.isChecked()),
            "background_alpha": float(self.subtitle_bg_alpha_spin.value()) if hasattr(self, "subtitle_bg_alpha_spin") else 0.6,
            "background_padding": int(self.subtitle_background_padding_spin.value()) if hasattr(self, "subtitle_background_padding_spin") else 6,
            "background_radius": int(self.subtitle_background_radius_spin.value()) if hasattr(self, "subtitle_background_radius_spin") else 0,
            "bold": bool(self.subtitle_bold_cb.isChecked()),
            "speaker_colors": self._uses_speaker_subtitle_colors(),
            "auto_keyword_highlight": bool(self.subtitle_keyword_highlight_cb.isChecked()),
            "highlight_color": self.subtitle_highlight_color_combo.currentText().strip(),
            "highlight_mode": self.subtitle_highlight_mode_combo.currentText().strip(),
            "single_line": bool(getattr(self, "subtitle_single_line_cb", None) and self.subtitle_single_line_cb.isChecked()),
            "single_line_words": int(self.subtitle_words_per_segment_spin.value()) if hasattr(self, "subtitle_words_per_segment_spin") else 4,
            "position": self.get_subtitle_position_config(),
        }

    def _apply_subtitle_style_controls_state(self, state: dict) -> None:
        if not isinstance(state, dict):
            return
        self.subtitle_font_combo.setCurrentText(str(state.get("font", self.subtitle_font_combo.currentText())))
        self.subtitle_font_size_spin.setValue(int(state.get("size", self.subtitle_font_size_spin.value())))
        self.subtitle_color_hex = str(state.get("color", self.subtitle_color_hex)).upper()
        self.subtitle_color_btn.setText(self.subtitle_color_hex)
        self.subtitle_background_color_hex = str(
            state.get("background_color", getattr(self, "subtitle_background_color_hex", "#000000"))
        ).upper()
        if hasattr(self, "subtitle_background_color_btn"):
            self.subtitle_background_color_btn.setText(self.subtitle_background_color_hex)
        self.subtitle_animation_combo.setCurrentText(str(state.get("animation", self.subtitle_animation_combo.currentText())))
        self.subtitle_animation_time_spin.setValue(float(state.get("animation_time", self.subtitle_animation_time_spin.value())))
        karaoke_mode = str(state.get("karaoke_timing_mode", self.subtitle_karaoke_timing_combo.currentData() or "vietnamese"))
        karaoke_index = self.subtitle_karaoke_timing_combo.findData(karaoke_mode)
        if karaoke_index >= 0:
            self.subtitle_karaoke_timing_combo.setCurrentIndex(karaoke_index)
        self.subtitle_background_cb.setChecked(bool(state.get("background", self.subtitle_background_cb.isChecked())))
        if hasattr(self, "subtitle_background_width_combo"):
            index = self.subtitle_background_width_combo.findData(str(state.get("background_width", "fit_text")))
            self.subtitle_background_width_combo.setCurrentIndex(max(0, index))
            shape_index = self.subtitle_background_shape_combo.findData(str(state.get("background_shape", "rectangle")))
            self.subtitle_background_shape_combo.setCurrentIndex(max(0, shape_index))
            self.on_subtitle_background_width_changed()
            if hasattr(self, "subtitle_background_radius_spin"):
                self.subtitle_background_radius_spin.setValue(int(state.get("background_radius", 0)))
        if hasattr(self, "subtitle_outline_cb"):
            self.subtitle_outline_cb.setChecked(bool(state.get("outline", self.subtitle_outline_cb.isChecked())))
        if hasattr(self, "subtitle_bg_alpha_spin"):
            self.subtitle_bg_alpha_spin.setValue(float(state.get("background_alpha", self.subtitle_bg_alpha_spin.value())))
        if hasattr(self, "subtitle_background_padding_spin"):
            self.subtitle_background_padding_spin.setValue(
                int(state.get("background_padding", self.subtitle_background_padding_spin.value()))
            )
        self.subtitle_bold_cb.setChecked(bool(state.get("bold", self.subtitle_bold_cb.isChecked())))
        if hasattr(self, "subtitle_speaker_colors_cb"):
            self.subtitle_speaker_colors_cb.setChecked(
                bool(state.get("speaker_colors", self.subtitle_speaker_colors_cb.isChecked()))
            )
        self.subtitle_keyword_highlight_cb.setChecked(
            bool(state.get("auto_keyword_highlight", self.subtitle_keyword_highlight_cb.isChecked()))
        )
        self.subtitle_highlight_color_combo.setCurrentText(
            str(state.get("highlight_color", self.subtitle_highlight_color_combo.currentText()))
        )
        self.subtitle_highlight_mode_combo.setCurrentText(
            str(state.get("highlight_mode", self.subtitle_highlight_mode_combo.currentText()))
        )
        if hasattr(self, "subtitle_single_line_cb") and "single_line" in state:
            self.subtitle_single_line_cb.setChecked(bool(state.get("single_line")))
        if hasattr(self, "subtitle_words_per_segment_spin") and "single_line_words" in state:
            try:
                self.subtitle_words_per_segment_spin.setValue(int(state.get("single_line_words", 4)))
            except Exception:
                pass
        position = dict(state.get("position") or {})
        if position:
            mode_combo = getattr(self, "subtitle_position_mode_combo", None)
            if mode_combo is not None:
                index = mode_combo.findData(str(position.get("position_mode", "anchor")))
                if index >= 0:
                    mode_combo.setCurrentIndex(index)
            align_combo = getattr(self, "subtitle_align_combo", None)
            if align_combo is not None:
                align_combo.setCurrentText(str(position.get("alignment_label", align_combo.currentText())))
            for widget_name, value_key in (
                ("subtitle_bottom_offset_spin", "margin_v"),
                ("subtitle_x_offset_spin", "x_offset"),
                ("subtitle_custom_x_spin", "custom_position_x"),
                ("subtitle_custom_y_spin", "custom_position_y"),
            ):
                widget = getattr(self, widget_name, None)
                if widget is not None and value_key in position:
                    widget.setValue(int(position[value_key]))
            self.on_subtitle_position_mode_changed()

    def _capture_subtitle_custom_style_state(self) -> None:
        self._subtitle_custom_style_state = self._current_subtitle_style_controls_state()

    def on_subtitle_style_control_edited(self, *_args):
        if getattr(self, "_subtitle_preset_apply_in_progress", False):
            return
        self._capture_subtitle_custom_style_state()
        custom_radio = getattr(self, "subtitle_preset_custom_radio", None)
        if custom_radio is not None and not custom_radio.isChecked():
            custom_radio.blockSignals(True)
            custom_radio.setChecked(True)
            custom_radio.blockSignals(False)
            self.on_subtitle_preset_changed()
        if getattr(self, "current_project_state", None) is not None:
            self.schedule_timeline_project_persist()

    def _read_saved_subtitle_style_presets(self) -> dict:
        raw_value = self.settings.value("saved_subtitle_styles", "{}")
        try:
            parsed = json.loads(raw_value) if isinstance(raw_value, str) else dict(raw_value)
        except Exception:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}

    def refresh_saved_subtitle_style_presets(self):
        if not hasattr(self, "saved_subtitle_style_combo"):
            return
        saved = self._read_saved_subtitle_style_presets()
        self.saved_subtitle_style_combo.blockSignals(True)
        self.saved_subtitle_style_combo.clear()
        self.saved_subtitle_style_combo.addItem("My Presets", "")
        for name in sorted(saved.keys(), key=str.lower):
            self.saved_subtitle_style_combo.addItem(name, name)
        self.saved_subtitle_style_combo.setCurrentIndex(0)
        self.saved_subtitle_style_combo.blockSignals(False)

    def save_current_subtitle_style_preset(self):
        name, ok = QInputDialog.getText(self, "Save Style", "Preset name:")
        if not ok or not (name or "").strip():
            return
        preset_name = name.strip()
        saved = self._read_saved_subtitle_style_presets()
        saved[preset_name] = self._saved_subtitle_style_payload()
        self.settings.setValue("saved_subtitle_styles", json.dumps(saved, ensure_ascii=False))
        self.refresh_saved_subtitle_style_presets()
        idx = self.saved_subtitle_style_combo.findData(preset_name)
        if idx >= 0:
            self.saved_subtitle_style_combo.setCurrentIndex(idx)

    def load_selected_subtitle_style_preset(self, index: int):
        if index <= 0:
            return
        preset_name = self.saved_subtitle_style_combo.itemData(index)
        saved = self._read_saved_subtitle_style_presets()
        preset = saved.get(preset_name or "")
        if not isinstance(preset, dict):
            return

        key = str(preset.get("preset", "tiktok")).lower()
        if key == "youtube":
            self.subtitle_preset_youtube_radio.setChecked(True)
        elif key == "minimal":
            self.subtitle_preset_minimal_radio.setChecked(True)
        elif key == "custom" and getattr(self, "subtitle_preset_custom_radio", None):
            self.subtitle_preset_custom_radio.setChecked(True)
        else:
            self.subtitle_preset_tiktok_radio.setChecked(True)

        self.subtitle_font_combo.setCurrentText(str(preset.get("font", self.subtitle_font_combo.currentText())))
        self.subtitle_font_size_spin.setValue(int(preset.get("size", self.subtitle_font_size_spin.value())))
        self.subtitle_color_hex = str(preset.get("color", self.subtitle_color_hex)).upper()
        self.subtitle_color_btn.setText(self.subtitle_color_hex)
        self.subtitle_background_color_hex = str(preset.get("background_color", getattr(self, "subtitle_background_color_hex", "#000000"))).upper()
        if hasattr(self, "subtitle_background_color_btn"):
            self.subtitle_background_color_btn.setText(self.subtitle_background_color_hex)
        self.subtitle_animation_combo.setCurrentText(str(preset.get("animation", self.subtitle_animation_combo.currentText())))
        self.subtitle_animation_time_spin.setValue(float(preset.get("animation_time", self.subtitle_animation_time_spin.value())))
        karaoke_mode = str(preset.get("karaoke_timing_mode", self.subtitle_karaoke_timing_combo.currentData() or "vietnamese"))
        karaoke_index = self.subtitle_karaoke_timing_combo.findData(karaoke_mode)
        if karaoke_index >= 0:
            self.subtitle_karaoke_timing_combo.setCurrentIndex(karaoke_index)
        self.subtitle_background_cb.setChecked(bool(preset.get("background", self.subtitle_background_cb.isChecked())))
        if hasattr(self, "subtitle_outline_cb"):
            self.subtitle_outline_cb.setChecked(bool(preset.get("outline", self.subtitle_outline_cb.isChecked())))
        if hasattr(self, "subtitle_bg_alpha_spin"):
            self.subtitle_bg_alpha_spin.setValue(float(preset.get("background_alpha", self.subtitle_bg_alpha_spin.value())))
        self.subtitle_bold_cb.setChecked(bool(preset.get("bold", self.subtitle_bold_cb.isChecked())))
        self.subtitle_keyword_highlight_cb.setChecked(bool(preset.get("auto_keyword_highlight", self.subtitle_keyword_highlight_cb.isChecked())))
        self.subtitle_highlight_color_combo.setCurrentText(str(preset.get("highlight_color", self.subtitle_highlight_color_combo.currentText())))
        self.subtitle_highlight_mode_combo.setCurrentText(str(preset.get("highlight_mode", self.subtitle_highlight_mode_combo.currentText())))
        self._capture_subtitle_custom_style_state()
        self.on_subtitle_preset_changed()
