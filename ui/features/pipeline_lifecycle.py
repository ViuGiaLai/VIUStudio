import os
import copy
import glob
import hashlib
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMessageBox)
from PySide6.QtCore import QTimer, QUrl

from utils.launcher_lifecycle import relaunch_launcher
from utils.display_utils import (
    cleanup_temp_preview_files as cleanup_temp_preview_files_impl,
    show_processed_files as show_processed_files_impl,
)
from utils.file_dialog_utils import (
    browse_audio_folder as browse_audio_folder_impl,
    browse_audio_source as browse_audio_source_impl,
    browse_background_audio as browse_background_audio_impl,
    browse_existing_mixed_audio as browse_existing_mixed_audio_impl,
    browse_srt_output_folder as browse_srt_output_folder_impl,
    browse_voice_output_folder as browse_voice_output_folder_impl,
    open_folder as open_folder_impl,
)
from utils.icon_utils import load_icon
from utils.media_utils import (
    browse_video as browse_video_impl,
    duration_changed as duration_changed_impl,
    position_changed as position_changed_impl,
    set_position as set_position_impl,
    setup_media_player as setup_media_player_impl,
    stop_video as stop_video_impl,
    toggle_play as toggle_play_impl,
    update_duration_label as update_duration_label_impl,
)
from widgets.subtitle_editor_dialog import SubtitleEditorDialog
from runtime_paths import asset_path
from worker_adapters import (
    VoiceOverWorker,
)
from utils.thread_lifecycle import release_thread_when_stopped



class PipelineLifecycleMixin:
    def apply_edited_translation(self, show_message=True, force_apply=True):
        result = self.subtitle_controller.apply_edited_translation(show_message=show_message, force_apply=force_apply)
        if result:
            self.refresh_auto_keyword_highlights()
            self._commit_subtitle_mutation(
                selected_index=getattr(self, "_selected_segment_index", None),
            )
            self.sync_segment_editor_rows()
            return result

    def open_subtitle_editor(self):
        """Open the staged, bulk translated-subtitle editor.

        Unlike the small inspector editor this does not alter the project on
        every keystroke.  It makes text-only changes explicit via Update.
        """
        translated_segments = list(self.current_translated_segments or [])
        source_segments = list(self.current_segments or [])
        if translated_segments:
            segments = translated_segments
        elif source_segments:
            # Run to Original intentionally stops before translation. Build a
            # temporary review track with blank Translated text so XLSX export
            # and import are immediately available without inventing a draft.
            segments = []
            for source in source_segments:
                review = copy.deepcopy(source)
                review["source_text"] = str(source.get("text", "") or "")
                review["text"] = ""
                review["subtitle_vi"] = ""
                review["tts_text"] = ""
                segments.append(review)
        else:
            QMessageBox.information(
                self,
                "Subtitle Editor",
                "No subtitles are available. Run Original Transcript or import an SRT first.",
            )
            return
        editor_segments = copy.deepcopy(segments)
        # Translation artifacts can intentionally omit source_text.  The
        # source transcript remains index/timing aligned, so enrich only the
        # editor copy for display without changing project metadata.
        source_by_time = {
            (round(float(item.get("start", 0.0) or 0.0), 3), round(float(item.get("end", 0.0) or 0.0), 3)): item
            for item in source_segments
            if isinstance(item, dict)
        }
        for index, segment in enumerate(editor_segments):
            if not str(segment.get("source_text") or segment.get("original_text") or "").strip():
                key = (
                    round(float(segment.get("start", 0.0) or 0.0), 3),
                    round(float(segment.get("end", 0.0) or 0.0), 3),
                )
                source = source_by_time.get(key) or (source_segments[index] if index < len(source_segments) else {})
                source_text = str(source.get("text", "") or "").strip()
                if source_text:
                    segment["source_text"] = source_text
        dialog = SubtitleEditorDialog(
            self,
            editor_segments,
            self._apply_subtitle_editor_changes,
            self.run_rewrite_translation,
            self._export_subtitle_translation_xlsx,
            self._import_subtitle_translation_xlsx,
            self._build_subtitle_translation_ai_prompt,
        )
        self._subtitle_editor_dialog = dialog
        try:
            dialog.exec()
        finally:
            if getattr(self, "_subtitle_editor_dialog", None) is dialog:
                self._subtitle_editor_dialog = None

    def _subtitle_exchange_context(self, segments) -> dict:
        state = getattr(self, "current_project_state", None)
        configured_source = str(self.get_source_language_code() or getattr(state, "input_language", "auto") or "auto")
        target_language = str(self.get_target_language_code() or getattr(state, "target_language", "vi") or "vi")
        style_parts = []
        style_combo = getattr(self, "translation_style_preset_combo", None)
        if style_combo is not None:
            style_label = str(style_combo.currentText() or "").strip()
            if style_label:
                style_parts.append(style_label)
        custom_style = getattr(self, "translator_style_edit", None)
        if custom_style is not None and str(custom_style.text() or "").strip():
            style_parts.append(str(custom_style.text()).strip())
        project_name = str(
            getattr(state, "display_name", "")
            or getattr(state, "project_id", "")
            or "CapCap Project"
        )
        return {
            "segments": list(segments or []),
            "configured_source": configured_source,
            "target_language": target_language,
            "translation_style": " | ".join(style_parts) or "Standard / Natural",
            "project_name": project_name,
        }

    def _build_subtitle_translation_ai_prompt(self, segments) -> str:
        from services import SubtitleExchangeService

        context = self._subtitle_exchange_context(segments)
        context.pop("project_name", None)
        return SubtitleExchangeService().build_prompt(**context)

    def _export_subtitle_translation_xlsx(self, segments):
        from services import SubtitleExchangeService

        context = self._subtitle_exchange_context(segments)
        missing_source = [
            index + 1
            for index, segment in enumerate(context["segments"])
            if not str(
                segment.get("source_text")
                or segment.get("original_text")
                or segment.get("original")
                or ""
            ).strip()
        ]
        if missing_source:
            preview = ", ".join(str(number) for number in missing_source[:8])
            if len(missing_source) > 8:
                preview += "…"
            QMessageBox.warning(
                self,
                "Export Translation Workbook",
                "The original-language text is missing for cue(s): "
                f"{preview}. Run the original transcript or import the source SRT first.",
            )
            return False
        safe_name = "".join(
            char if char.isalnum() or char in {"-", "_"} else "_"
            for char in context["project_name"]
        ).strip("_") or "capcap_subtitles"
        state = getattr(self, "current_project_state", None)
        initial_dir = str(getattr(state, "project_root", "") or os.getcwd())
        default_path = os.path.join(initial_dir, f"{safe_name}_translation_review.xlsx")
        output_path, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Subtitle Translation XLSX",
            default_path,
            "Excel Workbook (*.xlsx)",
        )
        if not output_path:
            return False
        if not output_path.lower().endswith(".xlsx"):
            output_path += ".xlsx"
        try:
            saved_path = SubtitleExchangeService().export_xlsx(output_path, **context)
        except Exception as exc:
            QMessageBox.critical(self, "Export XLSX Failed", str(exc))
            return False
        self.log(f"[Subtitle Editor] Exported translation workbook: {saved_path}")
        QMessageBox.information(
            self,
            "XLSX Exported",
            f"Translation workbook saved successfully:\n{saved_path}\n\n"
            "Only edit the Translated text column before importing it back.",
        )
        return True

    def _import_subtitle_translation_xlsx(self, segments):
        from services import SubtitleExchangeService

        service = SubtitleExchangeService()
        context = self._subtitle_exchange_context(segments)
        state = getattr(self, "current_project_state", None)
        initial_dir = str(getattr(state, "project_root", "") or os.getcwd())
        input_path, _filter = QFileDialog.getOpenFileName(
            self,
            "Import Subtitle Translation XLSX",
            initial_dir,
            "Excel Workbook (*.xlsx)",
        )
        if not input_path:
            return None
        try:
            translated = service.import_translations(
                input_path,
                segments=list(segments or []),
            )
            quality_warnings = service.assess_translation_quality(
                segments=list(segments or []),
                translated_texts=translated,
                target_language=context["target_language"],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Import XLSX Failed", str(exc))
            return None
        if quality_warnings:
            preview = "\n".join(f"• {warning}" for warning in quality_warnings[:10])
            remaining = len(quality_warnings) - 10
            if remaining > 0:
                preview += f"\n• …and {remaining} more warning(s)."
            decision = QMessageBox.warning(
                self,
                "Translation Quality Review",
                "The workbook structure is valid, but semantic QA found items to review:\n\n"
                f"{preview}\n\nImport these translations anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if decision != QMessageBox.Yes:
                self.log(
                    f"[Subtitle Editor] XLSX import paused for semantic review: "
                    f"{len(quality_warnings)} warning(s)."
                )
                return None
        self.log(f"[Subtitle Editor] Validated translation workbook: {input_path}")
        return translated

    def _build_partial_voice_track_after_subtitle_edit(self, *, changed_indices, state, voice_path):
        """Keep unchanged cue audio while muting only edited cue windows."""
        if not state or not voice_path or not os.path.exists(voice_path):
            return ""
        voice_segments_path = str(
            state.artifacts.get("voice_segments", "")
            or self.processed_artifacts.get("voice_segments", "")
        ).strip()
        if not voice_segments_path or not os.path.exists(voice_segments_path):
            return ""
        voice_segments = self.project_service.load_json_artifact(
            state, "voice_segments", default=[]
        ) or []
        if not voice_segments:
            return ""
        try:
            from audio_mixer import mute_voice_windows
            cache_dir = self.get_project_temp_dir("tts")
            os.makedirs(cache_dir, exist_ok=True)
            digest = hashlib.sha1(
                (str(voice_path) + ":" + ",".join(sorted(str(i) for i in changed_indices))).encode("utf-8")
            ).hexdigest()[:12]
            output_path = os.path.join(cache_dir, f"voice_vi_partial_{digest}.wav")
            return mute_voice_windows(
                input_wav_path=voice_path,
                segments=voice_segments,
                changed_indices=changed_indices,
                output_wav_path=output_path,
            )
        except Exception as exc:
            self.log(f"[Subtitle Editor] Could not preserve unchanged voice cues: {exc}")
            return ""

    def _invalidate_dubbed_output_after_subtitle_edit(self, changed_indices=None):
        """Stop old TTS/mix output from being used after subtitle edits.

        Per-cue cache files deliberately remain: VoiceWorkflow keys those
        files by text, voice and speed, so unchanged cues are cache hits on
        the next TTS run.  For a known subtitle edit, the current track is
        replaced by a temporary copy with only edited cue windows muted;
        unknown/global edits still invalidate the assembled track entirely.
        """
        state = self.ensure_current_project()
        changed_indices = set(changed_indices or [])
        previous_voice_path = str(
            getattr(self, "last_voice_vi_path", "")
            or self.processed_artifacts.get("voice_vi", "")
            or (state.artifacts.get("voice_vi", "") if state is not None else "")
        ).strip()
        partial_voice_path = self._build_partial_voice_track_after_subtitle_edit(
            changed_indices=changed_indices,
            state=state,
            voice_path=previous_voice_path,
        ) if changed_indices else ""
        preserve_unchanged_voice = bool(partial_voice_path)
        preview_had_burned_subtitles = bool(
            getattr(self, "_preview_video_has_burned_subtitles", False)
        )
        had_dubbed_output = bool(
            getattr(self, "last_voice_vi_path", "")
            or getattr(self, "last_mixed_vi_path", "")
            or self.processed_artifacts.get("voice_vi")
            or self.processed_artifacts.get("mixed_vi")
        )
        invalidated_artifacts = (
            "mixed_vi", "preview_video", "preview_video_5s", "preview_frame",
        )
        if not preserve_unchanged_voice:
            invalidated_artifacts = (
                "voice_vi", "mixed_vi", "voice_segments",
                "preview_video", "preview_video_5s", "preview_frame",
            )
        for key in invalidated_artifacts:
            self.processed_artifacts.pop(key, None)
            if state is not None:
                state.artifacts.pop(key, None)
        # Segment dictionaries also retain the measured end of the previous
        # TTS clip.  Keeping it after a text/timing/structure edit lets the
        # preview or a later export stretch a new cue using obsolete audio.
        for segments in (
            getattr(self, "current_segments", None),
            getattr(self, "current_translated_segments", None),
        ):
            for segment in list(segments or []):
                if isinstance(segment, dict):
                    segment.pop("_audio_start", None)
                    segment.pop("_audio_end", None)
                    segment.pop("_original_start", None)
                    segment.pop("_original_end", None)
        # The TS1 layer objects may still contain paths to the old assembled
        # voice track.  Clear them too so neither preview nor export can use
        # a deleted/obsolete cue before the next TTS run.
        timeline_model = getattr(getattr(self, "timeline", None), "_timeline", None)
        for track in list(getattr(timeline_model, "tracks", []) or []):
            track_type = str(getattr(getattr(track, "type", ""), "value", getattr(track, "type", ""))).lower()
            if track_type not in {"dub_subtitle", "subtitle"}:
                continue
            for layer in list(getattr(track, "layers", []) or []):
                if hasattr(layer, "audio_path"):
                    layer.audio_path = ""
                if hasattr(layer, "tts_settings"):
                    layer.tts_settings = {}
                metadata = getattr(layer, "metadata", None)
                if isinstance(metadata, dict):
                    metadata.pop("_audio_start", None)
                    metadata.pop("_audio_end", None)
                    metadata.pop("_original_start", None)
                    metadata.pop("_original_end", None)
                if preserve_unchanged_voice and hasattr(layer, "audio_path"):
                    layer.audio_path = partial_voice_path
        self.last_voice_vi_path = partial_voice_path if preserve_unchanged_voice else ""
        self.last_mixed_vi_path = ""
        # Keep the in-memory flag in sync with the project setting.  The
        # subtitle editor persists immediately after this method; without
        # this assignment that save would mistake the temporary muted track
        # for a complete voice render and write a fresh voice signature.
        self._voice_track_partial = preserve_unchanged_voice
        self.last_preview_video_path = ""
        self.last_styled_preview_path = ""
        self.last_styled_preview_signature = ""
        self.last_exact_preview_5s_path = ""
        self.last_exact_preview_frame_path = ""
        self._voiceover_force_refresh = True
        if state is not None:
            state.set_step_status("generate_tts", "pending")
            state.set_step_status("mix_audio", "pending")
            state.settings.pop("voice_signature", None)
            state.set_setting("voice_track_partial", preserve_unchanged_voice)
            if preserve_unchanged_voice:
                state.artifacts["voice_vi"] = partial_voice_path
                self.processed_artifacts["voice_vi"] = partial_voice_path
            self.project_service.save_project(state)
        if had_dubbed_output:
            self.log("[Subtitle Editor] Existing dubbed output invalidated; unchanged cues remain in the TTS cache.")
            self.sync_preview_audio_track_to_output(apply_to_player=True, force=True)
        if preview_had_burned_subtitles:
            # Rendered preview subtitles are pixels. Restore the original
            # media before enabling the live track; otherwise an edited or
            # deleted cue remains visible underneath the new TS1 overlay.
            source_path = self._resolve_preview_original_video_path()
            try:
                position = int(self.media_player.position() or 0)
                was_playing = bool(self.media_player.is_playing())
                self.media_player.pause()
                self.media_player.setSource(
                    QUrl.fromLocalFile(source_path) if source_path else QUrl()
                )
                if source_path and position > 0:
                    self.media_player.setPosition(position)
                if source_path and was_playing:
                    self.media_player.play()
            except Exception as exc:
                self.log(f"[Subtitle] Could not restore original preview source: {exc}")
            self._preview_video_has_burned_subtitles = False

    def _invalidate_translation_after_original_change(self):
        """Clear every downstream artifact after Original timing/text changes."""
        self.current_translated_segments = []
        self.current_translated_segment_models = []
        self.translated_text.clear()
        self.last_translated_srt_path = ""
        self.processed_artifacts.pop("srt_translated", None)
        self._invalidate_dubbed_output_after_subtitle_edit()
        state = self.ensure_current_project()
        if state is None:
            return
        state.set_setting("translation_signature", "")
        for artifact_key in (
            "subtitle_translated_srt",
            "srt_translated",
            "translation_raw",
            "translation_refined",
            "translation_final",
        ):
            state.artifacts.pop(artifact_key, None)
        state.set_step_status("translate_raw", "pending")
        state.set_step_status("refine_translation", "pending")
        self.project_service.save_project(state)

    def _apply_subtitle_editor_changes(self, rows) -> bool:
        """Apply staged content/deletion changes without rewriting cue metadata."""
        source = list(self.current_translated_segments or [])
        original_source = list(self.current_segments or [])
        if not source and original_source:
            source = []
            for original in original_source:
                draft = copy.deepcopy(original)
                draft["source_text"] = str(original.get("text", "") or "")
                draft["text"] = ""
                draft["subtitle_vi"] = ""
                draft["tts_text"] = ""
                source.append(draft)
        if len(rows or []) != len(source):
            QMessageBox.warning(self, "Subtitle Editor", "The subtitle list changed while the editor was open. Reopen it and try again.")
            return False

        updated = []
        updated_original = []
        changed_count = 0
        deleted_count = 0
        changed_indices = set()
        for index, (row, original) in enumerate(zip(rows, source)):
            if bool(row.get("deleted")):
                deleted_count += 1
                changed_indices.add(index)
                continue
            if index < len(original_source):
                updated_original.append(copy.deepcopy(original_source[index]))
            text = str(row.get("text", "") or "").strip()
            if not text:
                QMessageBox.warning(self, "Subtitle Editor", "Use Delete for an unnecessary segment instead of leaving translated text empty.")
                return False
            segment = copy.deepcopy(original)
            old_text = str(segment.get("text", "") or "").strip()
            if text != old_text:
                changed_count += 1
                changed_indices.add(index)
                segment["text"] = text
                segment["subtitle_vi"] = text
                # A changed subtitle must speak the changed text.  Do not
                # retain a manual voice override from the old sentence.
                segment["tts_text"] = ""
                segment["dubbing_vi"] = ""
                segment["voice_edited"] = False
                self._reconcile_manual_highlights(segment)
            updated.append(segment)

        if not changed_count and not deleted_count:
            return True

        self.current_translated_segments = updated
        self.current_translated_segment_models = self._dict_segments_to_models(updated, translated=True)
        if original_source:
            self.current_segments = updated_original
            self.current_segment_models = self._dict_segments_to_models(updated_original, translated=False)
            self._sync_hidden_transcript_text_from_segments()
        self._single_line_split_cache = None
        self._voiceover_force_refresh = bool(changed_count or deleted_count)
        self._sync_hidden_translated_text_from_segments()
        self.refresh_auto_keyword_highlights(force=True)
        self.apply_segments_to_timeline()
        all_subtitles_deleted = not updated and (not original_source or not updated_original)
        # A completely deleted subtitle track has no unchanged cue to keep.
        # Force the normal full invalidation so the old voice file cannot be
        # resurrected as a project artifact after "Delete All".
        self._invalidate_dubbed_output_after_subtitle_edit(
            changed_indices=(None if all_subtitles_deleted else changed_indices)
        )
        if all_subtitles_deleted:
            self.last_original_srt_path = ""
            self.last_translated_srt_path = ""
            for key in ("srt_original", "srt_translated"):
                self.processed_artifacts.pop(key, None)
        self.persist_current_timeline_project_data()
        self._regenerate_original_srt_from_segments()
        # Keep the project-facing translated SRT in sync as well as the
        # JSON/timeline state. Export can then use the edited result without
        # relying on a later preview refresh to rewrite it incidentally.
        self._regenerate_translated_srt_from_segments()
        if not updated:
            # persist_current_timeline_project_data intentionally skips an
            # empty list. Persist an explicit empty translation artifact so
            # a project reopened after "Delete All" cannot resurrect its
            # former subtitles from translation_final.json.
            self.persist_translation_project_data([], "" if all_subtitles_deleted else self.last_translated_srt_path)
        if all_subtitles_deleted:
            state = self.ensure_current_project()
            if state is not None:
                if original_source:
                    self.current_segment_models = self.project_bridge.persist_transcription(
                        state,
                        [],
                        "",
                    )
                for artifact_key in (
                    "subtitle_original_srt",
                    "srt_original",
                    "subtitle_translated_srt",
                    "srt_translated",
                ):
                    state.artifacts.pop(artifact_key, None)
                state.set_setting("transcription_signature", "")
                state.set_setting("translation_signature", "")
                state.set_step_status("transcribe", "pending")
                state.set_step_status("translate_raw", "pending")
                state.set_step_status("refine_translation", "pending")
                self.project_service.save_project(state)
        self.schedule_live_subtitle_preview_refresh()
        self.schedule_auto_frame_preview()
        self.sync_segment_editor_rows()
        self.refresh_ui_state()
        self.log(
            f"[Subtitle Editor] Updated translated subtitles: changed={changed_count}, deleted={deleted_count}, unchanged={len(updated) - changed_count}."
        )
        QMessageBox.information(
            self,
            "Subtitle Editor Updated",
            f"Updated {changed_count} subtitle segment(s); deleted {deleted_count}.\n"
            "Timeline timing, speaker assignments, and styles were preserved.\n"
            "Run TTS again only if you need dubbed audio; unchanged lines reuse their cache.",
        )
        return True



    def setup_media_player(self):
        if getattr(self, "_media_backend_ready", False):
            return
        previous_speed = getattr(self, "_preview_speed", 1.0)
        setup_media_player_impl(self)
        self._preview_speed = previous_speed
        self._media_backend_ready = True
        if hasattr(self, "media_player"):
            try:
                self.media_player.set_playback_rate(previous_speed)
            except Exception:
                pass

    def browse_video(self):
        browse_video_impl(self)

    def browse_audio_folder(self):
        browse_audio_folder_impl(self)

    def browse_srt_output_folder(self):
        browse_srt_output_folder_impl(self)

    def browse_audio_source(self):
        browse_audio_source_impl(self)

    def browse_background_audio(self):
        browse_background_audio_impl(self)

    def browse_existing_mixed_audio(self):
        browse_existing_mixed_audio_impl(self)

    def browse_voice_output_folder(self):
        browse_voice_output_folder_impl(self)

    def _get_voiceover_segments(self):
        source_segments = list(self.current_translated_segments or [])
        if not source_segments:
            translated_srt = self.translated_text.toPlainText().strip()
            if translated_srt:
                return self._apply_speaker_voice_assignments(self.parse_srt_to_segments(translated_srt))
            # Fallback to transcript if no translation exists
            if self.current_segments:
                return self._apply_speaker_voice_assignments(list(self.current_segments))
            transcript_srt = getattr(self, "transcript_text", None)
            if transcript_srt:
                text = transcript_srt.toPlainText().strip()
                if text:
                    return self._apply_speaker_voice_assignments(self.parse_srt_to_segments(text))
            return []

        grouped_segments = []
        idx = 0
        while idx < len(source_segments):
            segment = dict(source_segments[idx])
            group_id = str(segment.get('tts_group_id', '') or '').strip()
            tts_text = self._resolve_segment_voice_text(segment)
            if not group_id:
                segment['text'] = tts_text
                segment['tts_text'] = str(segment.get('tts_text') or '').strip() if bool(segment.get('voice_edited')) else ''
                grouped_segments.append(segment)
                idx += 1
                continue

            group_items = [segment]
            cursor = idx + 1
            while cursor < len(source_segments):
                candidate = source_segments[cursor]
                if str(candidate.get('tts_group_id', '') or '').strip() != group_id:
                    break
                group_items.append(dict(candidate))
                cursor += 1

            voice_text = ""
            voice_edited = False
            for item in group_items:
                if bool(item.get('voice_edited')):
                    candidate_text = " ".join(str(item.get('tts_text') or item.get('dubbing_vi') or '').split()).strip()
                    if candidate_text:
                        voice_text = candidate_text
                        voice_edited = True
                        break
            if not voice_text:
                voice_text = ' '.join(
                    ' '.join(str(item.get('text') or '').split()).strip()
                    for item in group_items
                ).strip()

            grouped_segments.append({
                'start': float(group_items[0].get('tts_group_start', group_items[0].get('start', 0.0)) or group_items[0].get('start', 0.0)),
                'end': float(group_items[-1].get('tts_group_end', group_items[-1].get('end', 0.0)) or group_items[-1].get('end', 0.0)),
                'text': voice_text,
                'tts_text': voice_text if voice_edited else '',
                'tts_group_id': group_id,
                'voice_edited': voice_edited,
                'source_text': ' '.join(
                    ' '.join(str(item.get('source_text') or item.get('text') or '').split()).strip()
                    for item in group_items
                ).strip(),
                'speaker': str(group_items[0].get('speaker', '') or ''),
            })
            idx = cursor
        return self._apply_speaker_voice_assignments(grouped_segments)

    def run_voiceover(self):
        if not self.ensure_required_resources("Voice generation", include_voice=True):
            return
        state = self.ensure_current_project()
        
        segments = self._get_voiceover_segments()
        if not segments and state:
            self.load_project_context(state)
            segments = self._get_voiceover_segments()

        if not segments:
            message = "Voiceover could not start because no subtitle segments were loaded. Run Generate again after transcription/translation completes."
            self.log(f"[Voiceover] {message}")
            pipeline_controller = getattr(self, "pipeline_controller", None)
            if getattr(self, "_pipeline_active", False) and pipeline_controller is not None:
                pipeline_controller.pipeline_fail(message)
            else:
                QMessageBox.warning(self, "Voiceover", message)
            return

        out_dir = self.voice_output_folder_edit.text().strip() or os.path.join(self.workspace_root, "output")
        bg_path = self.resolve_background_audio_path()
        audio_handling_mode = self.get_audio_handling_mode()
        voice_name = self._resolve_active_voice_name(persist_new_clone=True)
        if not voice_name:
            QMessageBox.warning(self, "Missing Voice", "Choose a voice first.")
            return
        if state is not None and state.settings.get("tts_skipped", False):
            # Starting TTS explicitly re-enables the generated voice path.
            state.set_setting("tts_skipped", False)
            self.project_service.save_project(state)
        voice_speed = self._parse_voice_speed_value()
        timing_sync_mode = str(self.voice_timing_sync_combo.currentText()).strip()
        original_volume = int(self.audio_a1_volume_slider.value()) if hasattr(self, "audio_a1_volume_slider") else 50
        dub_volume = int(self.audio_a2_volume_slider.value()) if hasattr(self, "audio_a2_volume_slider") else 100
        voice_signature = self.build_current_voice_signature(segments=segments, background_path=bg_path)
        if state and voice_signature:
            force_refresh = bool(getattr(self, "_voiceover_force_refresh", False))
            cached_voice_signature = str(state.settings.get("voice_signature", "") or "").strip()
            cached_voice_track = self._normalize_local_file_path(state.artifacts.get("voice_vi", "") or self.last_voice_vi_path)
            cached_mixed_track = self._normalize_local_file_path(state.artifacts.get("mixed_vi", "") or self.last_mixed_vi_path)
            required_output = cached_mixed_track if bg_path else cached_voice_track
            self.log(
                f"[Voiceover] Cache check: force={force_refresh}, "
                f"cached_sig={'<empty>' if not cached_voice_signature else cached_voice_signature[:16]+'...'}, "
                f"new_sig={'<empty>' if not voice_signature else voice_signature[:16]+'...'}, "
                f"match={cached_voice_signature == voice_signature}, "
                f"required_output={required_output}, exists={os.path.exists(required_output) if required_output else False}"
            )
            if not force_refresh and cached_voice_signature == voice_signature and required_output and os.path.exists(required_output):
                self.last_voice_vi_path = cached_voice_track if cached_voice_track and os.path.exists(cached_voice_track) else self.last_voice_vi_path
                self.last_mixed_vi_path = cached_mixed_track if cached_mixed_track and os.path.exists(cached_mixed_track) else ""
                if self.last_voice_vi_path:
                    self.processed_artifacts["voice_vi"] = self.last_voice_vi_path
                    self.update_project_artifact("voice_vi", self.last_voice_vi_path)
                    self.update_project_step("generate_tts", "done")
                if bg_path:
                    if self.last_mixed_vi_path:
                        self.processed_artifacts["mixed_vi"] = self.last_mixed_vi_path
                        self.update_project_artifact("mixed_vi", self.last_mixed_vi_path)
                        self.update_project_step("mix_audio", "done")
                    else:
                        self.update_project_step("mix_audio", "skipped")
                self.log("[Voiceover] Reusing existing generated audio. Generate did not call TTS again.")
                self.progress_bar.setValue(100)
                self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)
                self.refresh_ui_state()
                self._pipeline_advance("voiceover")
                return

        combo_text = self.free_voice_combo.currentText() if hasattr(self, "free_voice_combo") else ""
        combo_data = self.free_voice_combo.currentData() if hasattr(self, "free_voice_combo") else ""
        combo_id = self.free_voice_combo.currentData(self.VOICE_ENTRY_ID_ROLE) if hasattr(self, "free_voice_combo") else ""
        self.log(f"[Voiceover] Selected voice: text='{combo_text}', data='{combo_data}', id='{combo_id}'")

        self.log(
            "[Voiceover] Starting with "
            f"audio_mode={audio_handling_mode}, "
            f"voice={voice_name}, "
            f"speed={voice_speed:.2f}, "
            f"segments={len(segments)}, "
            f"background={bg_path or '<none>'}"
        )
        if state:
            self.log(
                "[Voiceover] State snapshot: "
                f"project={state.project_root}, "
                f"steps={dict(state.steps)}, "
                f"artifacts={dict(state.artifacts)}"
            )

        try:
            self.media_player.pause()
            self.timeline.set_playing(False)
        except Exception:
            pass

        if hasattr(self, "voiceover_btn"):
            self.voiceover_btn.setEnabled(False)
            self.voiceover_btn.setText("Generating... (TTS)")
        self.progress_bar.setValue(85)
        self._voice_generation_active = True
        self._pending_voice_background_path = str(bg_path or "")
        self.update_project_step("generate_tts", "running")
        if bg_path:
            self.update_project_step("mix_audio", "running")
        self.refresh_ui_state()
        try:
            QApplication.processEvents()
        except Exception:
            pass
        self._pending_voice_signature = voice_signature

        project_state_path = self.project_service.project_file(self.current_project_state.project_root) if self.current_project_state else ""

        # Stop any previously running voice thread before creating a new one.
        # Overwriting self.voice_thread without stopping it causes:
        # "QThread: Destroyed while thread '' is still running"
        old_voice_thread = getattr(self, "voice_thread", None)
        if old_voice_thread is not None:
            try:
                if old_voice_thread.isRunning():
                    old_voice_thread.requestInterruption()
                    old_voice_thread.quit()
                    if not old_voice_thread.wait(3000):  # wait up to 3s
                        old_voice_thread.terminate()
                        old_voice_thread.wait(1000)
            except RuntimeError:
                pass  # C++ object already deleted
            self.voice_thread = None

        self.voice_thread = VoiceOverWorker(
            self.workspace_root,
            segments,
            out_dir,
            bg_path,
            audio_handling_mode,
            voice_name,
            voice_speed,
            timing_sync_mode,
            original_volume,
            dub_volume,
            project_state_path,
            self.get_project_temp_dir("tts"),
            self.is_ai_dubbing_rewrite_enabled() and self.get_output_mode_key() in ("voice", "both"),
            self.get_ai_dubbing_style_instruction(),
            self.get_source_language_code(),
        )
        pipeline_controller = getattr(self, "pipeline_controller", None)
        if pipeline_controller is not None:
            self.voice_thread.progress.connect(pipeline_controller.on_voiceover_progress)
        else:
            self.voice_thread.progress.connect(self.log)
        worker = self.voice_thread
        worker.finished.connect(self.on_voiceover_finished)
        worker.finished.connect(
            lambda *_args, worker=worker: release_thread_when_stopped(
                worker,
                lambda: setattr(self, "voice_thread", None)
                if getattr(self, "voice_thread", None) is worker
                else None,
            )
        )
        self.voice_thread.start()

    def _apply_generated_tts_texts(self, voice_segments):
        source_segments = self.current_translated_segments
        if not source_segments or not voice_segments:
            return False

        updated = False
        grouped_updates = {}
        positional_updates = []
        for seg in list(voice_segments or []):
            tts_text = ' '.join(str((seg or {}).get("tts_text") or (seg or {}).get("text") or "").split()).strip()
            if not tts_text:
                continue
            subtitle_vi = ' '.join(str((seg or {}).get("subtitle_vi") or (seg or {}).get("text") or "").split()).strip()
            dubbing_vi = ' '.join(str((seg or {}).get("dubbing_vi") or tts_text).split()).strip()
            action_taken = str((seg or {}).get("action_taken") or "").strip().lower()
            ratio = float((seg or {}).get("ratio") or 0.0)
            group_id = str((seg or {}).get("tts_group_id") or "").strip()
            try:
                new_start = float((seg or {}).get("start", 0.0))
                new_end = float((seg or {}).get("end", 0.0))
            except (TypeError, ValueError):
                new_start = new_end = None
            try:
                new_audio_end = float((seg or {}).get("_audio_end")) if (seg or {}).get("_audio_end") is not None else None
            except (TypeError, ValueError):
                new_audio_end = None
            try:
                new_audio_start = float((seg or {}).get("_audio_start")) if (seg or {}).get("_audio_start") is not None else None
            except (TypeError, ValueError):
                new_audio_start = None
            payload = {
                "tts_text": tts_text,
                "subtitle_vi": subtitle_vi,
                "dubbing_vi": dubbing_vi,
                "action_taken": action_taken,
                "ratio": ratio,
                "attempt_count": int((seg or {}).get("attempt_count") or 1),
                "start": new_start,
                "end": new_end,
                "_audio_start": new_audio_start,
                "_audio_end": new_audio_end,
            }
            if group_id:
                grouped_updates[group_id] = payload
            else:
                positional_updates.append(payload)

        positional_index = 0
        for seg in source_segments:
            group_id = str((seg or {}).get("tts_group_id") or "").strip()
            if group_id and group_id in grouped_updates:
                next_payload = grouped_updates[group_id]
            elif positional_index < len(positional_updates):
                next_payload = positional_updates[positional_index]
                positional_index += 1
            else:
                continue

            next_tts_text = next_payload["tts_text"]
            current_tts_text = ' '.join(str(seg.get("tts_text") or "").split()).strip()
            if current_tts_text != next_tts_text:
                seg["tts_text"] = next_tts_text
                updated = True
            seg["subtitle_vi"] = next_payload["subtitle_vi"]
            seg["dubbing_vi"] = next_payload["dubbing_vi"]
            seg["action_taken"] = next_payload["action_taken"]
            seg["ratio"] = next_payload["ratio"]
            seg["attempt_count"] = next_payload["attempt_count"]
            # Keep source/timeline start/end immutable.  TTS can be queued
            # after a dense cue, but that scheduling belongs in audio metadata
            # and must never move the burned-in subtitle or all later cues.
            new_audio_start = next_payload.get("_audio_start")
            if new_audio_start is not None:
                if seg.get("_audio_start") != new_audio_start:
                    updated = True
                seg["_audio_start"] = new_audio_start
            else:
                if "_audio_start" in seg:
                    updated = True
                seg.pop("_audio_start", None)
            new_audio_end = next_payload.get("_audio_end")
            if new_audio_end is not None:
                if seg.get("_audio_end") != new_audio_end:
                    updated = True
                seg["_audio_end"] = new_audio_end
            else:
                if "_audio_end" in seg:
                    updated = True
                seg.pop("_audio_end", None)
        return updated

    def _regenerate_translated_srt_from_segments(self):
        """Regenerate the project SRT from the visual subtitle timeline."""
        out_path = str(getattr(self, "last_translated_srt_path", "") or "").strip()
        if not out_path:
            return
        try:
            from subtitle_builder import generate_srt
            generate_srt(self.current_translated_segments, out_path)
        except Exception as exc:
            print(f"[Voice] SRT regen failed: {exc}")
            return
        self.processed_artifacts["srt_translated"] = out_path
        self.persist_translation_project_data(self.current_translated_segments, out_path)

    def _regenerate_original_srt_from_segments(self):
        """Keep the project-facing Original SRT aligned with timeline edits."""
        out_path = str(getattr(self, "last_original_srt_path", "") or "").strip()
        if not out_path:
            return
        try:
            from subtitle_builder import generate_srt
            generate_srt(self.current_segments or [], out_path)
        except Exception as exc:
            print(f"[Subtitle] Original SRT regen failed: {exc}")
            return
        self.processed_artifacts["srt_original"] = out_path
        self.persist_transcription_project_data(self.current_segments or [], out_path)

    def on_voiceover_finished(self, voice_track, mixed, voice_segments, error):
        pending_background_path = str(
            getattr(self, "_pending_voice_background_path", "") or ""
        ).strip()
        self._voice_generation_active = False
        if hasattr(self, "voiceover_btn"):
            self.voiceover_btn.setEnabled(True)
            self.voiceover_btn.setText("Generate Voice / Mix")
        self.progress_bar.setValue(100)

        if error:
            self._voiceover_force_refresh = False
            self._pending_voice_signature = ""
            self.update_project_step("generate_tts", "failed")
            if pending_background_path:
                self.update_project_step("mix_audio", "failed")
            elif (
                self.current_project_state
                and self.current_project_state.steps.get("mix_audio") == "running"
            ):
                self.update_project_step("mix_audio", "skipped")
            self._pending_voice_background_path = ""
            QMessageBox.critical(self, "Error", f"Voiceover failed:\n\n{error}")
            self._pipeline_fail("Voiceover failed.")
            self.refresh_ui_state()
            return

        if hasattr(self, "audio_tab_btn"):
            self.audio_tab_btn.setEnabled(True)

        if voice_track and os.path.exists(voice_track):
            self._voice_track_partial = False
            self.last_voice_vi_path = voice_track
            self.processed_artifacts["voice_vi"] = voice_track
            self.update_project_artifact("voice_vi", voice_track)
            self.update_project_step("generate_tts", "done")
        if mixed and os.path.exists(mixed):
            self.last_mixed_vi_path = mixed
            self.processed_artifacts["mixed_vi"] = mixed
            self.update_project_artifact("mixed_vi", mixed)
            self.update_project_step("mix_audio", "done")
        elif pending_background_path or (
            self.current_project_state
            and self.current_project_state.steps.get("mix_audio") == "running"
        ):
            self.update_project_step("mix_audio", "skipped")
        if self._apply_generated_tts_texts(voice_segments):
            self._single_line_split_cache = None
            self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
            self._sync_hidden_translated_text_from_segments()
            self.apply_segments_to_timeline()
            if hasattr(self, "timeline") and voice_track:
                self.timeline.sync_tts_track(
                    voice_track,
                    segments=self.current_translated_segments or self.current_segments,
                )
                if hasattr(self, "voice_timing_sync_combo"):
                    self.timeline.set_voice_sync_mode(self.voice_timing_sync_combo.currentText())
            self._sync_timeline_mute_to_gui()
            self.persist_current_timeline_project_data()
            # Regenerate the project SRT from the unchanged visual subtitle
            # timings. TTS queue placement is stored separately as metadata.
            self._regenerate_translated_srt_from_segments()
            self.schedule_live_subtitle_preview_refresh()
            self.sync_segment_editor_rows()
        if self.current_project_state:
            self.current_project_state.set_setting("voice_track_partial", False)
            voice_signature = self.build_current_voice_signature(
                segments=self._get_voiceover_segments(),
                background_path=self.resolve_background_audio_path(),
            )
            if voice_signature:
                self.current_project_state.set_setting("voice_signature", voice_signature)
                self.project_service.save_project(self.current_project_state)
        self._voiceover_force_refresh = False
        self._pending_voice_signature = ""
        self._pending_voice_background_path = ""

        try:
            self._pipeline_advance("voiceover")
        except Exception as exc:
            self.log(f"[Voiceover] pipeline_advance failed: {exc}")
            self.refresh_ui_state()

        if mixed:
            self.log(f"[Voiceover] Generated Vietnamese voice and mixed audio: Voice={voice_track}, Mixed={mixed}")
        else:
            self.log(f"[Voiceover] Generated Vietnamese voice track: {voice_track} (No background mix created.)")

        # One concise completion record replaces the per-cue TTS spam.
        completed_tts = len(voice_segments or self._get_voiceover_segments() or [])
        self.log(f"✓ TTS completed — {completed_tts}/{completed_tts}")

        self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)
        self.refresh_ui_state()
        self.sync_preview_audio_track_to_output()

    def preview_video(self):
        self.preview_controller.preview_video()

    def on_preview_ready(self, preview_path, error, styled_signature=""):
        self.preview_controller.on_preview_ready(preview_path, error, styled_signature)

    def smart_generate(self):
        if getattr(self, "_pipeline_active", False):
            return
        has_subtitles = bool(self.current_segments)
        has_translated = bool(self.current_translated_segments and self.translated_text.toPlainText().strip())
        mode = self.get_output_mode_key()
        need_voice = mode in ("voice", "both")

        if not has_subtitles or (not has_translated and mode != "voice"):
            self.run_all_pipeline()
        elif need_voice:
            self.run_voiceover_with_progress()
        else:
            self.preview_video()

    def run_voiceover_with_progress(self, target_stage="full"):
        existing = getattr(self, "voice_thread", None)
        if existing and existing.isRunning():
            return
        self._pipeline_active = True
        self._pipeline_step = "voiceover"
        self.pipeline_controller.target_stage = str(target_stage or "full")
        if hasattr(self, "run_all_btn"):
            self.run_all_btn.setEnabled(False)
            self.run_all_btn.setText("Processing...")
        self.pipeline_controller._setup_progress_dialog(includes_separation=False)
        self.pipeline_controller.progress_dialog.skip_step("ai_process")
        self.pipeline_controller.progress_dialog.start_step("voiceover")
        self._voiceover_force_refresh = True
        self.run_voiceover()

    def run_pipeline_to_stage(self, target_stage: str):
        target_stage = str(target_stage or "full").strip().lower()
        if target_stage not in {"transcript", "translate", "tts"}:
            self.run_all_pipeline()
            return
        has_transcript = bool(self.current_segments or self.transcript_text.toPlainText().strip())
        has_translation = bool(self._get_voiceover_segments())
        if target_stage == "translate" and not has_transcript:
            QMessageBox.information(self, "Step-by-Step", "Complete Transcript before running Translate.")
            return
        if target_stage == "translate" and has_translation:
            # A deliberate re-translate must bypass the finished-translation
            # cache.  Keep the transcript cache intact, so this does not
            # repeat audio extraction or transcription.
            state = self.ensure_current_project()
            if state is not None:
                state.set_setting("translation_signature", "")
                state.set_step_status("translate_raw", "pending")
                state.set_step_status("refine_translation", "pending")
                self.project_service.save_project(state)
            self.log("[Translation] Re-translate requested; reusing the existing transcript.")
        if target_stage == "translate":
            # Translate is independent once TS1 exists.  Do not send this
            # request through PrepareWorkflow: that workflow begins at audio
            # extraction/transcription and can rerun OCR/ASR when a cache
            # signature changes.
            if not self.transcript_text.toPlainText().strip() and self.current_segments:
                self.transcript_text.setText(self.format_to_srt(self.current_segments))
            self.log("[Pipeline] Translate requested; using the completed transcript only.")
            self.run_translation()
            return
        if target_stage == "tts" and not has_translation:
            QMessageBox.information(self, "Step-by-Step", "Complete Translate before running Generate Voice / TTS.")
            return
        if target_stage == "tts" and has_translation:
            self.run_voiceover_with_progress(target_stage="tts")
            return
        if target_stage == "transcript":
            # A transcript-only run must not keep displaying or restoring a
            # translation from an earlier run of the same project.
            state = self.ensure_current_project()
            self.current_translated_segments = []
            self.current_translated_segment_models = []
            self.last_translated_srt_path = ""
            self.processed_artifacts.pop("srt_translated", None)
            if hasattr(self, "translated_text"):
                self.translated_text.clear()
            if state is not None:
                for artifact_name in (
                    "translation_raw",
                    "translation_refined",
                    "translation_final",
                    "subtitle_translated_srt",
                    "srt_translated",
                ):
                    state.artifacts.pop(artifact_name, None)
                state.settings.pop("translation_signature", None)
                state.set_step_status("translate_raw", "pending")
                state.set_step_status("refine_translation", "pending")
                self.project_service.save_project(state)
            if hasattr(self, "media_player"):
                self.media_player.clear_subtitle()
            if hasattr(self, "timeline"):
                self.timeline.set_segments(list(self.current_segments or []))
            self.log("[Pipeline] Transcript-only requested; cleared stale translated subtitle state.")
        mode = self.get_output_mode_key()
        include_voice = target_stage == "tts" and mode in ("voice", "both")
        is_ocr = self.get_transcription_engine() == "ocr"
        if not self.ensure_required_resources(
            "Generate",
            include_whisper=not is_ocr,
            include_voice=include_voice,
            include_ocr=is_ocr,
            validate_pipeline_runtime=True,
        ):
            return
        self.pipeline_controller.run_all_pipeline(target_stage=target_stage)

    def skip_tts_stage(self):
        """Explicitly finish the optional TTS phase after translation."""
        has_translation = bool(self._get_voiceover_segments())
        if not has_translation:
            QMessageBox.information(self, "Skip TTS", "Complete Translate before skipping Generate Voice / TTS.")
            return
        state = self.ensure_current_project()
        if state is not None:
            state.set_setting("tts_skipped", True)
            state.set_step_status("generate_tts", "skipped")
            state.set_step_status("mix_audio", "skipped")
            self.project_service.save_project(state)
        self._voiceover_force_refresh = True
        self.log("[Pipeline] Generate Voice / TTS skipped. The translated subtitle video is ready to export.")
        self.refresh_ui_state()

    def run_all_pipeline(self):
        mode = self.get_output_mode_key()
        include_voice = mode in ("voice", "both")
        is_ocr = self.get_transcription_engine() == "ocr"
        if not self.ensure_required_resources(
            "Generate",
            include_whisper=not is_ocr,
            include_voice=include_voice,
            include_ocr=is_ocr,
            validate_pipeline_runtime=True,
        ):
            return
        self.pipeline_controller.run_all_pipeline(target_stage="full")

    def on_prepare_workflow_finished(self, project_state_path, error):
        self.pipeline_controller.on_prepare_workflow_finished(project_state_path, error)

    def _pipeline_advance(self, completed_step: str):
        self.pipeline_controller.pipeline_advance(completed_step)

    def _pipeline_fail(self, reason: str):
        self.pipeline_controller.pipeline_fail(reason)

    def _pipeline_done(self):
        self.pipeline_controller.pipeline_done()

    def open_folder(self, path):
        open_folder_impl(self, path)

    def show_processed_files(self):
        show_processed_files_impl(self)

    def cleanup_temp_preview_files(self):
        cleanup_temp_preview_files_impl(self)

    def _path_within_root(self, path: str, root: str) -> bool:
        return self.project_controller.path_within_root(path, root)

    def _remove_path_if_safe(self, path: str, *, allowed_roots: list[str], removed: list[str]) -> None:
        return self.project_controller.remove_path_if_safe(path, allowed_roots=allowed_roots, removed=removed)

    def _reset_project_runtime_state(self) -> None:
        return self.project_controller.reset_project_runtime_state()

    def _has_cleanable_project_data(self) -> bool:
        return self.project_controller.has_cleanable_project_data()

    def exit_to_launcher(self):
        self._return_to_launcher(project_removed_from_recent=False)

    def clean_current_project(self):
        project_state = getattr(self, "current_project_state", None)
        if not self._has_cleanable_project_data():
            QMessageBox.information(self, "Clean Project", "There is no generated project data to clean right now.")
            return

        confirmation = QMessageBox.question(
            self,
            "Clean Project",
            "This will remove intermediate project files, temp previews, separated audio, cached TTS files, and this video's timeline media cache.\n\n"
            "It will keep your source video, imported assets, and final exported video.\n\n"
            "Do you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return

        removed_paths = []
        removed_groups = {
            "Project folder": [],
            "Generated voice files": [],
            "Separated audio": [],
            "Preview temp files": [],
            "TTS cache": [],
            "Temp folders": [],
            "Timeline media cache": [],
            "Launcher media cache": [],
        }
        project_temp_root = self.get_project_temp_root()
        output_root = os.path.join(self.workspace_root, "output")
        project_root = str(getattr(project_state, "project_root", "") or "").strip()
        project_id = str(getattr(project_state, "project_id", "") or "").strip()
        if not project_id and project_root:
            project_id = os.path.basename(os.path.normpath(project_root))
        project_state_path = self.project_service.project_file(project_root) if project_root else ""
        allowed_roots = [root for root in [project_temp_root, output_root, project_root] if root]

        # Stop active workers and pending persistence before deleting files.
        # Otherwise a late worker/timer can recreate the selected project's
        # cache or timeline after it has just been removed.
        self._terminate_workers()
        # Release MPV/QMediaPlayer handles before deleting extracted audio or
        # project files. Windows keeps a stopped sidecar source locked until
        # it is explicitly unloaded, which previously made the first cleanup
        # attempt report WinError 32.
        media_player = getattr(self, "media_player", None)
        if media_player is not None:
            try:
                media_player.clear_audio()
            except Exception:
                pass
            try:
                media_player._clear_original_audio()
            except Exception:
                pass
            try:
                from PySide6.QtCore import QUrl
                media_player.setSource(QUrl())
            except Exception:
                pass
            try:
                QApplication.processEvents()
            except Exception:
                pass
        persist_timer = getattr(self, "_timeline_persist_timer", None)
        if persist_timer is not None:
            persist_timer.stop()
        self._pending_timeline_persist = False
        self._pending_mask_state_persist = False
        self._pending_blur_state_persist = False

        self.cleanup_temp_preview_files()

        file_candidates = [
            ("Separated audio", self.last_extracted_audio),
            ("Separated audio", self.last_vocals_path),
            ("Separated audio", self.last_music_path),
            ("Generated voice files", self.last_voice_vi_path),
            ("Generated voice files", self.last_mixed_vi_path),
            ("Preview temp files", self.live_preview_subtitle_path),
            ("Preview temp files", self.live_preview_ass_path),
            ("Preview temp files", self.last_styled_preview_path),
            ("Project folder", project_state_path),
        ]
        for group_name, candidate in file_candidates:
            before_count = len(removed_paths)
            self._remove_path_if_safe(candidate, allowed_roots=allowed_roots, removed=removed_paths)
            if len(removed_paths) > before_count:
                removed_groups[group_name].append(removed_paths[-1])

        dir_candidates = [
            ("Project folder", project_root),
            ("TTS cache", self.get_project_temp_path("tts")),
            ("Temp folders", self.get_project_temp_path("segment_audio_preview")),
            ("Temp folders", self.get_project_temp_path("voice_sample_preview")),
            ("Temp folders", self.get_project_temp_path("htdemucs")),
            ("Temp folders", self.get_project_temp_path("timeline_video_thumbs")),
            ("Temp folders", project_temp_root),
        ]
        for group_name, candidate in dir_candidates:
            before_count = len(removed_paths)
            self._remove_path_if_safe(candidate, allowed_roots=allowed_roots, removed=removed_paths)
            if len(removed_paths) > before_count:
                removed_groups[group_name].append(removed_paths[-1])

        # Older builds stored a few per-project temporary files directly in
        # temp/<project_id>.  Remove that exact legacy directory only; never
        # remove the shared temp root or another project's folder.
        if project_id:
            legacy_project_temp = os.path.join(self.get_workspace_temp_root(), project_id)
            before_count = len(removed_paths)
            self._remove_path_if_safe(
                legacy_project_temp,
                allowed_roots=[self.get_workspace_temp_root()],
                removed=removed_paths,
            )
            if len(removed_paths) > before_count:
                removed_groups["Temp folders"].append(removed_paths[-1])

        # V1/A1 visual assets live in the shared temp root because they are
        # prepared in the launcher before a project context exists. Remove
        # only files whose digest belongs to this source video; caches for
        # other projects remain untouched.
        source_video = self._normalize_local_file_path(
            self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        )
        if source_video:
            source = os.path.abspath(source_video)
            # Some older code paths keyed cache files by the user-provided
            # path while newer ones use the normalized absolute path. Remove
            # both keys for this one selected source video.
            digest_sources = {source, source_video}
            digests = {
                hashlib.md5(cache_source.encode("utf-8")).hexdigest()[:12]
                for cache_source in digest_sources
            }
            full_digests = {
                hashlib.md5(cache_source.encode("utf-8")).hexdigest()
                for cache_source in digest_sources
            }
            temp_root = self.get_workspace_temp_root()
            timeline_cache_paths = []
            for digest in digests:
                timeline_cache_paths.extend([
                    os.path.join(temp_root, f"waveform_{digest}.wav"),
                    os.path.join(temp_root, "timeline_visuals", f"{digest}.json"),
                ])
            thumb_dir = os.path.join(temp_root, "timeline_thumbnails")
            if os.path.isdir(thumb_dir):
                for digest in digests:
                    timeline_cache_paths.extend(
                        glob.glob(os.path.join(thumb_dir, f"launcher_{digest}_*.jpg"))
                    )
            for candidate in timeline_cache_paths:
                before_count = len(removed_paths)
                self._remove_path_if_safe(candidate, allowed_roots=[temp_root], removed=removed_paths)
                if len(removed_paths) > before_count:
                    removed_groups["Timeline media cache"].append(removed_paths[-1])

            # The launcher card thumbnail has its own full-MD5 filename.
            # It belongs solely to this source video, so cleaning this project
            # can safely remove it without touching other recent projects.
            launcher_thumb_root = os.path.join(temp_root, "launcher_thumbs")
            for digest in full_digests:
                before_count = len(removed_paths)
                self._remove_path_if_safe(
                    os.path.join(launcher_thumb_root, f"{digest}.jpg"),
                    allowed_roots=[temp_root],
                    removed=removed_paths,
                )
                if len(removed_paths) > before_count:
                    removed_groups["Launcher media cache"].append(removed_paths[-1])

        self._reset_project_runtime_state()

        if removed_paths:
            self.log(f"[Clean Project] Removed {len(removed_paths)} intermediate paths.")
            detail_lines = ["Cleaned these groups:"]
            for group_name, paths in removed_groups.items():
                if paths:
                    detail_lines.append(f"- {group_name}: {len(paths)} item(s)")
            QMessageBox.information(
                self,
                "Clean Project",
                f"Removed {len(removed_paths)} intermediate paths for the current project.\n\n" + "\n".join(detail_lines),
            )
        else:
            QMessageBox.information(
                self,
                "Clean Project",
                "No removable intermediate files were found for the current project.",
            )
        # The project directory above has intentionally been deleted. Do not
        # persist the in-memory timeline while returning to the launcher,
        # because that would recreate projects/<project_id>/timeline.json.
        self._return_to_launcher(
            project_removed_from_recent=True,
            persist_project_data=False,
        )

    def _return_to_launcher(self, project_removed_from_recent=True, *, persist_project_data=True):
        # Keep the complete saved timeline when returning to the launcher.
        # Optional tracks (Text, Logo, Blur, Mask) are part of the project
        # state and must be available when that project is reopened.
        if persist_project_data:
            try:
                self.persist_current_timeline_project_data()
            except Exception:
                pass
                
        # Stop pending timeline persist timer so it doesn't fire after returning to launcher
        persist_timer = getattr(self, "_timeline_persist_timer", None)
        if persist_timer is not None:
            persist_timer.stop()
        self._pending_timeline_persist = False
        self._pending_mask_state_persist = False
        self._pending_blur_state_persist = False
        
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else getattr(self, "_current_video_path", "")
        self.log(f"[Clean] _return_to_launcher: video_path={video_path}")
        if video_path and project_removed_from_recent:
            try:
                from views.launcher import _load_recent_projects, _save_recent_projects
                projects = _load_recent_projects()
                projects = [p for p in projects if os.path.normpath(p.get("video_path", "")) != os.path.normpath(video_path)]
                _save_recent_projects(None, projects)
                self.log(f"[Clean] Removed from recent: {video_path} -> {len(projects)} remaining")
            except Exception as e:
                self.log(f"[Clean] Failed: {e}")
        self._current_video_path = ""
        self._terminate_workers()
        self.hide()
        self.deleteLater()
        QApplication.setQuitOnLastWindowClosed(False)
        QTimer.singleShot(100, lambda: relaunch_launcher(self.__class__))

    def _terminate_workers(self):
        # Stop local worker process server immediately
        if hasattr(self, "pipeline_controller") and hasattr(self.pipeline_controller, "_stop_local_worker_server"):
            try:
                self.pipeline_controller._stop_local_worker_server()
            except Exception:
                pass

        # Stop media players and release file locks
        from PySide6.QtCore import QUrl
        if hasattr(self, "media_player"):
            try:
                self.media_player.stop()
                self.media_player.setSource(QUrl())
            except Exception:
                pass
        if hasattr(self, "audio_preview_player"):
            try:
                self.audio_preview_player.stop()
                self.audio_preview_player.setSource(QUrl())
            except Exception:
                pass

        attrs = [
            "extraction_thread",
            "vocal_thread",
            "voice_thread",
            "_voice_sample_preview_thread",
            "transcription_thread",
            "_alternate_range_transcription_worker",
            "translation_thread",
            "rewrite_translation_thread",
            "prepare_workflow_thread",
            "export_thread",
            "quick_preview_thread",
            "frame_preview_thread",
            "preview_thread",
            "_timeline_waveform_worker",
            "_timeline_thumbnail_worker",
            "_resource_worker",
            "_ocr_translator_capture_worker",
            "_ocr_translator_translation_worker",
            "_ocr_region_worker",
        ]
        for name in attrs:
            worker = getattr(self, name, None)
            if worker is not None:
                try:
                    if getattr(worker, "isRunning", lambda: False)():
                        worker.requestInterruption()
                        worker.quit()
                        if not worker.wait(50):
                            worker.terminate()
                            worker.wait(50)
                except Exception:
                    pass
                setattr(self, name, None)

        threads_dict = getattr(self, "_segment_preview_threads", None)
        if threads_dict:
            for idx, worker in list(threads_dict.items()):
                try:
                    if getattr(worker, "isRunning", lambda: False)():
                        worker.requestInterruption()
                        worker.quit()
                        if not worker.wait(50):
                            worker.terminate()
                            worker.wait(50)
                except Exception:
                    pass
            threads_dict.clear()
        print("[Cleanup] Worker termination complete.")

    def closeEvent(self, event):
        try:
            # A drag may have ended less than one debounce interval ago.
            # Flush it before teardown so the final overlay position is not
            # lost when the window is closed immediately.
            self._flush_pending_timeline_persist()
            # Persist the current blur state BEFORE clearing the overlay.
            # Block the blurRegionChanged signal during the clear so the
            # signal handler does not overwrite the saved state with an
            # empty regions list.
            if getattr(self, "_blur_region_signal_bound", False) and hasattr(self, "video_view"):
                try:
                    self.video_view.blurRegionChanged.disconnect(self.on_preview_blur_region_changed)
                except Exception:
                    pass
                self._blur_region_signal_bound = False
            if hasattr(self, "persist_project_blur_state"):
                try:
                    self.persist_project_blur_state()
                except Exception:
                    pass
            if hasattr(self, "persist_project_mask_state"):
                try:
                    self.persist_project_mask_state()
                except Exception:
                    pass
            # Preserve the complete project timeline on a normal application
            # close, including Text and Logo tracks. Optional layers are
            # removed only by the explicit clean/return workflow.
            if hasattr(self, "video_view"):
                self.video_view.clear_blur_region()
            if hasattr(self, "media_player") and hasattr(self.media_player, "clear_mask_region"):
                try:
                    self.media_player.clear_mask_region()
                except Exception:
                    pass
            self.save_user_settings()
            self.cleanup_temp_preview_files()
            self._terminate_workers()
        finally:
            super().closeEvent(event)

    def toggle_play(self):
        clips = self.get_timeline_video_clips() if hasattr(self, "get_timeline_video_clips") else []
        if clips:
            if self.media_player.is_playing():
                self.media_player.pause()
                self.refresh_play_button_icon()
                self.timeline.set_playing(False)
            else:
                if hasattr(self, "ensure_media_backend_ready"):
                    self.ensure_media_backend_ready()
                pos_ms = getattr(self, "_timeline_global_position_ms", int(self.timeline._playhead * 1000))
                self.seek_timeline_video(pos_ms / 1000.0)
                self.media_player.play()
                self.timeline.set_playing(True)
                self.refresh_play_button_icon()
            return
        toggle_play_impl(self)

    def stop_video(self):
        stop_video_impl(self)
        clips = self.get_timeline_video_clips() if hasattr(self, "get_timeline_video_clips") else []
        if clips:
            self.seek_timeline_video(0.0)

    def position_changed(self, position):
        if hasattr(self, "handle_sequence_position_changed"):
            try:
                if self.handle_sequence_position_changed(position):
                    return
            except Exception as exc:
                self.log(f"[Timeline Preview] sequence position error: {exc}")
        position_changed_impl(self, position)

    def duration_changed(self, duration):
        clips = self.get_timeline_video_clips() if hasattr(self, "get_timeline_video_clips") else []
        if clips:
            total_ms = int(float(clips[-1]["timeline_end"]) * 1000)
            self.timeline.set_duration(total_ms)
            self.update_duration_label(int(getattr(self, "_timeline_global_position_ms", 0)), total_ms)
            return
        duration_changed_impl(self, duration)
        self.schedule_timeline_visual_refresh(waveform=False, thumbnails=True)

    def set_position(self, position):
        clips = self.get_timeline_video_clips() if hasattr(self, "get_timeline_video_clips") else []
        if clips:
            self.seek_timeline_video(float(position) / 1000.0)
            return
        set_position_impl(self, position)
        # A seek is explicit navigation, even when playback is paused.  The
        # media backend may emit positionChanged later, so use the requested
        # timestamp immediately to keep the Inspector and Preview on the same
        # cue instead of leaving the previously selected subtitle visible.
        if hasattr(self, "_sync_selected_segment_to_playback_position"):
            self._sync_selected_segment_to_playback_position(position)

    def update_duration_label(self, current, total):
        update_duration_label_impl(self, current, total)

    def refresh_play_button_icon(self):
        """Update the play button icon + tooltip to reflect the current
        media player state (playing vs paused). Called from
        position_changed when playback ends naturally so the button
        switches from the pause icon back to the play icon."""
        if not hasattr(self, "play_btn"):
            return
        playing = False
        try:
            playing = bool(self.media_player.is_playing())
        except Exception:
            playing = False
        play_icon = "pause.svg" if playing else "play.svg"
        play_tip = "Pause preview" if playing else "Play preview"
        try:
            self.play_btn.setIcon(load_icon(asset_path("icons", play_icon), 18))
            self.play_btn.setToolTip(play_tip)
        except Exception:
            pass
        if hasattr(self, "blur_area_btn"):
            blur_active = bool(self.blur_area_btn.isChecked())
            self.blur_area_btn.setToolTip("Blur effect on" if blur_active else "Turn blur effect on or off")
        if hasattr(self, "preview_speed_combo"):
            target = float(getattr(self, "_preview_speed", 1.0))
            index = self.preview_speed_combo.findData(target)
            if index >= 0 and self.preview_speed_combo.currentIndex() != index:
                self.preview_speed_combo.blockSignals(True)
                self.preview_speed_combo.setCurrentIndex(index)
                self.preview_speed_combo.blockSignals(False)
        if hasattr(self, "preview_audio_track_combo"):
            combo = self.preview_audio_track_combo
            entries = self._preview_audio_track_choices()
            current_mode = str(getattr(self, "_preview_audio_track_mode", "both") or "both").strip().lower()
            if current_mode == "dubbed" and not any(value == "dubbed" for _label, value in entries):
                current_mode = "both"
                self._preview_audio_track_mode = "both"
            existing = [(combo.itemText(i), str(combo.itemData(i) or "")) for i in range(combo.count())]
            if existing != entries:
                combo.blockSignals(True)
                combo.clear()
                for label, value in entries:
                    combo.addItem(label, value)
                combo.blockSignals(False)
            target_index = combo.findData(current_mode)
            if target_index < 0:
                target_index = 0
            if combo.currentIndex() != target_index:
                combo.blockSignals(True)
                combo.setCurrentIndex(target_index)
                combo.blockSignals(False)
            combo.setEnabled(combo.count() > 1 and getattr(self, "media_player", None) is not None and getattr(self.media_player, "backend_name", "") == "libmpv")

    def on_preview_speed_changed(self, index: int):
        if not hasattr(self, "preview_speed_combo"):
            return
        rate = self.preview_speed_combo.itemData(index)
        try:
            new_rate = float(rate or 1.0)
        except Exception:
            new_rate = 1.0
        self._preview_speed = new_rate
        if hasattr(self, "media_player"):
            try:
                self.media_player.set_playback_rate(new_rate)
            except Exception:
                pass
