import os
import re
import hashlib
from PySide6.QtWidgets import (
    QLineEdit,
                             QTextEdit, QColorDialog)
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QKeySequence, QPixmap

from helpers import (
    build_guidance_state,
    build_preview_context_text,
    build_workflow_hint,
    get_export_button_label,
    get_output_mode_key,
)
from utils.file_dialog_utils import (
    cleanup_file_if_exists as cleanup_file_if_exists_impl,
)
from features.voice_catalog import _default_asr_engine
from utils.media_utils import (
    refresh_video_dimensions as refresh_video_dimensions_impl,
    update_frame_preview_thumbnail as update_frame_preview_thumbnail_impl,
)

from video_processor import get_video_dimensions



class PreviewConfigurationMixin:
    def _enable_post_pipeline_preview_assets(self, *, refresh: bool = True):
        self._allow_post_pipeline_preview_assets = True
        if refresh:
            self.refresh_timeline_waveform()
            self.refresh_timeline_video_thumbnails()

    def resolve_background_audio_path(self) -> str:
        manual_candidate = self.bg_music_edit.text().strip() if hasattr(self, "bg_music_edit") else ""
        if manual_candidate:
            normalized = self._normalize_local_file_path(manual_candidate)
            if normalized and os.path.exists(normalized):
                self.last_music_path = normalized
                self.processed_artifacts["music"] = normalized
                return normalized

        audio_mode = self.get_audio_handling_mode()
        state_artifacts = getattr(getattr(self, "current_project_state", None), "artifacts", {}) if getattr(self, "current_project_state", None) else {}
        candidates = []
        if audio_mode == "clean":
            candidates.extend(
                [
                    getattr(self, "last_music_path", ""),
                    state_artifacts.get("music", ""),
                    getattr(self, "last_extracted_audio", ""),
                    state_artifacts.get("extracted_audio", ""),
                ]
            )
        else:
            candidates.extend(
                [
                    getattr(self, "last_extracted_audio", ""),
                    state_artifacts.get("extracted_audio", ""),
                    getattr(self, "last_music_path", ""),
                    state_artifacts.get("music", ""),
                ]
            )
        for candidate in candidates:
            normalized = self._normalize_local_file_path(candidate)
            if normalized and os.path.exists(normalized):
                if audio_mode == "clean":
                    self.last_music_path = normalized
                    self.processed_artifacts["music"] = normalized
                else:
                    self.processed_artifacts["background_source"] = normalized
                return normalized
        return ""

    def has_reusable_voice_inputs(self) -> bool:
        state = self.ensure_current_project()
        if state and not self.translated_text.toPlainText().strip():
            self.load_project_context(state)
        translated_srt = self.translated_text.toPlainText().strip()
        if not translated_srt:
            return False
        return bool(self.parse_srt_to_segments(translated_srt))

    def schedule_auto_frame_preview(self):
        if not bool(getattr(self, "_allow_post_pipeline_preview_assets", False)):
            return
        if not hasattr(self, "auto_preview_frame_cb") or not self.auto_preview_frame_cb.isChecked():
            return
        if self.auto_preview_frame_cb.isHidden():
            return
        if getattr(self, "_pipeline_active", False):
            return
        if not (self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()) or not self.get_active_segments():
            return
        self.frame_preview_status_label.setText("Refreshing exact frame preview...")
        self.auto_frame_preview_timer.start()

    def trigger_auto_frame_preview(self):
        self.start_exact_frame_preview(show_dialog=False)

    def schedule_seek_frame_preview(self):
        if not bool(getattr(self, "_allow_post_pipeline_preview_assets", False)):
            return
        if not hasattr(self, "auto_preview_frame_cb") or not self.auto_preview_frame_cb.isChecked():
            return
        if self.auto_preview_frame_cb.isHidden():
            return
        if getattr(self, "_pipeline_active", False):
            return
        if self.media_player.is_playing():
            return
        if not (self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()) or not self.get_active_segments():
            return
        self.frame_preview_status_label.setText("Updating exact frame preview for the selected timeline position...")
        self.seek_frame_preview_timer.start()

    def trigger_seek_frame_preview(self):
        if self.media_player.is_playing():
            return
        self.start_exact_frame_preview(show_dialog=False)

    def update_frame_preview_thumbnail(self, image_path: str):
        widget = getattr(self, "frame_preview_image_label", None)
        if widget is not None and hasattr(widget, "set_frame_image"):
            if hasattr(self, "video_view") and self.video_view is not None:
                widget.set_video_dimensions(
                    int(getattr(self.video_view, "video_source_width", 0) or 0),
                    int(getattr(self.video_view, "video_source_height", 0) or 0),
                )
                widget.set_preview_aspect_ratio(getattr(self.video_view, "preview_aspect_key", "source"))
                widget.set_preview_scale_mode(getattr(self.video_view, "preview_scale_mode", "fit"))
                focus_x, focus_y = self.get_output_fill_focus()
                widget.set_preview_fill_focus(focus_x, focus_y)
            widget.set_frame_image(image_path)
            return
        update_frame_preview_thumbnail_impl(self, image_path, QPixmap, Qt)

    def show_filter_thumbnail_preview(self, image_path: str):
        already_visible = bool(getattr(self, "_filter_thumbnail_visible", False))
        self._filter_thumbnail_visible = True
        if already_visible:
            self.update_frame_preview_thumbnail(image_path)
            if hasattr(self, "frame_preview_badge_label"):
                self._position_frame_preview_badge()
                self.frame_preview_badge_label.show()
            return
        self._suspend_preview_region_tools_for_filter()
        if hasattr(self, "preview_context_label"):
            self.preview_context_label.hide()
        if hasattr(self, "frame_preview_status_label"):
            self.frame_preview_status_label.hide()
        if hasattr(self, "frame_preview_image_label"):
            target_height = int(getattr(self, "_filter_thumbnail_target_height", 320) or 320)
            if hasattr(self, "video_view") and self.video_view is not None:
                live_height = int(self.video_view.height() or 0)
                if live_height > 0:
                    target_height = max(320, live_height)
            self._filter_thumbnail_target_height = target_height
            if hasattr(self.frame_preview_image_label, "setMinimumHeight"):
                self.frame_preview_image_label.setMinimumHeight(target_height)
            if hasattr(self.frame_preview_image_label, "setMaximumHeight"):
                self.frame_preview_image_label.setMaximumHeight(target_height)
            self.frame_preview_image_label.show()
        if hasattr(self, "video_view"):
            self.video_view.hide()
        self._force_hide_ocr_overlay_for_filter()
        self.update_frame_preview_thumbnail(image_path)
        if hasattr(self, "frame_preview_badge_label"):
            self._position_frame_preview_badge()
            self.frame_preview_badge_label.show()
        QTimer.singleShot(0, self._force_hide_ocr_overlay_for_filter)

    def hide_filter_thumbnail_preview(self):
        self._filter_thumbnail_visible = False
        if hasattr(self, "frame_preview_badge_label"):
            self.frame_preview_badge_label.hide()
        if hasattr(self, "frame_preview_image_label"):
            if hasattr(self.frame_preview_image_label, "setMinimumHeight"):
                self.frame_preview_image_label.setMinimumHeight(0)
            if hasattr(self.frame_preview_image_label, "setMaximumHeight"):
                self.frame_preview_image_label.setMaximumHeight(16777215)
            if hasattr(self.frame_preview_image_label, "clear_frame_image"):
                self.frame_preview_image_label.clear_frame_image()
            self.frame_preview_image_label.hide()
        if hasattr(self, "frame_preview_status_label"):
            self.frame_preview_status_label.hide()
        if hasattr(self, "preview_context_label"):
            self.preview_context_label.hide()
        if hasattr(self, "video_view"):
            self.video_view.show()
        self._restore_preview_region_tools_after_filter()

    def _suspend_preview_region_tools_for_filter(self):
        self._suspend_ocr_overlay = True
        self._filter_preview_blur_was_checked = bool(
            hasattr(self, "blur_area_btn") and self.blur_area_btn.isChecked()
        )
        overlay = getattr(self, "ocr_region_overlay", None)
        self._filter_preview_ocr_was_editable = bool(getattr(overlay, "_editable", False)) if overlay is not None else False

        if hasattr(self, "blur_area_btn"):
            self.blur_area_btn.setEnabled(False)
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_blur_edit_enabled"):
            self.video_view.set_blur_edit_enabled(False)
        if overlay is not None:
            overlay.set_editable(False)
            overlay.hide()

    def _force_hide_ocr_overlay_for_filter(self):
        if not bool(getattr(self, "_filter_thumbnail_visible", False)):
            return
        overlay = getattr(self, "ocr_region_overlay", None)
        if overlay is not None:
            overlay.set_editable(False)
            overlay.hide()

    def _restore_preview_region_tools_after_filter(self):
        self._suspend_ocr_overlay = False
        if hasattr(self, "blur_area_btn"):
            self.blur_area_btn.setEnabled(True)
        self._sync_blur_controls()

        overlay = getattr(self, "ocr_region_overlay", None)
        if overlay is not None:
            self._update_ocr_overlay()
            if (
                bool(getattr(self, "_filter_preview_ocr_was_editable", False))
                and os.getenv("TRANSCRIPTION_ENGINE", _default_asr_engine()).strip().lower() == "ocr"
            ):
                overlay.set_editable(True)
                overlay.sync_to_view()

    def _position_frame_preview_badge(self):
        badge = getattr(self, "frame_preview_badge_label", None)
        if badge is None:
            return
        host = None
        if getattr(self, "_filter_thumbnail_visible", False):
            host = getattr(self, "frame_preview_image_label", None)
        if host is None or not host.isVisible():
            host = getattr(self, "video_view", None)
        if host is None:
            return
        badge.adjustSize()
        content_rect = None
        if hasattr(host, "get_video_content_rect"):
            try:
                content_rect = host.get_video_content_rect()
            except Exception:
                content_rect = None
        if content_rect is not None and content_rect.width() > 0 and content_rect.height() > 0:
            x = host.x() + content_rect.right() - badge.width() - 14
            y = host.y() + content_rect.top() + 14
        else:
            x = host.x() + max(12, host.width() - badge.width() - 14)
            y = host.y() + 14
        badge.move(int(x), int(y))
        badge.raise_()

    def _update_ocr_overlay(self):
        overlay = getattr(self, "ocr_region_overlay", None)
        if overlay is None:
            return
        is_ocr = os.getenv("TRANSCRIPTION_ENGINE", _default_asr_engine()).strip().lower() == "ocr"
        alternate_ocr_active = bool(getattr(self, "_alternate_ocr_range_pending", None))
        btn = getattr(self, "ocr_region_btn", None)
        if btn:
            btn.setVisible(is_ocr)
            btn.blockSignals(True)
            btn.setChecked(bool(getattr(self, "_ocr_overlay_visible", True)))
            btn.blockSignals(False)
        if not is_ocr and not alternate_ocr_active:
            overlay._requested_visible = False
            overlay.hide()
            overlay.set_editable(False)
        else:
            overlay._requested_visible = bool(alternate_ocr_active or getattr(self, "_ocr_overlay_visible", True))
            if bool(alternate_ocr_active or getattr(self, "_ocr_overlay_visible", True)):
                overlay.set_editable(True)
                overlay.sync_to_view()
            else:
                overlay.set_editable(False)
                overlay.hide()

    def toggle_ocr_overlay_visibility(self, checked: bool):
        self._ocr_overlay_visible = bool(checked)
        overlay = getattr(self, "ocr_region_overlay", None)
        if overlay is not None:
            overlay._requested_visible = bool(checked)
            overlay.set_editable(bool(checked))
            if checked:
                overlay.sync_to_view()
                overlay.raise_()
                QTimer.singleShot(0, overlay.sync_to_view)
            else:
                overlay.hide()
        self._update_ocr_overlay()

    def cleanup_file_if_exists(self, path: str):
        cleanup_file_if_exists_impl(path)

    def get_workspace_temp_root(self, create: bool = False) -> str:
        root = os.path.normpath(os.path.join(self.workspace_root, "temp"))
        if create:
            os.makedirs(root, exist_ok=True)
        return root

    def _cleanup_temp_root(self) -> None:
        root = self.get_workspace_temp_root()
        if not os.path.isdir(root):
            return
        for entry in os.listdir(root):
            fpath = os.path.join(root, entry)
            if not os.path.isfile(fpath):
                continue
            try:
                os.remove(fpath)
            except OSError:
                pass

    def get_current_project_temp_key(self) -> str:
        state = getattr(self, "current_project_state", None)
        project_id = str(getattr(state, "project_id", "") or "").strip()
        if project_id:
            return project_id
        project_root = str(getattr(state, "project_root", "") or "").strip()
        if project_root:
            return os.path.basename(os.path.normpath(project_root))
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        if video_path:
            video_name = os.path.splitext(os.path.basename(video_path))[0] or "project"
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", video_name).strip("_").lower() or "project"
            digest = hashlib.sha1(os.path.abspath(video_path).encode("utf-8")).hexdigest()[:8]
            return f"{slug}_{digest}"
        return "global"

    def get_project_temp_root(self, create: bool = False) -> str:
        root = os.path.normpath(
            os.path.join(
                self.get_workspace_temp_root(create=create),
                "projects",
                self.get_current_project_temp_key(),
            )
        )
        if create:
            os.makedirs(root, exist_ok=True)
        return root

    def get_project_temp_path(self, *parts: str, create_parent: bool = False) -> str:
        path = os.path.normpath(os.path.join(self.get_project_temp_root(create=create_parent), *parts))
        if create_parent:
            parent = os.path.dirname(path) if os.path.splitext(path)[1] else path
            if parent:
                os.makedirs(parent, exist_ok=True)
        return path

    def get_project_temp_dir(self, *parts: str) -> str:
        path = self.get_project_temp_path(*parts, create_parent=True)
        os.makedirs(path, exist_ok=True)
        return path
    def get_output_mode_key(self):
        if not hasattr(self, "output_mode_combo"):
            return "both"
        return get_output_mode_key(self.output_mode_combo.currentText())

    def get_final_dub_audio_path(self) -> str:
        """Return the resolved path to the generated or selected dub audio."""
        candidates = [
            getattr(self, "last_mixed_vi_path", ""),
            getattr(self, "last_voice_vi_path", ""),
            self.processed_artifacts.get("mixed_vi", ""),
            self.processed_artifacts.get("voice_vi", ""),
        ]
        if hasattr(self, "current_project_state") and self.current_project_state:
            artifacts = getattr(self.current_project_state, "artifacts", {}) or {}
            candidates.extend([
                artifacts.get("mixed_vi", ""),
                artifacts.get("voice_vi", ""),
            ])
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return ""

    def get_output_quality_key(self):
        if not hasattr(self, "output_quality_combo"):
            return "source"
        value = self.output_quality_combo.currentData()
        if value:
            return str(value).strip().lower()
        return str(self.output_quality_combo.currentText() or "source").strip().lower() or "source"

    def get_export_preset(self) -> str:
        combo = getattr(self, "output_preset_combo", None)
        value = str(combo.currentData() if combo is not None else "balanced").strip().lower()
        return value if value in {"fast", "balanced", "max"} else "balanced"

    def get_output_bitrate_kbps(self) -> int:
        spin = getattr(self, "output_bitrate_spin", None)
        try:
            return max(500, int(spin.value())) if spin is not None else 2000
        except (TypeError, ValueError):
            return 2000

    def get_output_fps_key(self):
        if not hasattr(self, "output_fps_combo"):
            return "source"
        value = self.output_fps_combo.currentData()
        if value:
            return str(value).strip().lower()
        return str(self.output_fps_combo.currentText() or "source").strip().lower() or "source"

    def get_output_ratio_key(self):
        if not hasattr(self, "output_ratio_combo"):
            return "source"
        value = self.output_ratio_combo.currentData()
        if value:
            return str(value).strip().lower()
        return str(self.output_ratio_combo.currentText() or "source").strip().lower() or "source"

    def get_output_scale_mode_key(self):
        if hasattr(self, "video_view") and hasattr(self.video_view, "preview_scale_mode"):
            view_mode = str(getattr(self.video_view, "preview_scale_mode", "") or "").strip().lower()
            if view_mode in ("fit", "fill"):
                return view_mode
        if hasattr(self, "output_scale_mode_combo"):
            value = self.output_scale_mode_combo.currentData()
            if value:
                return str(value).strip().lower()
            text_val = str(self.output_scale_mode_combo.currentText() or "").strip().lower()
            if text_val in ("fit", "fill"):
                return text_val
        return "fit"

    def get_output_fill_focus(self):
        if hasattr(self, "video_view") and hasattr(self.video_view, "get_preview_fill_focus"):
            return self.video_view.get_preview_fill_focus()
        return (0.5, 0.5)

    def _video_filter_presets(self):
        return {
            "original": {
                "brightness": 0,
                "contrast": 0,
                "saturation": 0,
                "temperature": 0,
                "highlights": 0,
                "shadows": 0,
            },
            "bright": {
                "brightness": 20,
                "contrast": 5,
                "saturation": 5,
                "temperature": 0,
                "highlights": -10,
                "shadows": 20,
            },
            "warm": {
                "brightness": 10,
                "contrast": 5,
                "saturation": 10,
                "temperature": 25,
                "highlights": -5,
                "shadows": 10,
            },
            "vivid": {
                "brightness": 10,
                "contrast": 20,
                "saturation": 25,
                "temperature": 0,
                "highlights": -5,
                "shadows": 5,
            },
            "cool": {
                "brightness": 0,
                "contrast": 15,
                "saturation": 5,
                "temperature": -20,
                "highlights": -10,
                "shadows": -5,
            },
            "soft": {
                "brightness": 10,
                "contrast": -12,
                "saturation": 5,
                "temperature": 10,
                "highlights": -15,
                "shadows": 15,
            },
        }

    def _video_filter_lut_map(self):
        return self.video_filter_controller.video_filter_lut_map()

    def _video_filter_fields(self):
        return self.video_filter_controller.video_filter_fields()

    def _clamp_video_filter_value(self, value):
        return self.video_filter_controller.clamp_video_filter_value(value)

    def _default_video_filter_overrides(self):
        return self.video_filter_controller.default_video_filter_overrides()

    def _default_video_filter_modified_flags(self):
        return self.video_filter_controller.default_video_filter_modified_flags()

    def _normalize_video_filter_preset_key(self, preset_key):
        return self.video_filter_controller.normalize_video_filter_preset_key(preset_key)

    def _get_video_filter_base_values(self, preset_key=None):
        return self.video_filter_controller.get_video_filter_base_values(preset_key)

    def _get_video_filter_scaled_values(self, preset_key=None, intensity=None):
        return self.video_filter_controller.get_video_filter_scaled_values(preset_key, intensity)

    def _get_video_filter_effective_values(self, preset_key=None, intensity=None, overrides=None, modified_flags=None):
        return self.video_filter_controller.get_video_filter_effective_values(preset_key, intensity, overrides, modified_flags)

    def _refresh_video_filter_ui(self):
        return self.video_filter_controller.refresh_video_filter_ui()

    def _update_video_filter_slider_visual_state(self, field, slider):
        return self.video_filter_controller.update_video_filter_slider_visual_state(field, slider)

    def set_video_filter_state(self, preset_key="original", intensity=75, overrides=None, modified_flags=None):
        return self.video_filter_controller.set_video_filter_state(preset_key, intensity, overrides, modified_flags)

    def on_video_filter_preset_selected(self, preset_key):
        return self.video_filter_controller.on_video_filter_preset_selected(preset_key)

    def on_video_filter_intensity_changed(self, value):
        return self.video_filter_controller.on_video_filter_intensity_changed(value)

    def on_video_filter_adjust_changed(self, field_key, value):
        return self.video_filter_controller.on_video_filter_adjust_changed(field_key, value)

    def reset_video_filters(self):
        return self.video_filter_controller.reset_video_filters()

    def reset_video_filter_adjustments(self):
        return self.video_filter_controller.reset_video_filter_adjustments()

    def get_video_filter_state(self):
        return self.video_filter_controller.get_video_filter_state()

    def has_active_video_filters(self):
        return self.video_filter_controller.has_active_video_filters()

    def on_output_ratio_changed(self, *_args):
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_preview_aspect_ratio"):
            self.video_view.set_preview_aspect_ratio(self.get_output_ratio_key())
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_preview_scale_mode"):
            self.video_view.set_preview_scale_mode(self.get_output_scale_mode_key())
        self._sync_preview_framing_to_player()
        self._sync_preview_output_canvas_dimensions()
        self.update_subtitle_preview_style()
        # update_subtitle_preview_style establishes the new output canvas
        # render dimensions. Refresh Text afterwards so it cannot reuse the
        # previous Ratio's height/scale payload.
        self._refresh_text_layer_preview(getattr(getattr(self, "timeline", None), "_selected_layer_id", ""))
        self.apply_preview_blur_region()
        self.refresh_ui_state()

    def on_output_scale_mode_changed(self, *_args):
        scale_key = self.get_output_scale_mode_key()
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_preview_scale_mode"):
            self.video_view.set_preview_scale_mode(scale_key)
        self._sync_preview_scale_btn(scale_key)
        self._sync_preview_framing_to_player()
        self._sync_preview_output_canvas_dimensions()
        self.update_subtitle_preview_style()
        self._refresh_text_layer_preview(getattr(getattr(self, "timeline", None), "_selected_layer_id", ""))
        self.apply_preview_blur_region()
        self.refresh_ui_state()

    def _sync_preview_scale_btn(self, scale_mode: str = ""):
        btn = getattr(self, "preview_scale_btn", None)
        if btn is not None:
            mode = str(scale_mode or self.get_output_scale_mode_key() or "fit").strip().upper()
            btn.setText("FILL" if mode == "FILL" else "FIT")

    def toggle_preview_scale_mode(self):
        current = self.get_output_scale_mode_key()
        target = "fill" if current == "fit" else "fit"
        combo = getattr(self, "output_scale_mode_combo", None)
        if combo is not None:
            idx = combo.findData(target)
            if idx < 0:
                idx = combo.findText(target.capitalize())
            if idx >= 0:
                combo.setCurrentIndex(idx)
                return
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_preview_scale_mode"):
            self.video_view.set_preview_scale_mode(target)
        self._sync_preview_scale_btn(target)
        self._sync_preview_framing_to_player()
        self._sync_preview_output_canvas_dimensions()
        self.update_subtitle_preview_style()
        self.refresh_ui_state()

    def on_preview_framing_changed(self, *_args):
        self._sync_preview_framing_to_player()
        self._refresh_text_layer_preview(getattr(getattr(self, "timeline", None), "_selected_layer_id", ""))
        self.apply_preview_blur_region()
        self.refresh_ui_state()

    def reset_preview_framing(self):
        if hasattr(self, "video_view") and hasattr(self.video_view, "reset_preview_fill_focus"):
            self.video_view.reset_preview_fill_focus()
        self._sync_preview_framing_to_player()
        self.apply_preview_blur_region()
        self.refresh_ui_state()

    def get_audio_handling_mode(self):
        if not hasattr(self, "audio_handling_combo"):
            return "fast"
        value = self.audio_handling_combo.currentData()
        if value:
            return str(value).strip().lower()
        return "fast"

    def is_speaker_diarization_enabled(self) -> bool:
        engine = str(os.getenv("TRANSCRIPTION_ENGINE", _default_asr_engine()) or "").strip().lower()
        return bool(
            engine != "ocr"
            and hasattr(self, "speaker_diarization_cb")
            and self.speaker_diarization_cb.isChecked()
        )

    def get_speaker_diarization_num_speakers(self) -> int:
        combo = getattr(self, "speaker_diarization_speakers_combo", None)
        if combo is None:
            return -1
        try:
            value = int(combo.currentData())
            return value if value >= 2 else -1
        except (TypeError, ValueError):
            return -1

    def update_speaker_diarization_availability(self) -> None:
        checkbox = getattr(self, "speaker_diarization_cb", None)
        hint = getattr(self, "speaker_diarization_hint_label", None)
        card = getattr(self, "speaker_diarization_card", None)
        speakers_combo = getattr(self, "speaker_diarization_speakers_combo", None)
        if checkbox is None:
            return
        engine = str(os.getenv("TRANSCRIPTION_ENGINE", _default_asr_engine()) or "").strip().lower()
        available = engine != "ocr"
        if not available:
            checkbox.setChecked(False)
        checkbox.setEnabled(available)
        checkbox.setVisible(available)
        if card is not None:
            card.setVisible(available)
        if speakers_combo is not None:
            speakers_combo.setEnabled(available)
        if hint is not None:
            hint.setVisible(available)
        checkbox.setToolTip(
            "Detect speakers offline with Sherpa-ONNX and color TS1 segments."
            if available else "Speaker diarization is unavailable when Video (OCR) is selected."
        )

    def get_source_language_code(self):
        if not hasattr(self, "lang_whisper_combo"):
            return "auto"
        value = self.lang_whisper_combo.currentData()
        if value:
            return str(value)
        return self.lang_whisper_combo.currentText().strip() or "auto"

    def get_target_language_code(self):
        if not hasattr(self, "lang_target_combo"):
            return "vi"
        value = self.lang_target_combo.currentData()
        if value:
            return str(value)
        label = self.lang_target_combo.currentText().strip().lower()
        if "english" in label:
            return "en"
        return "vi"

    def is_ai_polish_enabled(self):
        # The old "Use AI translation" checkbox was removed when provider
        # selection moved into Settings.  A configured cloud/API provider is
        # now the explicit request to use AI; only selecting Google Translate
        # bypasses the AI branch.  Keeping the legacy checkbox fallback makes
        # older embedded UI layouts harmless.
        provider = str(os.getenv("OPENAI_PROVIDER") or "google").strip().lower()
        if provider in {"gemini", "google_ai_studio", "openai", "ollama"}:
            return True
        legacy_checkbox = getattr(self, "translator_ai_cb", None)
        return bool(legacy_checkbox and legacy_checkbox.isChecked())

    def is_skip_translation(self):
        # Translation is always part of the fixed Subtitle + Voice workflow.
        return False

    def is_ai_dubbing_rewrite_enabled(self):
        return bool(getattr(self, "ai_dubbing_rewrite_cb", None) and self.ai_dubbing_rewrite_cb.isChecked())

    def get_ai_dubbing_style_instruction(self):
        return self.get_ai_style_instruction()

    def get_ai_style_instruction(self):
        style_parts = []
        preset_key = ""
        target_lang = str(self.get_target_language_code() or "vi").strip().lower()
        if hasattr(self, "translation_style_preset_combo"):
            preset_key = str(self.translation_style_preset_combo.currentData() or "").strip()

        if target_lang.startswith("vi"):
            tutien_prompt = "Thể loại Recap Tu Tiên / Kiếm Hiệp: Dịch chuẩn xưng hô Hán Việt theo vai vế ngữ cảnh (Sư tôn/Đồ nhi, Tiền bối/Vãn bối, Huynh đệ/Tỷ muội, Đạo hữu/Tại hạ, Tông chủ/Trưởng lão). Sử dụng chính xác thuật ngữ tu chân (công pháp, linh đan, đan điền, độ kiếp, pháp bảo, tông môn, linh khí, thần thức). Câu văn ngắn gọn súc tích (khoảng 25-35 ký tự/dòng, tối đa 2 dòng), nhịp điệu nhanh dứt khoát, dễ đọc lướt theo video recap."
        else:
            tutien_prompt = f"Cultivation/Wuxia recap in {target_lang}: use established {target_lang} genre terminology, titles and role-based forms of address consistently. Keep names, factions, realms and power-system terms canonical across the video. Use concise, decisive, natural subtitle prose, at most two readable lines. Never insert Vietnamese Hán-Việt terms into this target language."
        preset_prompts = {
            "tutien_recap": tutien_prompt,
            "anime": f"Anime/Manga in {target_lang}: lively, emotional and natural for the characters' age and relationship. Preserve canonical names and franchise terminology consistently.",
            "drama": f"Cinematic drama in {target_lang}: natural, emotionally precise dialogue that preserves each character's personality, status and scene context.",
            "standard": f"Accurate, fluent and concise {target_lang}, written naturally for readable video subtitles.",
        }
        if preset_key in preset_prompts:
            style_parts.append(preset_prompts[preset_key])

        if hasattr(self, "translator_style_edit"):
            custom_style = self.translator_style_edit.text().strip()
            if custom_style:
                style_parts.append(custom_style)
        if hasattr(self, "subtitle_single_line_cb") and self.subtitle_single_line_cb.isChecked():
            style_parts.append("[subtitle_layout=single_line]")
        return " | ".join(part for part in style_parts if part).strip()

    def on_output_mode_changed(self, value: str):
        mode = self.get_output_mode_key()
        if getattr(self, "_filter_thumbnail_visible", False):
            self.hide_filter_thumbnail_preview()
        self.workflow_hint_label.setText(build_workflow_hint(mode, self.is_ai_polish_enabled()))

        show_voice = mode in ("voice", "both")
        if hasattr(self, "voice_section_card"):
            self.voice_section_card.setVisible(show_voice)
        if hasattr(self, "quick_preview_btn"):
            self.quick_preview_btn.setVisible(show_voice)
        if hasattr(self, "styled_preview_btn"):
            self.styled_preview_btn.setVisible(show_voice)
        self.mixed_audio_edit.setEnabled(show_voice)
        if hasattr(self, "use_generated_audio_radio"):
            self.use_generated_audio_radio.setVisible(show_voice)
        if hasattr(self, "use_existing_audio_radio"):
            self.use_existing_audio_radio.setVisible(show_voice)
        if hasattr(self, "browse_bg_music_btn"):
            self.browse_bg_music_btn.setVisible(show_voice)
        if hasattr(self, "browse_mixed_audio_btn"):
            self.browse_mixed_audio_btn.setVisible(show_voice)
        self.export_btn.setText(get_export_button_label(mode))
        self.refresh_ui_state()

    def on_left_panel_workflow_changed(self, index: int):
        # Filter thumbnail preview should only stay active while the Filter page is open.
        if int(index) != 4 and getattr(self, "_filter_thumbnail_visible", False):
            self.hide_filter_thumbnail_preview()

    def _workflow_dependency_state(self) -> dict:
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        has_video = bool(video_path and os.path.exists(video_path))
        return {
            "media": {"enabled": True, "reason": ""},
            "audio": {"enabled": has_video, "reason": "Select a video first to configure audio."},
            "language": {"enabled": has_video, "reason": "Select a video first to transcribe and translate."},
            "voice": {"enabled": has_video, "reason": "Select a video first to configure voice and audio."},
            "style": {"enabled": has_video, "reason": "Select a video first to style subtitle output."},
            "advanced": {"enabled": True, "reason": ""},
        }

    def update_workflow_availability(self):
        states = self._workflow_dependency_state()
        current_index = int(self.left_panel_stack.currentIndex()) if hasattr(self, "left_panel_stack") else 0
        page_order = ["media", "audio", "language", "voice", "style", "advanced"]

        for page_key, state in states.items():
            container = getattr(self, "workflow_page_containers", {}).get(page_key) if hasattr(self, "workflow_page_containers") else None
            hint = getattr(self, "workflow_page_hints", {}).get(page_key) if hasattr(self, "workflow_page_hints") else None
            tab_btn = getattr(self, "workflow_tab_buttons", {}).get(page_key) if hasattr(self, "workflow_tab_buttons") else None
            enabled = bool(state.get("enabled"))
            reason = str(state.get("reason", "") or "").strip()
            if container is not None:
                container.setEnabled(enabled)
            if hint is not None:
                hint.setText("" if enabled else reason)
                hint.setVisible(not enabled and bool(reason))
            if tab_btn is not None:
                tab_btn.setEnabled(enabled)
                tab_btn.style().unpolish(tab_btn)
                tab_btn.style().polish(tab_btn)
            rail_key = {"media": "source", "language": "captions"}.get(page_key, page_key)
            rail_button = getattr(self, "navigation_buttons", {}).get(rail_key)
            if rail_button is not None:
                rail_button.setEnabled(enabled)
                rail_button.setToolTip(f"Open {rail_key.title()} controls" if enabled else reason)

        active_key = page_order[current_index] if 0 <= current_index < len(page_order) else "media"
        active_state = states.get(active_key, {"enabled": True})
        if not active_state.get("enabled", True):
            for fallback_key in ("media", "advanced"):
                fallback_index = page_order.index(fallback_key)
                fallback_state = states.get(fallback_key, {"enabled": True})
                if fallback_state.get("enabled", True):
                    btn = getattr(self, "workflow_tab_buttons", {}).get(fallback_key) if hasattr(self, "workflow_tab_buttons") else None
                    if btn is not None:
                        btn.setChecked(True)
                    elif hasattr(self, "left_panel_stack"):
                        self.left_panel_stack.setCurrentIndex(fallback_index)
                    break

    def update_guidance_panel(self):
        guidance = build_guidance_state(
            video_path=self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text(),
            transcript_text=self.transcript_text.toPlainText(),
            translated_text=self.translated_text.toPlainText(),
            translated_srt_path=self.last_translated_srt_path,
            selected_audio_path=self.resolve_selected_audio_path(),
            mode=self.get_output_mode_key(),
            pipeline_active=getattr(self, "_pipeline_active", False),
            mode_label=self.output_mode_combo.currentText(),
        )
        self.update_preview_context_label(guidance["has_subtitles"], guidance["has_voice_audio"])

    def update_project_header(self):
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        state = getattr(self, "current_project_state", None)
        project_name = str(getattr(state, "display_name", "") or "").strip()
        if project_name:
            self.project_title_label.setText(f"Project: {project_name}")
            if hasattr(self, "upload_status_label"):
                if video_path:
                    self.upload_status_label.setText(f"[OK] {os.path.basename(video_path)} uploaded")
                else:
                    self.upload_status_label.setText("Project ready · add videos in Media Workflow")
        elif video_path:
            video_name = os.path.basename(video_path)
            self.project_title_label.setText(f"Project: {video_name}")
            if hasattr(self, "upload_status_label"):
                self.upload_status_label.setText(f"[OK] {video_name} uploaded")
        else:
            self.project_title_label.setText("Project: No video selected")
            if hasattr(self, "upload_status_label"):
                self.upload_status_label.setText("No video uploaded yet")

    def sync_left_panel_container_width(self):
        scroll_area = getattr(self, "left_panel_scroll_area", None)
        container = getattr(self, "left_panel_container", None)
        if not scroll_area or not container:
            return
        viewport_width = max(0, scroll_area.viewport().width())
        if viewport_width <= 0:
            return
        gutter = 10
        target_width = max(320, viewport_width - gutter)
        container.setMaximumWidth(target_width)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            scroll_area = getattr(self, "left_panel_scroll_area", None)
            if scroll_area and watched in (scroll_area, scroll_area.viewport(), scroll_area.verticalScrollBar()):
                QTimer.singleShot(0, self.sync_left_panel_container_width)
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Undo):
            focused = self.focusWidget()
            if isinstance(focused, (QTextEdit, QLineEdit)):
                super().keyPressEvent(event)
                return
            if self.undo_last_timeline_timing_edit():
                event.accept()
                return
        if event.matches(QKeySequence.Redo):
            focused = self.focusWidget()
            if isinstance(focused, (QTextEdit, QLineEdit)):
                super().keyPressEvent(event)
                return
            if self.redo_last_timeline_timing_edit():
                event.accept()
                return
        super().keyPressEvent(event)

    def toggle_controls_panel(self):
        # Hide-controls is disabled - the workflow panel is always visible.
        self.set_controls_panel_visible(True)

    def set_controls_panel_visible(self, visible: bool):
        # The workflow panel is always visible. Hide-controls is disabled.
        if hasattr(self, "left_panel_scroll_area"):
            self.left_panel_scroll_area.setVisible(True)
        QTimer.singleShot(0, self._resync_preview_region_overlays)

    def _resync_preview_region_overlays(self):
        try:
            self._sync_blur_controls()
        except Exception:
            pass
        try:
            self._update_ocr_overlay()
        except Exception:
            pass

    def update_progress_checklist(self):
        self.update_workflow_stage_badges()

    def _completed_translation_provider_label(self) -> str:
        """Return the provider recorded in completed translation segments.

        This intentionally reads the result metadata rather than Settings:
        an unavailable AI provider can finish a run through Google Translate.
        """
        models = list(getattr(self, "current_translated_segment_models", []) or [])
        provider_counts = {}
        for model in models:
            provider = str(getattr(model, "metadata", {}).get("translation_provider", "") or "").strip().lower()
            if provider:
                provider_counts[provider] = provider_counts.get(provider, 0) + 1
        if not provider_counts:
            return ""
        provider = max(provider_counts, key=provider_counts.get)
        names = {
            "google-web": "Google Translate",
            "google": "Google Translate",
            "gemini": "Google AI Studio",
            "google_ai_studio": "Google AI Studio",
            "openai": "OpenAI",
            "ollama": "Ollama",
        }
        return names.get(provider, provider.replace("-", " ").title())

    def update_workflow_stage_badges(self):
        """Reflect persisted workflow artifacts in the left-side milestones."""
        badges = getattr(self, "workflow_stage_badges", {}) or {}
        labels = getattr(self, "workflow_stage_labels", {}) or {}
        if not badges:
            return
        video_path = str(self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text() if hasattr(self, "video_path_edit") else "")).strip()
        state = getattr(self, "current_project_state", None)
        artifacts = getattr(state, "artifacts", {}) or {}
        steps = getattr(state, "steps", {}) or {}
        has_video = bool(video_path and os.path.exists(video_path))
        transcript = bool(self.current_segments) or bool(artifacts.get("transcript_segments"))
        # PrepareWorkflow writes a compatibility SRT even when translation is
        # intentionally skipped. Only a completed translation artifact/step
        # unlocks the next Step-by-Step action.
        translation_status = str(steps.get("translate_raw", "")).lower()
        # A retained translation artifact is useful for legacy projects, but
        # it must not make the phase look completed while a new translation
        # is running or after the user stopped it.
        translated = (
            False if translation_status in {"running", "failed"}
            else translation_status == "done" or bool(artifacts.get("translation_final"))
        )
        tts_skipped = bool(state and state.settings.get("tts_skipped", False))
        voice = not tts_skipped and bool(
            artifacts.get("voice_vi") or artifacts.get("mixed_vi") or self.last_voice_vi_path or self.last_mixed_vi_path
        )
        exported = bool(artifacts.get("final_video"))
        running = str(getattr(self, "_pipeline_step", "") or "") if getattr(self, "_pipeline_active", False) else ""
        values = {
            "prepare": (has_video, "prepare"),
            "transcript": (transcript, "prepare"),
            "translate": (translated, "translation"),
            "tts": (voice, "voiceover"),
            "export": (exported, "export"),
        }
        for key, (complete, running_step) in values.items():
            label = labels.get(key)
            if label is not None and key == "translate":
                provider = self._completed_translation_provider_label() if complete else ""
                label.setText(f"Translate — {provider}" if provider else "Translate")
            badge = badges.get(key)
            if badge is None:
                continue
            is_running = running == running_step or (key == "transcript" and running == "prepare")
            if is_running:
                text, color = "Processing…", "#f6c453"
            elif complete:
                text, color = "✓ Completed", "#6ee7d6"
            elif key == "tts" and translated:
                # A translated subtitle track is exportable without a dub.
                # Keep TTS available for later regeneration, but make its
                # optional nature obvious in the workflow sidebar.
                text, color = "Optional", "#8394aa"
            else:
                text, color = "Not started", "#8394aa"
            badge.setText(text)
            badge.setStyleSheet(f"color: {color}; font-weight: 700;")

        # Step-by-Step is deliberately linear until translation is complete.
        # Translation remains repeatable, like TTS: users often adjust the
        # provider, prompt, or source subtitles and need to run it again
        # without transcribing the video a second time.
        if hasattr(self, "_generate_transcript_action"):
            self._generate_transcript_action.setEnabled(has_video and not transcript and not self._pipeline_active)
        if hasattr(self, "_generate_translate_action"):
            self._generate_translate_action.setEnabled(transcript and not self._pipeline_active)
            self._generate_translate_action.setText("Re-translate" if translated else "Auto Translate")
        if hasattr(self, "_generate_import_translated_srt_action"):
            self._generate_import_translated_srt_action.setEnabled(has_video and not self._pipeline_active)
        if hasattr(self, "_generate_tts_action"):
            self._generate_tts_action.setEnabled(
                # TTS is intentionally repeatable: subtitle/voice edits may
                # require regenerating audio after this stage was completed.
                translated and not self._pipeline_active
                and self.get_output_mode_key() in ("voice", "both")
            )
        if hasattr(self, "_generate_tts_skip_action"):
            self._generate_tts_skip_action.setEnabled(translated and not self._pipeline_active)

    def update_preview_context_label(self, has_subtitles: bool, has_voice_audio: bool):
        subtitle_source = "Vietnamese review track" if self.current_translated_segments else ("original subtitle track" if self.current_segments else "no subtitle track yet")
        audio_source = "existing mixed audio" if self.using_existing_audio_source() else "generated Vietnamese voice"
        self.preview_context_label.setText(
            build_preview_context_text(
                video_ready=bool(self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()),
                has_subtitles=has_subtitles,
                has_voice_audio=has_voice_audio,
                subtitle_source=subtitle_source,
                audio_source=audio_source,
            )
        )

    def choose_subtitle_color(self):
        color = QColorDialog.getColor(QColor(self.subtitle_color_hex), self, "Choose Subtitle Color")
        if not color.isValid():
            return
        self.subtitle_color_hex = color.name().upper()
        self.subtitle_color_btn.setText(self.subtitle_color_hex)
        self.on_subtitle_style_control_edited()
        self.update_subtitle_preview_style()

    def choose_subtitle_background_color(self):
        current = getattr(self, "subtitle_background_color_hex", "#000000")
        color = QColorDialog.getColor(QColor(current), self, "Choose Subtitle Background Color")
        if not color.isValid():
            return
        self.subtitle_background_color_hex = color.name().upper()
        if hasattr(self, "subtitle_background_color_btn"):
            self.subtitle_background_color_btn.setText(self.subtitle_background_color_hex)
        self.on_subtitle_style_control_edited()
        self.update_subtitle_preview_style()

    def on_subtitle_background_width_changed(self, *_args):
        is_full_area = bool(
            hasattr(self, "subtitle_background_width_combo")
            and self.subtitle_background_width_combo.currentData() == "full_area"
        )
        hint = getattr(self, "subtitle_background_exact_hint", None)
        if hint is not None:
            hint.setVisible(is_full_area)
        # Shape selection was removed in favor of a consistent rounded
        # rectangle controlled by Corner radius.
        for name in ("subtitle_background_shape_label", "subtitle_background_shape_combo"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(False)
        self.update_subtitle_preview_style()

    def on_subtitle_font_scale_changed(self, _index: int = -1):
        """Translate the friendly percentage picker into the stored font size."""
        combo = getattr(self, "subtitle_font_scale_combo", None)
        spin = getattr(self, "subtitle_font_size_spin", None)
        if combo is None or spin is None:
            return
        percent = int(combo.currentData() or 100)
        spin.setValue(max(spin.minimum(), min(spin.maximum(), round(60 * percent / 100.0))))

    def sync_subtitle_font_scale_control(self, size: int | None = None):
        """Keep the visible selector honest when a preset/project sets a size."""
        combo = getattr(self, "subtitle_font_scale_combo", None)
        spin = getattr(self, "subtitle_font_size_spin", None)
        if combo is None or spin is None:
            return
        size = int(spin.value() if size is None else size)
        choices = [int(combo.itemData(index)) for index in range(combo.count())]
        if not choices:
            return
        nearest = min(choices, key=lambda percent: abs((60 * percent / 100.0) - size))
        index = combo.findData(nearest)
        if index >= 0 and index != combo.currentIndex():
            was_blocked = combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(was_blocked)

    def _subtitle_render_dimensions(self) -> tuple[int, int]:
        """Return the canvas dimensions the export ASS file is authored for."""
        source_w = max(1, int(getattr(self.video_view, "video_source_width", 0) or 1920))
        source_h = max(1, int(getattr(self.video_view, "video_source_height", 0) or 1080))
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        controller = getattr(self, "preview_controller", None)
        if controller is not None and video_path:
            try:
                target_w, target_h = controller._resolve_output_canvas_dimensions(video_path)
                if target_w and target_h:
                    return int(target_w), int(target_h)
            except Exception:
                pass
        return source_w, source_h

    def _sync_preview_output_canvas_dimensions(self):
        """Set the current output canvas before any preview-layer refresh.

        Text can exist without TS1 subtitles, so it must not depend on the
        subtitle-style path to learn that Ratio/Quality changed.
        """
        view = getattr(self, "video_view", None)
        if view is None or not hasattr(view, "set_subtitle_render_dimensions"):
            return
        width, height = self._subtitle_render_dimensions()
        view.set_subtitle_render_dimensions(width, height)

    def _resolved_subtitle_font_name(self, requested_font: str) -> str:
        """Use Qt's actual font fallback for both preview and ASS export.

        Preset fonts such as Montserrat are not installed on every Windows
        system. Qt and libass otherwise pick different fallbacks, causing
        identical text and widths to wrap on different words.
        """
        requested_font = str(requested_font or "Segoe UI").strip() or "Segoe UI"
        try:
            if not getattr(self, "_bundled_subtitle_fonts_registered", False):
                candidates = [
                    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")),
                    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")),
                ]
                try:
                    from runtime_paths import asset_path
                    candidates.insert(0, asset_path("fonts"))
                except Exception:
                    pass
                for bundled_dir in candidates:
                    if os.path.isdir(bundled_dir):
                        for filename in os.listdir(bundled_dir):
                            if filename.lower().endswith((".ttf", ".otf")):
                                QFontDatabase.addApplicationFont(os.path.join(bundled_dir, filename))
                        self._bundled_subtitle_fonts_registered = True
                        break
            resolved = QFontInfo(QFont(requested_font)).family().strip()
            return resolved or requested_font
        except Exception:
            return requested_font

    def update_subtitle_preview_style(self):
        if not hasattr(self, "video_view"):
            return
        item = self.video_view.subtitle_item
        has_video = bool(self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip())
        has_segments = bool(self.get_active_segments())
        if not has_video or not has_segments:
            item.set_text("")
            item.hide()
            self.sync_live_subtitle_preview()
            return
        render_w, render_h = self._subtitle_render_dimensions()
        if hasattr(self.video_view, "set_subtitle_render_dimensions"):
            self.video_view.set_subtitle_render_dimensions(render_w, render_h)
        source_h = max(1, render_h)
        preview_rect = self.video_view.get_preview_canvas_rect() if hasattr(self.video_view, "get_preview_canvas_rect") else self.video_view.get_video_content_rect()
        preview_h = max(1.0, preview_rect.height() or float(self.video_view.height()) or 1.0)
        preset = self.get_subtitle_preset_config()
        export_font_size = int(self.subtitle_font_size_spin.value())
        preview_scale = preview_h / source_h
        preview_font_size = max(1, int(round(export_font_size * preview_scale)))
        font_name = self._resolved_subtitle_font_name(
            self.subtitle_font_combo.currentText().strip() or preset.get("font_name", "Segoe UI")
        )
        bg_alpha = float(self.subtitle_bg_alpha_spin.value()) if hasattr(self, "subtitle_bg_alpha_spin") else float(preset.get("background_alpha", 0.0))
        bg_color = QColor(getattr(self, "subtitle_background_color_hex", preset.get("background_color", "#000000")))
        bg_color.setAlpha(max(0, min(255, int(round(bg_alpha * 255.0)))))
        bg_padding = float(self.subtitle_background_padding_spin.value()) if hasattr(self, "subtitle_background_padding_spin") else float(preset.get("background_padding", 6.0))
        bg_radius = float(self.subtitle_background_radius_spin.value()) if hasattr(self, "subtitle_background_radius_spin") else float(preset.get("background_radius", 0.0))
        base_outline = (
            float(preset.get("outline_width", 2))
            if not hasattr(self, "subtitle_outline_cb") or self.subtitle_outline_cb.isChecked()
            else 0.0
        )
        item.set_style(
            font_name=font_name or preset.get("font_name", "Segoe UI"),
            font_size=preview_font_size,
            base_font_size=export_font_size,
            base_outline_width=base_outline,
            base_padding=bg_padding,
            base_radius=bg_radius,
            font_color=self._subtitle_color_for_segment(
                (self.live_preview_segments or self.get_active_segments() or [None])[0]
            ),
            outline_width=base_outline * preview_scale,
            outline_color=QColor(preset.get("outline_color", "#000000")),
            background_box=bool(self.subtitle_background_cb.isChecked()),
            background_color=bg_color,
            background_padding=max(1.0, bg_padding * preview_scale),
            background_radius=max(0.0, bg_radius * preview_scale),
            single_line=bool(getattr(self, "subtitle_single_line_cb", None) and self.subtitle_single_line_cb.isChecked()),
            bold=bool(self.subtitle_bold_cb.isChecked()),
            shadow_color=QColor(preset.get("shadow_color", "#000000")),
            shadow_depth=float(preset.get("shadow_depth", 0)) * preview_scale,
        )
        position = self.get_subtitle_position_config()
        item.set_alignment(position.get("alignment_label", "Bottom"))
        item.set_positioning(
            x_offset=int(position.get("x_offset", 0)),
            bottom_offset=int(position.get("margin_v", 30)),
            custom_position_enabled=bool(position.get("custom_position_enabled", False)),
            custom_x_percent=int(position.get("custom_position_x", 50)),
            custom_y_percent=int(position.get("custom_position_y", 86)),
        )
        segments = self.live_preview_segments or self.get_active_segments()
        selected = int(getattr(self, "_selected_segment_index", -1))
        style_segment = segments[selected] if 0 <= selected < len(segments) else (segments[0] if segments else None)
        self._apply_live_subtitle_segment_color(style_segment)
        self._set_live_subtitle_effects(style_segment)
        if not self._preview_is_playing() and style_segment:
            if isinstance(style_segment, dict):
                seg_text = str(
                    style_segment.get("final_text", "")
                    or style_segment.get("text", "")
                    or style_segment.get("subtitle_text", "")
                    or style_segment.get("raw_translation", "")
                    or style_segment.get("original_text", "")
                    or ""
                ).strip()
            else:
                seg_text = str(
                    getattr(style_segment, "subtitle_text", "")
                    or getattr(style_segment, "final_text", "")
                    or getattr(style_segment, "original_text", "")
                    or getattr(style_segment, "text", "")
                    or ""
                ).strip()
            if seg_text:
                item.set_text(seg_text)
            if getattr(item, "current_text", "") and bool(getattr(self, "_subtitle_track_preview_visible", True)):
                item.show()
        self.video_view.reposition_subtitle()
        self.sync_live_subtitle_preview()
        self.schedule_auto_frame_preview()

    def _set_live_subtitle_effects(self, segment: dict | None, position_ms: int = 0):
        """Feed the editable preview layer the same cue effects used at export."""
        if not hasattr(self, "video_view"):
            return
        item = self.video_view.subtitle_item
        segment = segment or {}
        preset = self.get_subtitle_preset_config()
        if isinstance(segment, dict):
            text = str(
                segment.get("final_text", "")
                or segment.get("text", "")
                or segment.get("subtitle_text", "")
                or segment.get("raw_translation", "")
                or segment.get("original_text", "")
                or ""
            )
            auto_h = list(segment.get("auto_highlights", []) or [])
            manual_h = list(segment.get("manual_highlights", []) or [])
            start = float(segment.get("start", 0.0) or 0.0)
            end = max(start + 0.01, float(segment.get("end", start + 0.01) or start + 0.01))
        elif segment is not None:
            text = str(getattr(segment, "final_text", "") or getattr(segment, "original_text", "") or getattr(segment, "text", "") or "")
            meta = getattr(segment, "metadata", {}) if isinstance(getattr(segment, "metadata", None), dict) else {}
            auto_h = list(meta.get("auto_highlights", []) or getattr(segment, "auto_highlights", []) or [])
            manual_h = list(meta.get("manual_highlights", []) or getattr(segment, "manual_highlights", []) or [])
            start = float(getattr(segment, "start", 0.0) or 0.0)
            end = max(start + 0.01, float(getattr(segment, "end", start + 0.01) or start + 0.01))
        else:
            text = ""
            auto_h = []
            manual_h = []
            start = 0.0
            end = 0.01
        mode = self.subtitle_highlight_mode_combo.currentText().strip() if hasattr(self, "subtitle_highlight_mode_combo") else "Auto"
        phrases = []
        if mode in ("Auto", "Auto + Manual"):
            phrases.extend(auto_h)
        if mode in ("Manual", "Auto + Manual"):
            phrases.extend(manual_h)
        animation = self.subtitle_animation_combo.currentText().strip().lower() if hasattr(self, "subtitle_animation_combo") else ""
        animation_duration = max(0.01, float(self.subtitle_animation_time_spin.value())) if hasattr(self, "subtitle_animation_time_spin") else 0.22
        elapsed = max(0.0, float(position_ms) / 1000.0 - start)
        animation_progress = min(1.0, elapsed / animation_duration)
        if animation == "fade out":
            animation_progress = min(1.0, max(0.0, float(position_ms) / 1000.0 - (end - animation_duration)) / animation_duration)
        karaoke_index = -1
        if animation == "word highlight karaoke" and text:
            words = [word for word in text.split() if word]
            progress = max(0.0, min(0.999, (float(position_ms) / 1000.0 - start) / (end - start)))
            karaoke_index = min(len(words) - 1, int(progress * len(words))) if words else -1
        item.set_effects(
            highlight_color=self._highlight_color_hex() or preset.get("highlight_color", "#FFD400"),
            highlight_phrases=phrases,
            karaoke_word_index=karaoke_index,
            auto_keyword_highlight=bool(self.subtitle_keyword_highlight_cb.isChecked()) if hasattr(self, "subtitle_keyword_highlight_cb") else False,
            animation_style=animation,
            animation_progress=animation_progress,
        )

    def on_single_line_toggled(self, checked: bool):
        self.update_subtitle_preview_style()
        if not self.current_translated_segments:
            return
        if checked:
            self._split_segments_for_single_line()
        else:
            self._single_line_split_cache = None
        self.apply_segments_to_timeline()
        self.schedule_live_subtitle_preview_refresh()
        self.schedule_timeline_project_persist()

    def _split_segments_for_single_line(self):
        from translation import TranslationOrchestrator
        source = list(self.current_translated_segments or [])
        if not source:
            return
        orchestrator = TranslationOrchestrator()
        provider_type, polisher = orchestrator._resolve_ai_provider()
        if not polisher or not polisher.is_configured():
            polisher = None
        split = orchestrator._split_segments_for_single_line(
            source, polisher=polisher, provider_type=provider_type, target_lang=self.get_target_language_code(),
            words_per_segment=int(self.subtitle_words_per_segment_spin.value()) if hasattr(self, "subtitle_words_per_segment_spin") else 4,
        )
        if split and split != source:
            self._single_line_split_cache = split

    def get_subtitle_export_style(self, segments=None):
        preset = self.get_subtitle_preset_config()
        # Export-only glyph calibration. ASS ScaleX/ScaleY enlarges glyphs
        # without changing font-size-derived line spacing or row placement.
        export_font_scale = max(0.1, float(getattr(self, "subtitle_export_font_scale", 1.0)))
        export_font_size = max(1, int(self.subtitle_font_size_spin.value()))
        style_segments = segments if segments is not None else self.get_active_segments()
        position = self.get_subtitle_position_config()
        # Preview and export both use the subtitle's centre anchor.  Do not
        # convert it to ASS's bottom anchor: that conversion includes the Qt
        # widget's font-metric padding and caused a vertical offset whenever
        # the output canvas ratio changed.
        custom_bottom_y = None
        return {
            "font_name": self._resolved_subtitle_font_name(
                self.subtitle_font_combo.currentText().strip() or preset.get("font_name", "Arial")
            ),
            "font_size": export_font_size,
            "font_scale": export_font_scale,
            "font_color": self._hex_to_ass_color(self.subtitle_color_hex),
            "speaker_colors": (
                [
                    self._hex_to_ass_color(self._speaker_color_hex(str(segment.get("speaker", "") or "")))
                    if str(segment.get("speaker", "") or "").strip() else ""
                    for segment in (style_segments or [])
                ]
                if self._uses_speaker_subtitle_colors() else []
            ),
            "highlight_color": self._hex_to_ass_color(self._highlight_color_hex()),
            "outline_color": self._hex_to_ass_color(preset.get("outline_color", "#000000")),
            "outline_width": (
                float(preset.get("outline_width", 2))
                if not hasattr(self, "subtitle_outline_cb") or self.subtitle_outline_cb.isChecked()
                else 0.0
            ),
            "shadow_color": self._hex_to_ass_color(preset.get("shadow_color", "#000000")),
            "shadow_depth": float(preset.get("shadow_depth", 1)),
            "shadow_alpha": float(preset.get("shadow_alpha", 0.0)),
            "background_color": self._hex_to_ass_color(
                getattr(self, "subtitle_background_color_hex", preset.get("background_color", "#000000"))
            ),
            "background_alpha": float(self.subtitle_bg_alpha_spin.value()) if hasattr(self, "subtitle_bg_alpha_spin") else float(preset.get("background_alpha", 0.0)),
            "background_padding": int(self.subtitle_background_padding_spin.value()) if hasattr(self, "subtitle_background_padding_spin") else 6,
            "background_radius": int(self.subtitle_background_radius_spin.value()) if hasattr(self, "subtitle_background_radius_spin") else 0,
            "background_width": str(self.subtitle_background_width_combo.currentData() if hasattr(self, "subtitle_background_width_combo") else "fit_text"),
            "background_shape": str(self.subtitle_background_shape_combo.currentData() if hasattr(self, "subtitle_background_shape_combo") else "rectangle"),
            "animation": self.subtitle_animation_combo.currentText().strip() or preset.get("animation", "Static"),
            "animation_duration": float(self.subtitle_animation_time_spin.value()),
            "karaoke_timing_mode": str(self.subtitle_karaoke_timing_combo.currentData() or "vietnamese"),
            "position_mode": str(position.get("position_mode", "anchor")),
            "alignment": int(position.get("alignment", 2)),
            "margin_v": int(position.get("margin_v", 30)),
            "custom_position_enabled": bool(position.get("custom_position_enabled", False)),
            "custom_position_x": int(position.get("custom_position_x", 50)),
            "custom_position_y": int(position.get("custom_position_y", 86)),
            "custom_position_bottom_y": custom_bottom_y,
            "background_box": bool(self.subtitle_background_cb.isChecked()),
            "bold": bool(self.subtitle_bold_cb.isChecked()),
            "preset_key": self.get_selected_subtitle_preset(),
            "auto_keyword_highlight": bool(self.subtitle_keyword_highlight_cb.isChecked())
            and self.subtitle_highlight_mode_combo.currentText().strip() in ("Auto", "Auto + Manual")
            and not any(seg.get("auto_highlights") for seg in (style_segments or [])),
            "manual_highlights": self._build_render_highlight_lists(style_segments or []),
            "word_timings": [list(seg.get("words", [])) for seg in (style_segments or [])],
            "blur_region": (
                self.video_view.get_blur_region_normalized()
                if hasattr(self, "video_view") and self._blur_effect_enabled()
                else None
            ),
            "render_subtitles": False,
        }

    def _build_render_highlight_lists(self, style_segments):
        mode = self.subtitle_highlight_mode_combo.currentText().strip() if hasattr(self, "subtitle_highlight_mode_combo") else "Auto"
        include_auto = mode in ("Auto", "Auto + Manual")
        include_manual = mode in ("Manual", "Auto + Manual")
        rows = []
        for seg in style_segments or []:
            merged = []
            seen = set()
            if include_auto:
                for phrase in seg.get("auto_highlights", []) or []:
                    normalized = self._normalize_manual_highlight(phrase)
                    key = normalized.lower()
                    if normalized and key not in seen:
                        seen.add(key)
                        merged.append(normalized)
            if include_manual:
                for phrase in seg.get("manual_highlights", []) or []:
                    normalized = self._normalize_manual_highlight(phrase)
                    key = normalized.lower()
                    if normalized and key not in seen:
                        seen.add(key)
                        merged.append(normalized)
            rows.append(merged)
        return rows

    def on_subtitle_preset_changed(self):
        preset = self.get_subtitle_preset_config()
        selected = self.get_selected_subtitle_preset()
        self._subtitle_preset_apply_in_progress = True
        try:
            if selected == "custom":
                if self._subtitle_custom_style_state:
                    self._apply_subtitle_style_controls_state(self._subtitle_custom_style_state)
            else:
                self.subtitle_font_combo.setCurrentText(preset.get("font_name", "Arial"))
                self.subtitle_font_size_spin.setValue(int(preset.get("font_size", self.subtitle_font_size_spin.value())))
                self.subtitle_animation_combo.setCurrentText(preset.get("animation", "Static"))
                self.subtitle_background_cb.setChecked(bool(preset.get("background_box", False)))
                self.subtitle_background_color_hex = str(
                    preset.get("background_color", getattr(self, "subtitle_background_color_hex", "#000000"))
                ).upper()
                if hasattr(self, "subtitle_background_color_btn"):
                    self.subtitle_background_color_btn.setText(self.subtitle_background_color_hex)
                if hasattr(self, "subtitle_outline_cb"):
                    self.subtitle_outline_cb.setChecked(bool(preset.get("outline_width", 0) > 0))
                if hasattr(self, "subtitle_bg_alpha_spin"):
                    self.subtitle_bg_alpha_spin.setValue(float(preset.get("background_alpha", self.subtitle_bg_alpha_spin.value())))
                self.subtitle_bold_cb.setChecked(bool(preset.get("bold", False)))
                if hasattr(self, "subtitle_keyword_highlight_cb"):
                    self.subtitle_keyword_highlight_cb.setChecked(bool(preset.get("auto_keyword_highlight", False)))
                if hasattr(self, "subtitle_highlight_color_combo"):
                    color_name = "Yellow" if preset.get("highlight_color", "").upper() == "#FFD400" else "Cyan"
                    self.subtitle_highlight_color_combo.setCurrentText(color_name)
                if hasattr(self, "subtitle_highlight_mode_combo"):
                    self.subtitle_highlight_mode_combo.setCurrentText(str(preset.get("highlight_mode", "Auto")))
        finally:
            self._subtitle_preset_apply_in_progress = False
        if hasattr(self, "style_library_card"):
            self.style_library_card.setVisible(True)
        if hasattr(self, "highlight_card"):
            self.highlight_card.setVisible(True)
        if hasattr(self, "custom_title_card"):
            self.custom_title_card.setVisible(True)
        if hasattr(self, "subtitle_preset_summary_label"):
            self.subtitle_preset_summary_label.setText(
                f"{preset.get('label', 'Preset')}: {preset.get('summary', '')}"
            )
        self._update_animation_time_visibility()
        self.on_subtitle_background_width_changed()
        if selected == "custom":
            self._capture_subtitle_custom_style_state()
        self.on_subtitle_position_mode_changed()

    def _update_animation_time_visibility(self):
        current_animation = self.subtitle_animation_combo.currentText().strip().lower()
        show_animation_time = current_animation != "static"
        show_karaoke_timing = current_animation in ("word highlight karaoke", "typewriter")
        if hasattr(self, "subtitle_animation_time_label"):
            self.subtitle_animation_time_label.setVisible(show_animation_time)
        if hasattr(self, "subtitle_animation_time_spin"):
            self.subtitle_animation_time_spin.setVisible(show_animation_time)
        if hasattr(self, "subtitle_karaoke_timing_label"):
            self.subtitle_karaoke_timing_label.setVisible(show_karaoke_timing)
        if hasattr(self, "subtitle_karaoke_timing_combo"):
            self.subtitle_karaoke_timing_combo.setVisible(show_karaoke_timing)

    def on_subtitle_animation_changed(self):
        self._update_animation_time_visibility()
        self.update_subtitle_preview_style()

    def refresh_video_dimensions(self, path: str):
        refresh_video_dimensions_impl(self, path, get_video_dimensions)
        self._sync_preview_framing_to_player()

    def _hex_to_ass_color(self, hex_color: str) -> str:
        color = QColor(hex_color)
        return f"&H00{color.blue():02X}{color.green():02X}{color.red():02X}"
