from __future__ import annotations

import os
import hashlib
import json

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox

from app.services.timeline_video_sequence import (
    append_video,
    insert_media,
    is_image_file,
    move_video,
    ordered_video_layers,
    remove_video,
    resolve_timeline_time,
    timeline_video_clips,
)


class MultiVideoTimelineMixin:
    """Coordinate the sequential source videos stored directly on V1."""

    def get_timeline_video_clips(self, *, existing_only: bool = False) -> list[dict]:
        model = getattr(getattr(self, "timeline", None), "_timeline", None)
        return [clip.to_dict() for clip in timeline_video_clips(model, existing_only=existing_only)]

    def timeline_position_ms(self) -> int:
        clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []
        if clips and hasattr(self, "media_player"):
            current_source = os.path.normcase(os.path.abspath(str(getattr(getattr(self, "media_player", None), "_source_path", "") or "")))
            cached_source = os.path.normcase(os.path.abspath(str(getattr(self, "_timeline_preview_source", "") or "")))
            source = current_source or cached_source
            clip = next((item for item in clips if os.path.normcase(os.path.abspath(item["source"])) == source), None)
            if clip is not None:
                try:
                    local_ms = int(self.media_player.position())
                    local_seconds = max(0.0, float(local_ms) / 1000.0)
                    global_seconds = float(clip["timeline_start"]) + max(
                        0.0, (local_seconds - float(clip["source_start"])) / max(0.01, float(clip.get("speed", 1.0) or 1.0))
                    )
                    global_seconds = min(float(clip["timeline_end"]), global_seconds)
                    return int(global_seconds * 1000)
                except Exception:
                    pass
        global_pos = getattr(self, "_timeline_global_position_ms", None)
        if global_pos is not None:
            return int(global_pos)
        try:
            return int(self.media_player.position())
        except Exception:
            return 0

    def timeline_position_seconds(self) -> float:
        return max(0.0, float(self.timeline_position_ms()) / 1000.0)

    def refresh_source_video_list(self) -> None:
        widget = getattr(self, "source_video_list", None)
        timeline = getattr(getattr(self, "timeline", None), "_timeline", None)
        if widget is None:
            return
        if timeline is not None:
            from app.services.timeline_video_sequence import normalize_v1_sequence
            normalize_v1_sequence(timeline)
            timeline_widget = getattr(self, "timeline", None)
            if timeline_widget is not None:
                timeline_widget.set_duration(int(round(float(timeline.duration) * 1000.0)))
        selected_id = ""
        current = widget.currentItem()
        if current is not None:
            selected_id = str(current.data(Qt.UserRole) or "")
        widget.blockSignals(True)
        widget.clear()
        video_count = 0
        image_count = 0
        for index, layer in enumerate(ordered_video_layers(timeline), 1):
            duration = max(0.0, float(layer.end) - float(layer.start))
            minutes, seconds = divmod(int(round(duration)), 60)
            hours, minutes = divmod(minutes, 60)
            if hours > 0:
                time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                time_str = f"{minutes:02d}:{seconds:02d}"
            is_img = is_image_file(layer.source)
            if is_img:
                image_count += 1
                badge = "🖼️ [Ảnh]"
            else:
                video_count += 1
                badge = "🎬 [Video]"
            item = QListWidgetItem(
                f"{index}. {badge} {os.path.basename(layer.source)}   {time_str}"
            )
            item.setData(Qt.UserRole, layer.id)
            item.setToolTip(layer.source)
            widget.addItem(item)
            if layer.id == selected_id:
                widget.setCurrentItem(item)
        widget.blockSignals(False)
        count = widget.count()
        if hasattr(self, "source_video_summary_label"):
            total = float(getattr(timeline, "duration", 0.0) or 0.0)
            hours, remainder = divmod(int(round(total)), 3600)
            minutes, seconds = divmod(remainder, 60)
            total_text = f"{hours:d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
            summary_parts = []
            if video_count > 0:
                summary_parts.append(f"{video_count} video")
            if image_count > 0:
                summary_parts.append(f"{image_count} ảnh")
            summary_label_str = ", ".join(summary_parts) if summary_parts else f"{count} clip"
            self.source_video_summary_label.setText(f"{summary_label_str} · {total_text}")
        self._update_source_video_buttons()

    def _selected_source_video_layer_id(self) -> str:
        widget = getattr(self, "source_video_list", None)
        item = widget.currentItem() if widget is not None else None
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def _update_source_video_buttons(self) -> None:
        widget = getattr(self, "source_video_list", None)
        row = widget.currentRow() if widget is not None else -1
        count = widget.count() if widget is not None else 0
        # The Media UI owns these controls.  Keep the names aligned with the
        # widgets created in start_panel so reorder/remove are available as
        # soon as a source is selected.
        for name, enabled in (
            ("source_video_up_btn", row > 0),
            ("source_video_down_btn", 0 <= row < count - 1),
            ("source_video_remove_btn", row >= 0 and count > 1),
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setEnabled(enabled)

    def _sync_canonical_source_after_change(self) -> None:
        """Persist the first V1 clip as the project's canonical source."""
        model = getattr(getattr(self, "timeline", None), "_timeline", None)
        clips = timeline_video_clips(model)
        first_video = next((c for c in clips if not c.is_image), None)
        first_source = os.path.abspath(first_video.source) if first_video else (os.path.abspath(clips[0].source) if clips else "")
        state = getattr(self, "current_project_state", None)
        if first_source:
            self._current_video_path = first_source
            editor = getattr(self, "video_path_edit", None)
            if editor is not None:
                editor.setText(first_source)
            if state is not None:
                state.input_video = first_source
                service = getattr(self, "project_service", None)
                if service is not None and hasattr(service, "_input_video_identity"):
                    state.set_setting("input_video_identity", service._input_video_identity(first_source))
        elif state is not None:
            state.input_video = ""
            self._current_video_path = ""

        clip_payload = [clip.to_dict() for clip in clips]
        if state is not None:
            state.set_setting("timeline_video_clips", clip_payload)
            signature_payload = []
            for clip in clip_payload:
                source = os.path.abspath(str(clip.get("source", "") or ""))
                try:
                    stat = os.stat(source)
                    identity = [stat.st_size, stat.st_mtime_ns]
                except OSError:
                    identity = [0, 0]
                signature_payload.append({
                    "source": source,
                    "identity": identity,
                    "source_start": round(float(clip.get("source_start", 0.0) or 0.0), 6),
                    "source_duration": round(float(clip.get("source_duration", 0.0) or 0.0), 6),
                    "timeline_start": round(float(clip.get("timeline_start", 0.0) or 0.0), 6),
                    "speed": round(float(clip.get("speed", 1.0) or 1.0), 6),
                })
            state.set_setting(
                "timeline_video_signature",
                hashlib.sha256(json.dumps(signature_payload, sort_keys=True).encode("utf-8")).hexdigest()
                if signature_payload else "",
            )
            try:
                self.project_service.save_project(state)
            except Exception:
                pass
        if hasattr(self, "update_project_header"):
            try:
                self.update_project_header()
            except Exception:
                pass

    def _invalidate_artifacts_after_timeline_change(self) -> None:
        """Detach source-derived artifacts after V1 order/content changes."""
        state = getattr(self, "current_project_state", None)
        artifact_keys = {
            "extracted_audio", "audio_extracted", "asr_audio_profile", "asr_ocr_reference",
            "transcript_raw", "transcript_segments", "transcript_chunk_raw", "transcript_merged",
            "transcript_regrouped", "transcription_chunks", "subtitle_original_srt", "srt_original",
            "subtitle_translated_srt", "srt_translated", "translation_raw", "translation_refined",
            "translation_final", "voice_vi", "voice_segments", "mixed_vi", "vocals", "music",
            "auto_recap_video",
        }
        if state is not None:
            for key in artifact_keys:
                state.artifacts.pop(key, None)
            for key in (
                "extraction_signature", "asr_audio_normalization", "transcription_signature",
                "translation_signature", "voice_signature", "auto_recap_edl",
                "input_video_content_changed",
            ):
                state.settings.pop(key, None)
            state.settings["voice_track_partial"] = False
            if hasattr(state, "steps"):
                for step in (
                    "extract_audio", "transcribe", "translate_raw", "refine_translation",
                    "generate_tts", "build_subtitle", "mix_audio", "export",
                ):
                    state.steps[step] = "pending"
        processed = getattr(self, "processed_artifacts", None)
        if isinstance(processed, dict):
            for key in artifact_keys:
                processed.pop(key, None)
        for attr in (
            "last_extracted_audio", "last_vocals_path", "last_music_path", "last_original_srt_path",
            "last_translated_srt_path", "last_voice_vi_path", "last_mixed_vi_path",
            "last_preview_video_path", "last_styled_preview_path", "last_recap_video_path",
            "last_exported_video_path", "live_preview_subtitle_path", "live_preview_ass_path",
        ):
            if hasattr(self, attr):
                setattr(self, attr, "")
        for attr in ("current_segments", "current_translated_segments", "current_segment_models", "current_translated_segment_models"):
            if hasattr(self, attr):
                setattr(self, attr, [])
        if hasattr(self, "current_auto_recap_edl"):
            self.current_auto_recap_edl = []
        self._voice_track_partial = False
        self._voiceover_force_refresh = True
        self._timeline_preview_source = ""
        self._timeline_global_position_ms = 0
        timeline = getattr(self, "timeline", None)
        if timeline is not None:
            try:
                timeline.set_segments([])
            except Exception:
                pass
        if state is not None:
            try:
                self.project_service.save_project(state)
            except Exception:
                pass
        if hasattr(self, "refresh_source_video_list"):
            self.refresh_source_video_list()
        if hasattr(self, "refresh_ui_state"):
            try:
                self.refresh_ui_state()
            except Exception:
                pass

    def shift_timeline_timed_elements(self, delta: float, after_time: float = 0.0) -> None:
        """Shift non-V1 timed elements (subtitles, TTS segments, overlays) to maintain sync with video."""
        if abs(delta) < 0.001:
            return

        # 1. Shift current_segments and current_translated_segments (canonical transcript / TTS cues)
        from ui.helpers.srt_helpers import _shift_segment_timeline
        for seg_list_name in ("current_segments", "current_translated_segments"):
            segments = getattr(self, seg_list_name, None)
            if isinstance(segments, list):
                for seg in segments:
                    if isinstance(seg, dict):
                        st = float(seg.get("start", 0.0) or 0.0)
                        if st >= after_time - 0.001:
                            seg.update(_shift_segment_timeline(seg, delta))

        # 2. Shift segment models if present
        for model_list_name in ("current_segment_models", "current_translated_segment_models"):
            models = getattr(self, model_list_name, None)
            if isinstance(models, list):
                for m in models:
                    st = float(getattr(m, "start", 0.0) or 0.0)
                    if st >= after_time - 0.001:
                        dur = max(0.1, float(getattr(m, "end", st + 0.1) or (st + 0.1)) - st)
                        new_st = max(0.0, round(m.start + delta, 3))
                        m.start = new_st
                        m.end = round(new_st + dur, 3)

        # 3. Shift layers on non-V1/A1 tracks in Timeline model (subtitles, voiceover, logo, blur, mask, text)
        timeline_widget = getattr(self, "timeline", None)
        model = getattr(timeline_widget, "_timeline", None)
        if model is not None:
            for track in model.tracks:
                track_name = str(getattr(track, "name", "") or "")
                if track_name.startswith("V1") or track_name.startswith("A1"):
                    continue
                for layer in track.layers:
                    st = float(getattr(layer, "start", 0.0) or 0.0)
                    if st >= after_time - 0.001:
                        dur = max(0.05, float(getattr(layer, "end", st + 0.05) or (st + 0.05)) - st)
                        new_st = max(0.0, round(st + delta, 6))
                        layer.start = new_st
                        layer.end = round(new_st + dur, 6)

        # 4. Update timeline duration and redraw
        if timeline_widget is not None and model is not None:
            timeline_widget.set_duration(int(round(float(model.duration) * 1000.0)))
            timeline_widget._redraw()

        # 5. Keep subtitle text widgets in sync with shifted segment timings
        if hasattr(self, "format_to_srt"):
            if hasattr(self, "transcript_text") and getattr(self, "current_segments", None):
                try:
                    self.transcript_text.setText(self.format_to_srt(self.current_segments))
                except Exception:
                    pass
            if hasattr(self, "translated_text") and getattr(self, "current_translated_segments", None):
                try:
                    self.translated_text.setText(self.format_to_srt(self.current_translated_segments))
                except Exception:
                    pass

        # 6. Refresh UI components that display subtitles or overlays
        if hasattr(self, "refresh_segment_table"):
            try:
                self.refresh_segment_table()
            except Exception:
                pass
        if hasattr(self, "refresh_timed_layer_preview"):
            try:
                self.refresh_timed_layer_preview()
            except Exception:
                pass
        if hasattr(self, "persist_current_timeline_project_data"):
            try:
                self.persist_current_timeline_project_data()
            except Exception:
                pass

    def add_videos_to_timeline(self, insert_front: bool = False) -> None:
        title = "Chèn video vào đầu" if insert_front else "Thêm video vào Timeline"
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            title,
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.m4v)",
        )
        if not paths:
            return
        timeline_widget = getattr(self, "timeline", None)
        model = getattr(timeline_widget, "_timeline", None)
        if timeline_widget is None or model is None:
            QMessageBox.warning(self, "Add Video", "Timeline is not ready.")
            return
        was_empty = not ordered_video_layers(model)
        first_vid_before = next((float(l.start) for l in ordered_video_layers(model) if not is_image_file(l.source)), None)
        added = 0
        first_added_path = ""
        for path in paths:
            duration = float(timeline_widget._probe_video_duration(path))
            if duration <= 0:
                self.log(f"[Timeline] Skipped unreadable video: {path}")
                continue
            if insert_front:
                insert_media(model, path, duration, index=added)
            else:
                append_video(model, path, duration)
            if not first_added_path:
                first_added_path = os.path.abspath(path)
            added += 1
        if not added:
            QMessageBox.warning(self, "Add Video", "No readable video was selected.")
            return
        timeline_widget.set_duration(int(model.duration * 1000))
        timeline_widget._redraw()
        if insert_front and not was_empty and first_vid_before is not None:
            first_vid_after = next((float(l.start) for l in ordered_video_layers(model) if not is_image_file(l.source)), None)
            if first_vid_after is not None:
                shift = first_vid_after - first_vid_before
                if abs(shift) > 0.001:
                    self.shift_timeline_timed_elements(shift, after_time=0.0)
        # A newly-created project has no source yet. The first imported clip
        # becomes its primary processing source, while all selected videos are
        # retained in order on V1. Project id/name stay unchanged.
        if was_empty and first_added_path:
            state = getattr(self, "current_project_state", None)
            if state is not None:
                state.input_video = first_added_path
                state.set_setting("input_video_identity", self.project_service._input_video_identity(first_added_path))
                self.project_service.save_project(state)
            self._current_video_path = first_added_path
            self.video_path_edit.setText(first_added_path)
            self.ensure_media_backend_ready()
            self.media_player.setSource(QUrl.fromLocalFile(first_added_path))
            if hasattr(self, "refresh_video_dimensions"):
                self.refresh_video_dimensions(first_added_path)
            if hasattr(self, "update_project_header"):
                self.update_project_header()
            try:
                from views.launcher import LauncherWindow
                LauncherWindow.add_recent(None, {
                    "project_state_path": self.project_service.project_file(state.project_root) if state else "",
                    "video_path": first_added_path,
                })
            except Exception as exc:
                self.log(f"[Timeline] Could not update recent projects: {exc}")
        self._sync_canonical_source_after_change()
        if hasattr(self, "persist_current_timeline_project_data"):
            self.persist_current_timeline_project_data()
        self.refresh_source_video_list()
        if hasattr(self, "schedule_timeline_visual_refresh"):
            self.schedule_timeline_visual_refresh(waveform=True, thumbnails=True)
        if hasattr(self, "log"):
            action_name = "Chèn vào đầu" if insert_front else "Thêm vào cuối"
            self.log(f"[Timeline] {action_name}: {added} video vào V1.")
        self.timeline.viewport().update()

    def add_images_to_timeline(self, insert_front: bool = False) -> None:
        title = "Chèn ảnh vào đầu (Intro)" if insert_front else "Thêm ảnh vào Timeline"
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            title,
            "",
            "Image Files (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*.*)",
        )
        if not paths:
            return
        timeline_widget = getattr(self, "timeline", None)
        model = getattr(timeline_widget, "_timeline", None)
        if timeline_widget is None or model is None:
            QMessageBox.warning(self, "Add Image", "Timeline is not ready.")
            return
        was_empty = not ordered_video_layers(model)
        first_vid_before = next((float(l.start) for l in ordered_video_layers(model) if not is_image_file(l.source)), None)
        added = 0
        first_added_path = ""
        for path in paths:
            duration = 3.0
            if hasattr(timeline_widget, "_probe_video_duration"):
                probe_dur = float(timeline_widget._probe_video_duration(path))
                if probe_dur > 0:
                    duration = probe_dur
            if insert_front:
                insert_media(model, path, duration, index=added)
            else:
                append_video(model, path, duration)
            if not first_added_path:
                first_added_path = os.path.abspath(path)
            added += 1
        if not added:
            return
        timeline_widget.set_duration(int(model.duration * 1000))
        timeline_widget._redraw()
        if insert_front and not was_empty and first_vid_before is not None:
            first_vid_after = next((float(l.start) for l in ordered_video_layers(model) if not is_image_file(l.source)), None)
            if first_vid_after is not None:
                shift = first_vid_after - first_vid_before
                if abs(shift) > 0.001:
                    self.shift_timeline_timed_elements(shift, after_time=0.0)
        if was_empty and first_added_path:
            state = getattr(self, "current_project_state", None)
            if state is not None:
                state.input_video = first_added_path
                state.set_setting("input_video_identity", self.project_service._input_video_identity(first_added_path))
                self.project_service.save_project(state)
            self._current_video_path = first_added_path
            self.video_path_edit.setText(first_added_path)
            self.ensure_media_backend_ready()
            self.media_player.setSource(QUrl.fromLocalFile(first_added_path))
            if hasattr(self, "refresh_video_dimensions"):
                self.refresh_video_dimensions(first_added_path)
            if hasattr(self, "update_project_header"):
                self.update_project_header()
        self._sync_canonical_source_after_change()
        if hasattr(self, "persist_current_timeline_project_data"):
            self.persist_current_timeline_project_data()
        self.refresh_source_video_list()
        if hasattr(self, "schedule_timeline_visual_refresh"):
            self.schedule_timeline_visual_refresh(waveform=True, thumbnails=True)
        if hasattr(self, "log"):
            action_name = "Chèn vào đầu (Intro)" if insert_front else "Thêm vào cuối"
            self.log(f"[Timeline] {action_name}: {added} ảnh vào V1.")
        self.timeline.viewport().update()

    def remove_selected_source_video(self) -> None:
        """Remove the selected V1 source while preserving project identity."""
        model = getattr(getattr(self, "timeline", None), "_timeline", None)
        layers = ordered_video_layers(model)
        layer_id = self._selected_source_video_layer_id()
        if not layer_id:
            QMessageBox.information(self, "Remove Video", "Select a source clip first.")
            return
        if len(layers) <= 1:
            QMessageBox.information(self, "Remove Video", "A project must keep at least one clip on V1.")
            return
        if not remove_video(model, layer_id):
            return
        self.timeline.set_duration(int(round(float(model.duration) * 1000.0)))
        self.timeline._selected_layer_id = ""
        self.timeline._redraw()
        self._sync_canonical_source_after_change()
        self._invalidate_artifacts_after_timeline_change()
        self.persist_current_timeline_project_data()
        if hasattr(self, "schedule_timeline_visual_refresh"):
            self.schedule_timeline_visual_refresh(waveform=True, thumbnails=True)

    def move_selected_source_video(self, offset: int) -> None:
        """Move the selected V1 source and invalidate source-timed artifacts."""
        model = getattr(getattr(self, "timeline", None), "_timeline", None)
        layer_id = self._selected_source_video_layer_id()
        if not layer_id or not move_video(model, layer_id, int(offset)):
            return
        self.timeline.set_duration(int(round(float(model.duration) * 1000.0)))
        self.timeline._redraw()
        self._sync_canonical_source_after_change()
        self._invalidate_artifacts_after_timeline_change()
        self.persist_current_timeline_project_data()
        if hasattr(self, "schedule_timeline_visual_refresh"):
            self.schedule_timeline_visual_refresh(waveform=True, thumbnails=True)

    def select_source_video_in_timeline(self) -> None:
        """Select a source clip in V1 without changing the playhead."""
        layer_id = self._selected_source_video_layer_id()
        if not layer_id or not hasattr(self, "timeline"):
            return
        self.timeline._selected_layer_id = layer_id
        self.timeline.viewport().update()

    def seek_timeline_video(self, global_seconds: float) -> None:
        model = getattr(getattr(self, "timeline", None), "_timeline", None)
        clip, local_seconds = resolve_timeline_time(model, global_seconds)
        if clip is None or not os.path.isfile(clip.source):
            return
        # The cached source is only a hint.  Other preview features can swap
        # the player source asynchronously, so trust the player's real
        # source as well.  Without this check a seek on V2 could calculate
        # V2's local timestamp but apply it to V1.
        current = os.path.abspath(str(getattr(self, "_timeline_preview_source", "") or ""))
        player_source = os.path.abspath(str(getattr(self.media_player, "_source_path", "") or ""))
        wanted = os.path.abspath(clip.source)
        if current != wanted or player_source != wanted:
            self._timeline_preview_source = wanted
            self.media_player.setSource(QUrl.fromLocalFile(wanted))
            if hasattr(self, "refresh_video_dimensions") and not clip.is_image:
                self.refresh_video_dimensions(wanted)
            if hasattr(self, "sync_preview_audio_track_to_output"):
                self.sync_preview_audio_track_to_output(apply_to_player=True, force=True)
            elif hasattr(self.media_player, "set_original_audio_file"):
                self.media_player.set_original_audio_file(wanted)
        global_ms = int(max(0.0, global_seconds) * 1000)
        self._timeline_global_position_ms = global_ms
        if hasattr(self, "timeline"):
            if hasattr(self.timeline, "set_playhead"):
                self.timeline.set_playhead(max(0.0, global_seconds))
            if hasattr(self.timeline, "set_position"):
                self.timeline.set_position(global_ms)
        clips = self.get_timeline_video_clips(existing_only=True)
        if clips:
            total_ms = int(float(clips[-1]["timeline_end"]) * 1000)
            self.update_duration_label(global_ms, total_ms)
        try:
            self.media_player.setPosition(int(local_seconds * 1000), global_ms)
        except TypeError:
            self.media_player.setPosition(int(local_seconds * 1000))
        if hasattr(self, "refresh_timed_layer_preview"):
            self.refresh_timed_layer_preview(global_ms)
        if hasattr(self, "update_playback_subtitle_highlight"):
            self.update_playback_subtitle_highlight(global_ms)
        if hasattr(self, "_sync_selected_segment_to_playback_position"):
            self._sync_selected_segment_to_playback_position(global_ms)

    def handle_sequence_position_changed(self, local_position_ms: int) -> bool:
        clips = self.get_timeline_video_clips(existing_only=True)
        if not clips:
            return False
        current_source = os.path.abspath(str(getattr(getattr(self, "media_player", None), "_source_path", "") or ""))
        preview_source = os.path.abspath(str(getattr(self, "last_preview_video_path", "") or ""))
        cached_source = os.path.abspath(str(getattr(self, "_timeline_preview_source", "") or ""))
        # Position callbacks originate from the active player source.  Prefer
        # it over the cache so the global playhead cannot jump back to V1
        # after a source switch.
        source = current_source or cached_source
        clip = next((item for item in clips if os.path.abspath(item["source"]) == source), None)
        if clip is None:
            clip = next((item for item in clips if os.path.abspath(item["source"]) == cached_source), None)
        # A rendered preview represents the complete logical Timeline and
        # therefore already uses global time. Do not map it through V1's
        # source_start/speed values.
        rendered_preview_active = bool(
            preview_source
            and current_source == preview_source
            and not any(os.path.abspath(item["source"]) == current_source for item in clips)
        )
        if rendered_preview_active:
            total_seconds = float(clips[-1]["timeline_end"])
            global_seconds = min(total_seconds, max(0.0, float(local_position_ms) / 1000.0))
            global_ms = int(global_seconds * 1000)
            self._timeline_global_position_ms = global_ms
            self.timeline.set_position(global_ms)
            self.update_duration_label(global_ms, int(total_seconds * 1000))
            self.refresh_timed_layer_preview(global_ms)
            self.update_playback_subtitle_highlight(global_ms)
            return True
        if clip is None:
            return False
        self._timeline_preview_source = os.path.abspath(clip["source"])
        local_seconds = max(0.0, float(local_position_ms) / 1000.0)
        global_seconds = float(clip["timeline_start"]) + max(
            0.0, (local_seconds - float(clip["source_start"])) / max(0.01, float(clip["speed"]))
        )
        global_seconds = min(float(clip["timeline_end"]), global_seconds)
        global_ms = int(global_seconds * 1000)
        self._timeline_global_position_ms = global_ms
        self.timeline.set_position(global_ms)
        self.update_duration_label(global_ms, int(float(clips[-1]["timeline_end"]) * 1000))
        self.refresh_timed_layer_preview(global_ms)
        self.update_playback_subtitle_highlight(global_ms)

        at_clip_end = local_seconds >= (
            float(clip["source_start"]) + float(clip["source_duration"]) - 0.12
        )
        if at_clip_end:
            index = clips.index(clip)
            if index + 1 < len(clips):
                was_playing = getattr(self.timeline, "_is_playing", False) or bool(self.media_player.is_playing())
                next_clip = clips[index + 1]
                self.seek_timeline_video(float(next_clip["timeline_start"]))
                if was_playing:
                    self.media_player.play()
        return True
