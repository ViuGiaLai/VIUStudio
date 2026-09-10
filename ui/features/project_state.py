import os

from features.voice_catalog import _default_asr_engine



class ProjectStateMixin:
    def resolve_canonical_video_path(self) -> str:
        """Return the active imported source, excluding rendered previews."""
        candidates = []
        state = getattr(self, "current_project_state", None)
        if state is not None:
            candidates.append(str(getattr(state, "input_video", "") or "").strip())
        candidates.append(str(getattr(self, "_current_video_path", "") or "").strip())
        try:
            candidates.extend(
                str(item.get("source", "") or "").strip()
                for item in self.get_timeline_video_clips(existing_only=True)
            )
        except Exception:
            pass
        editor = getattr(self, "video_path_edit", None)
        if editor is not None:
            candidates.append(str(editor.text() or "").strip())
        seen = set()
        for candidate in candidates:
            if not candidate:
                continue
            path = os.path.abspath(candidate)
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            if os.path.isfile(path):
                return path
        return ""

    def ensure_current_project(self):
        existing_state = getattr(self, "current_project_state", None)
        if existing_state is not None and os.path.isdir(str(existing_state.project_root or "")):
            state = existing_state
            state_changed = False
            # Keep the canonical project fields synchronized with the visible
            # controls. Previously a project created with Vietnamese defaults
            # could retain target_language="vi" after an English SRT import,
            # while only settings.target_lang became "en". Backend workflows
            # reopening that project could then apply Vietnamese assumptions
            # to English subtitles and voices.
            canonical_values = {
                "input_language": self.get_source_language_code(),
                "target_language": self.get_target_language_code(),
                "mode": self.get_output_mode_key(),
                "translator_ai": self.is_ai_polish_enabled(),
            }
            for field_name, field_value in canonical_values.items():
                if getattr(state, field_name, None) != field_value:
                    setattr(state, field_name, field_value)
                    state_changed = True
            audio_handling_mode = self.get_audio_handling_mode()
            if str(state.settings.get("audio_handling_mode", "fast")).strip().lower() != audio_handling_mode:
                state.set_setting("audio_handling_mode", audio_handling_mode)
                state_changed = True
            if state_changed:
                self.project_service.save_project(state)
            return state
        # Project identity must follow the imported source, not whichever
        # derived preview (Auto Recap, styled preview, filtered preview) is
        # currently loaded in the media player.  Using video_path_edit alone
        # allowed a preview path to redirect subsequent subtitle/voice saves
        # into another project's folder.
        video_path = self.resolve_canonical_video_path()
        if video_path:
            video_path = os.path.abspath(video_path)
        state = self.project_bridge.ensure_project(
            video_path=video_path,
            mode=self.get_output_mode_key(),
            translator_ai=self.is_ai_polish_enabled(),
            input_language=self.get_source_language_code(),
            target_language=self.get_target_language_code(),
        )
        if not state:
            return None
        audio_handling_mode = self.get_audio_handling_mode()
        if str(state.settings.get("audio_handling_mode", "fast")).strip().lower() != audio_handling_mode:
            state.set_setting("audio_handling_mode", audio_handling_mode)
            self.project_service.save_project(state)
        self.current_project_state = state
        self.processed_artifacts.update(state.artifacts)
        return state

    def rename_current_project(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox

        state = getattr(self, "current_project_state", None)
        if state is None:
            QMessageBox.information(self, "Rename Project", "Open or create a project first.")
            return
        current_name = str(getattr(state, "display_name", "") or state.project_id)
        name, accepted = QInputDialog.getText(self, "Rename Project", "Project name:", text=current_name)
        if not accepted:
            return
        try:
            self.project_service.rename_project(state, name)
        except ValueError as exc:
            QMessageBox.warning(self, "Rename Project", str(exc))
            return
        self.update_project_header()
        try:
            from views.launcher import LauncherWindow
            LauncherWindow.add_recent(None, {
                "project_state_path": self.project_service.project_file(state.project_root),
                "video_path": state.input_video,
            })
        except Exception:
            pass
        self.log(f"[Project] Renamed to {state.display_name}")

    def update_project_step(self, step_name: str, status: str):
        state = self.ensure_current_project()
        if not state:
            return
        self.project_bridge.update_step(state, step_name, status)

    def update_project_artifact(self, artifact_name: str, path: str):
        state = self.ensure_current_project()
        if not state or not path:
            return
        normalized_path = self._normalize_local_file_path(path)
        self.processed_artifacts[artifact_name] = normalized_path
        self.project_bridge.update_artifact(state, artifact_name, normalized_path)

    def _dict_segments_to_models(self, segments, *, translated=False):
        return self.project_bridge.dict_segments_to_models(segments, translated=translated)

    def _sync_segment_models_from_current_segments(self):
        self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
        self.current_translated_segment_models = self._dict_segments_to_models(
            self.current_translated_segments,
            translated=True,
        )

    def persist_transcription_project_data(self, raw_segments, srt_path=""):
        state = self.ensure_current_project()
        if not state:
            return
        self.current_segment_models = self.project_bridge.persist_transcription(state, raw_segments, srt_path)

    def persist_translation_project_data(self, translated_segments, srt_path=""):
        state = self.ensure_current_project()
        if not state:
            return
        self.current_translated_segment_models = self.project_bridge.persist_translation(
            state,
            self.current_segment_models,
            translated_segments,
            srt_path,
        )
        signature = self.build_current_translation_signature()
        if signature:
            state.set_setting("translation_signature", signature)
            self.project_service.save_project(state)

    def persist_auto_recap_project_data(self, decisions, recap_video_path=""):
        state = self.ensure_current_project()
        if not state:
            return
        edl_data = [d.to_dict() if hasattr(d, "to_dict") else dict(d.__dict__) for d in decisions]
        state.set_setting("auto_recap_edl", edl_data)
        if recap_video_path:
            state.artifacts["auto_recap_video"] = self._normalize_local_file_path(recap_video_path)
        self.project_service.save_project(state)

    def build_current_translation_signature(self, source_segments=None):
        base_segments = list(source_segments or self.current_segments or [])
        if not base_segments:
            transcript_text = self.transcript_text.toPlainText().strip() if hasattr(self, "transcript_text") else ""
            if transcript_text:
                base_segments = self.parse_srt_to_segments(transcript_text)
        if not base_segments:
            return ""
        return self.project_service.build_translation_signature(
            base_segments,
            src_lang=self.get_source_language_code(),
            target_lang=self.get_target_language_code(),
            enable_polish=self.is_ai_polish_enabled(),
            optimize_subtitles=False,
            style_instruction=self.get_ai_style_instruction(),
        )

    def build_current_voice_signature(self, segments=None, background_path=""):
        voice_segments = list(segments or [])
        if not voice_segments:
            voice_segments = self._get_voiceover_segments()
        if not voice_segments:
            return ""
        return self.project_service.build_voice_signature(
            voice_segments,
            audio_handling_mode=self.get_audio_handling_mode(),
            voice_name=self.get_active_voice_name(),
            voice_speed=self._parse_voice_speed_value(),
            timing_sync_mode=str(self.voice_timing_sync_combo.currentText()).strip(),
            background_path=background_path,
            original_volume=int(self.audio_a1_volume_slider.value()) if hasattr(self, "audio_a1_volume_slider") else 50,
            dub_volume=int(self.audio_a2_volume_slider.value()) if hasattr(self, "audio_a2_volume_slider") else 100,
        )

    def persist_current_timeline_project_data(self):
        state = self.ensure_current_project()
        if not state:
            return
        if self.current_segments:
            self.current_segment_models = self.project_bridge.persist_transcription(
                state,
                self.current_segments,
                self.last_original_srt_path,
            )
        if self.current_translated_segments:
            self.current_translated_segment_models = self.project_bridge.persist_translation(
                state,
                self.current_segment_models,
                self.current_translated_segments,
                self.last_translated_srt_path,
            )
            signature = self.build_current_translation_signature()
            if signature:
                state.set_setting("translation_signature", signature)
        if self.current_project_state:
            has_generated_voice = (
                not bool(getattr(self, "_voice_track_partial", False))
                and bool(
                    getattr(self, "last_voice_vi_path", "")
                    or getattr(self, "last_mixed_vi_path", "")
                    or self.processed_artifacts.get("voice_vi")
                    or self.processed_artifacts.get("mixed_vi")
                )
            )
            # Saving edits must not certify old samples against new text or
            # timing. Only the successful TTS completion writes this signature.
            if not has_generated_voice:
                state.settings.pop("voice_signature", None)

        # Collect and save all current project settings
        proj_settings = {
            "output_mode": self.output_mode_combo.currentText() if hasattr(self, "output_mode_combo") else "",
            "output_quality": self.output_quality_combo.currentText() if hasattr(self, "output_quality_combo") else "",
            "output_preset": self.output_preset_combo.currentData() if hasattr(self, "output_preset_combo") else "balanced",
            "output_bitrate_kbps": int(self.output_bitrate_spin.value()) if hasattr(self, "output_bitrate_spin") else 2000,
            "output_fps": self.output_fps_combo.currentText() if hasattr(self, "output_fps_combo") else "",
            "output_ratio": self.output_ratio_combo.currentText() if hasattr(self, "output_ratio_combo") else "",
            "output_scale_mode": self.output_scale_mode_combo.currentText() if hasattr(self, "output_scale_mode_combo") else "",
            "audio_handling_mode": self.get_audio_handling_mode() if hasattr(self, "get_audio_handling_mode") else "",
            "source_lang": self.lang_whisper_combo.currentText() if hasattr(self, "lang_whisper_combo") else "",
            "target_lang": (self.lang_target_combo.currentData() or self.lang_target_combo.currentText()) if hasattr(self, "lang_target_combo") else "",
            "translation_engine": (self.translation_engine_combo.currentData() or self.translation_engine_combo.currentText()) if hasattr(self, "translation_engine_combo") else "",
            "llama_app_model": str(self.llama_model_combo.currentData() or "") if hasattr(self, "llama_model_combo") else "",
            "translation_style_preset": (self.translation_style_preset_combo.currentData() or self.translation_style_preset_combo.currentText()) if hasattr(self, "translation_style_preset_combo") else "",
            "voice_engine": (self.voice_engine_combo.currentData() or self.voice_engine_combo.currentText()) if hasattr(self, "voice_engine_combo") else "",
            "free_voice_name": self.free_voice_combo.currentText() if hasattr(self, "free_voice_combo") else "",
            "voice_gender": self.voice_gender_combo.currentText() if hasattr(self, "voice_gender_combo") else "",
            "voice_speed": self.voice_speed_spin.currentText() if hasattr(self, "voice_speed_spin") else "",
            "voice_timing_sync_mode": self.voice_timing_sync_combo.currentText() if hasattr(self, "voice_timing_sync_combo") else "",
            "speaker_diarization": self.speaker_diarization_cb.isChecked() if hasattr(self, "speaker_diarization_cb") else False,
            "speaker_diarization_num_speakers": self.speaker_diarization_speakers_combo.currentData() if hasattr(self, "speaker_diarization_speakers_combo") else -1,
            "ai_dubbing_rewrite": self.ai_dubbing_rewrite_cb.isChecked() if hasattr(self, "ai_dubbing_rewrite_cb") else False,
            "preview_track_visibility": {
                "TS1": bool(getattr(self, "_subtitle_track_preview_visible", True)),
                "T1 Text": bool(getattr(self, "_text_track_preview_visible", True)),
                "L1 Logo": bool(getattr(self, "_logo_track_preview_visible", True)),
                "M1": bool(getattr(self, "_mask_track_preview_visible", True)),
                "B1": bool(self._blur_effect_enabled()),
            },
            "subtitle_style_controls": self._current_subtitle_style_controls_state(),
            "video_filter_state": self.get_video_filter_state() if hasattr(self, "get_video_filter_state") else {},
        }
        for k, v in proj_settings.items():
            state.set_setting(k, v)

        # Save timeline data (includes mask and logo layers)
        if hasattr(self, "timeline") and self.timeline._timeline:
            timeline_data = self.timeline._timeline.to_dict()
            # Save timeline to a file in the project directory
            timeline_path = os.path.join(state.project_root, "timeline", "timeline.json")
            os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
            # Timeline edits are frequent and a process interruption must not
            # leave a truncated JSON file that prevents the project reopening.
            self.project_service._atomic_write_json(timeline_path, timeline_data)
            state.set_artifact("timeline", timeline_path)
            # Selection Range is an ephemeral editing aid. Never restore it
            # when reopening a project, where an old range can be confusing.
            state.settings.pop("timeline_selection_range", None)

        self.project_service.save_project(state)

    def schedule_timeline_project_persist(self, *, mask_state=False, blur_state=False):
        """Coalesce persistence requested by high-frequency editor events.

        Preview geometry is updated by the callers immediately.  Only the
        disk-backed project/timeline write is delayed, which prevents drag
        operations and text typing from blocking the Qt event loop.
        """
        self._pending_timeline_persist = True
        self._pending_mask_state_persist = self._pending_mask_state_persist or bool(mask_state)
        self._pending_blur_state_persist = self._pending_blur_state_persist or bool(blur_state)
        timer = getattr(self, "_timeline_persist_timer", None)
        if timer is not None:
            timer.start()
        else:
            self._flush_pending_timeline_persist()

    def _flush_pending_timeline_persist(self):
        """Write coalesced editor changes once after an edit burst ends."""
        if not getattr(self, "_pending_timeline_persist", False):
            return
        save_mask = self._pending_mask_state_persist
        save_blur = self._pending_blur_state_persist
        self._pending_timeline_persist = False
        self._pending_mask_state_persist = False
        self._pending_blur_state_persist = False
        try:
            if save_mask:
                self.persist_project_mask_state()
            if save_blur:
                self.persist_project_blur_state()
            self.persist_current_timeline_project_data()
        except Exception:
            # Preserve existing best-effort persistence behavior: a save
            # failure must not interrupt editing or leave the timer running.
            pass

    def _cache_core_timeline_tracks_only(self):
        """Keep only V1, A1, and TS1 when a video session is closed.

        Optional editing tracks remain fully usable (and exportable) during
        the active session. They are deliberately not retained in the
        reopen cache, preventing Blur/Logo/Mask/Text tracks from following
        a video into its next editing session.
        """
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        core_track_names = {"V1 Video", "A1 Audio", "TS1"}
        timeline = self.timeline._timeline
        removed = [track for track in timeline.tracks if track.name not in core_track_names]
        if removed:
            timeline.tracks = [track for track in timeline.tracks if track.name in core_track_names]
            for track in removed:
                self.timeline._track_heights.pop(track.id, None)
            selected_id = str(getattr(self.timeline, "_selected_layer_id", "") or "")
            retained_ids = {layer.id for track in timeline.tracks for layer in track.layers}
            if selected_id not in retained_ids:
                self.timeline._selected_layer_id = ""
            self.timeline._redraw()
            self.persist_current_timeline_project_data()
        state = getattr(self, "current_project_state", None)
        if state is not None:
            # Blur and mask also have legacy settings fallbacks. Clear those
            # cache entries so they cannot recreate optional tracks on load.
            state.set_setting("blur_state", {"enabled": False, "regions": []})
            state.set_setting("mask_state", {"enabled": False, "regions": []})
            self.project_service.save_project(state)
        if removed:
            self.log(f"[Timeline Cache] Retained core tracks only; discarded {len(removed)} optional track(s).")

    def _restore_saved_timeline_model(self, state) -> bool:
        """Restore the complete editor timeline, including optional layers.

        The project bridge restores transcript artifacts, but those artifacts
        only describe the core subtitle data.  Text/Logo/Blur/Mask tracks are
        persisted separately in ``timeline/timeline.json`` and must be loaded
        before the subtitle sync rebuilds TS1; otherwise reopening a project
        silently drops the optional tracks from the in-memory model.
        """
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            return False
        artifacts = getattr(state, "artifacts", {}) or {}
        timeline_path = str(artifacts.get("timeline", "") or "").strip()
        if not timeline_path:
            timeline_path = os.path.join(state.project_root, "timeline", "timeline.json")
        timeline_path = self._normalize_local_file_path(timeline_path)
        if not timeline_path or not os.path.isfile(timeline_path):
            return False
        try:
            import json
            from app.layers.timeline import Timeline

            with open(timeline_path, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            loaded = Timeline.from_dict(saved)
            if not loaded.tracks:
                return False

            from app.services.timeline_video_sequence import ordered_video_layers, timeline_video_clips

            loaded_clips = timeline_video_clips(loaded)
            loaded_sources = [os.path.normcase(os.path.abspath(clip.source)) for clip in loaded_clips]
            canonical_source = os.path.normcase(os.path.abspath(str(state.input_video or "")))
            recap_source = os.path.normcase(os.path.abspath(str(artifacts.get("auto_recap_video", "") or "")))
            allowed_first_sources = {source for source in (canonical_source, recap_source) if source}

            # A restored V1 whose first clip belongs to another imported
            # video is evidence of the old project-switch leak. Never let it
            # replace the selected project's source in the editor.
            if loaded_sources and loaded_sources[0] not in allowed_first_sources:
                self._project_media_source_mismatch = True
                self.log(
                    "[Project Recovery] Saved Timeline belongs to another source; "
                    "starting this project from its own imported video."
                )
                reset_timeline = getattr(timeline, "_init_default_tracks", None)
                if callable(reset_timeline):
                    reset_timeline()
                return False

            lineage = list(getattr(state, "settings", {}).get("timeline_video_clips") or [])
            lineage_sources = [
                os.path.normcase(os.path.abspath(str(item.get("source", "") or "")))
                for item in lineage if isinstance(item, dict) and item.get("source")
            ]
            # The prepare pipeline records the exact source order used to
            # produce transcript/translation/voice artifacts. If the saved
            # editor Timeline now points at a different video set, those
            # artifacts must not be shown over the new source.
            if (
                lineage_sources
                and loaded_sources != lineage_sources
                and (not loaded_sources or loaded_sources[0] != recap_source)
            ):
                self._project_media_source_mismatch = True

            timeline._timeline = loaded
            # Track visibility toggles are an editor-view concern, not part
            # of the serialized project model.  Do not let hidden IDs from a
            # previous project affect the restored tracks.
            timeline._timeline_hidden_track_ids.clear()
            # The source/video duration is refreshed later by set_video_source;
            # retain the saved duration until then so optional layer geometry
            # can be drawn immediately during project restoration.
            timeline._duration = max(
                float(getattr(timeline, "_duration", 0.0) or 0.0),
                float(getattr(loaded, "duration", 0.0) or 0.0),
            )
            timeline._track_heights = {
                str(track.id): int(getattr(track, "height", timeline.TRACK_DEFAULT_H))
                for track in loaded.tracks
            }
            timeline._segment_indices.clear()
            timeline._overlap_layout_cache.clear()
            timeline._overlap_row_assignments.clear()
            timeline._redraw()
            # Restore the canonical source from the saved V1 order.  The
            # editor field may still contain a rendered preview from the
            # previous session; using it would attach this project's next
            # artifacts to the wrong video.
            restored_layers = ordered_video_layers(loaded)
            if restored_layers:
                restored_source = os.path.abspath(str(restored_layers[0].source or ""))
                if restored_source and os.path.isfile(restored_source):
                    state.input_video = restored_source
                    self._current_video_path = restored_source
                    if hasattr(self, "video_path_edit"):
                        self.video_path_edit.setText(restored_source)
                    if hasattr(self, "project_service"):
                        state.set_setting(
                            "input_video_identity",
                            self.project_service._input_video_identity(restored_source),
                        )
            state.set_setting("timeline_video_clips", [clip.to_dict() for clip in loaded_clips])
            try:
                self.project_service.save_project(state)
            except Exception:
                pass
            self.log(
                f"[Timeline] Restored {len(loaded.tracks)} saved track(s) "
                f"from {timeline_path}"
            )
            return True
        except Exception as exc:
            self.log(f"[Timeline] Could not restore saved timeline: {exc}")
            return False

    def _detach_mismatched_media_artifacts(self, state) -> None:
        """Preserve stale files for recovery but remove them from active UI."""
        import time

        media_keys = {
            "extracted_audio", "audio_extracted", "asr_audio_profile", "asr_ocr_reference",
            "transcript_raw", "transcript_segments", "transcript_chunk_raw",
            "transcript_merged", "transcript_regrouped", "transcription_chunks",
            "subtitle_original_srt", "srt_original", "subtitle_translated_srt", "srt_translated",
            "translation_raw", "translation_refined", "translation_final",
            "voice_vi", "voice_segments", "mixed_vi", "vocals", "music",
            "auto_recap_video",
        }
        detached = {key: value for key, value in state.artifacts.items() if key in media_keys}
        if not detached:
            return
        recovery_dir = os.path.join(state.project_root, "recovery")
        os.makedirs(recovery_dir, exist_ok=True)
        recovery_path = os.path.join(recovery_dir, f"mismatched_media_{int(time.time())}.json")
        payload = {
            "reason": "Saved media artifacts were generated from a different V1 source sequence.",
            "input_video": state.input_video,
            "timeline_video_clips": list(state.settings.get("timeline_video_clips") or []),
            "artifacts": detached,
        }
        self.project_service._atomic_write_json(recovery_path, payload)
        for key in detached:
            state.artifacts.pop(key, None)
        state.artifacts["detached_media_recovery"] = recovery_path
        for key in (
            "timeline_video_clips", "timeline_video_signature", "extraction_signature",
            "transcription_signature", "translation_signature", "voice_signature",
            "asr_audio_normalization", "auto_recap_edl", "input_video_content_changed",
        ):
            state.settings.pop(key, None)
        for step in (
            "extract_audio", "transcribe", "translate_raw", "refine_translation",
            "generate_tts", "build_subtitle", "mix_audio", "export",
        ):
            state.steps[step] = "pending"
        self.project_service.save_project(state)
        self.log(
            "[Project Recovery] Detached subtitles/voice generated for another video. "
            f"Original files were preserved at {recovery_path}"
        )

    def load_project_context(self, state):
        if not state:
            return
        self._allow_post_pipeline_preview_assets = False
        self._project_media_source_mismatch = False

        st = getattr(state, "settings", {}) or {}

        if st.get("input_video_content_changed"):
            self._project_media_source_mismatch = True

        lineage = list(st.get("timeline_video_clips") or [])
        lineage_sources = [
            os.path.normcase(os.path.abspath(str(item.get("source", "") or "")))
            for item in lineage if isinstance(item, dict) and item.get("source")
        ]
        canonical_source = os.path.normcase(os.path.abspath(str(state.input_video or "")))
        recap_source_for_lineage = os.path.normcase(os.path.abspath(str(
            getattr(state, "artifacts", {}).get("auto_recap_video", "") or ""
        )))
        if (
            lineage_sources
            and lineage_sources[0] not in {canonical_source, recap_source_for_lineage}
        ):
            self._project_media_source_mismatch = True

        # Restore Auto Recap state early so export and the Generate menu do not
        # silently lose the previous EDL when a project is reopened.
        try:
            from app.services.auto_recap_engine import ShotDecision

            restored_edl = []
            for item in list(st.get("auto_recap_edl") or []):
                if not isinstance(item, dict):
                    continue
                values = dict(item)
                values.pop("output_duration", None)
                restored_edl.append(ShotDecision(**values))
            self.current_auto_recap_edl = restored_edl
        except (TypeError, ValueError):
            self.current_auto_recap_edl = []

        recap_artifact = str(getattr(state, "artifacts", {}).get("auto_recap_video", "") or "")
        recap_artifact = self._normalize_local_file_path(recap_artifact)
        self.last_recap_video_path = recap_artifact if recap_artifact and os.path.exists(recap_artifact) else ""

        # 1. Output & Media Settings
        saved_output_mode = st.get("output_mode")
        if saved_output_mode and hasattr(self, "output_mode_combo"):
            idx = self.output_mode_combo.findText(saved_output_mode)
            if idx >= 0:
                self.output_mode_combo.setCurrentIndex(idx)

        saved_q = st.get("output_quality")
        if saved_q and hasattr(self, "output_quality_combo"):
            idx = self.output_quality_combo.findText(saved_q)
            if idx >= 0:
                self.output_quality_combo.setCurrentIndex(idx)
        if hasattr(self, "output_preset_combo"):
            saved_preset = st.get("output_preset")
            if saved_preset:
                idx = self.output_preset_combo.findData(saved_preset)
                if idx >= 0:
                    self.output_preset_combo.setCurrentIndex(idx)
        if hasattr(self, "output_bitrate_spin") and st.get("output_bitrate_kbps"):
            try:
                self.output_bitrate_spin.setValue(int(st.get("output_bitrate_kbps")))
            except (TypeError, ValueError):
                pass

        saved_fps = st.get("output_fps")
        if saved_fps and hasattr(self, "output_fps_combo"):
            idx = self.output_fps_combo.findText(saved_fps)
            if idx >= 0:
                self.output_fps_combo.setCurrentIndex(idx)

        saved_ratio = st.get("output_ratio")
        if saved_ratio and hasattr(self, "output_ratio_combo"):
            idx = self.output_ratio_combo.findText(saved_ratio)
            if idx >= 0:
                self.output_ratio_combo.setCurrentIndex(idx)

        saved_scale = st.get("output_scale_mode")
        if saved_scale and hasattr(self, "output_scale_mode_combo"):
            idx = self.output_scale_mode_combo.findText(saved_scale)
            if idx >= 0:
                self.output_scale_mode_combo.setCurrentIndex(idx)

        # 2. Audio Settings
        audio_handling_mode = str(st.get("audio_handling_mode", "") or "").strip().lower()
        if audio_handling_mode and hasattr(self, "audio_handling_combo"):
            combo_index = self.audio_handling_combo.findData(audio_handling_mode)
            if combo_index < 0:
                combo_index = self.audio_handling_combo.findText(audio_handling_mode)
            if combo_index >= 0:
                self.audio_handling_combo.setCurrentIndex(combo_index)

        # 3. Language & Translation Engine
        project_engine = str(st.get("transcription_engine", "") or "").strip().lower()
        os.environ["TRANSCRIPTION_ENGINE"] = project_engine if project_engine in {"whisper", "sensevoice", "ocr"} else _default_asr_engine()

        saved_src = st.get("source_lang")
        if saved_src and hasattr(self, "lang_whisper_combo"):
            idx = self.lang_whisper_combo.findText(saved_src)
            if idx < 0:
                idx = self.lang_whisper_combo.findData(saved_src)
            if idx >= 0:
                self.lang_whisper_combo.setCurrentIndex(idx)

        saved_tgt = st.get("target_lang")
        if saved_tgt and hasattr(self, "lang_target_combo"):
            idx = self.lang_target_combo.findData(saved_tgt)
            if idx < 0:
                idx = self.lang_target_combo.findText(saved_tgt)
            if idx >= 0:
                self.lang_target_combo.setCurrentIndex(idx)

        saved_llama_model = str(st.get("llama_app_model", "") or "").strip()
        if saved_llama_model:
            os.environ["LLAMA_APP_MODEL"] = saved_llama_model
            if hasattr(self, "settings"):
                self.settings.setValue("llama_app_model", saved_llama_model)
        saved_tengine = st.get("translation_engine")
        if saved_tengine and hasattr(self, "translation_engine_combo"):
            idx = self.translation_engine_combo.findData(saved_tengine)
            if idx < 0:
                idx = self.translation_engine_combo.findText(saved_tengine)
            if idx >= 0:
                self.translation_engine_combo.setCurrentIndex(idx)

        saved_tstyle = st.get("translation_style_preset")
        if saved_tstyle and hasattr(self, "translation_style_preset_combo"):
            idx = self.translation_style_preset_combo.findData(saved_tstyle)
            if idx < 0:
                idx = self.translation_style_preset_combo.findText(saved_tstyle)
            if idx >= 0:
                self.translation_style_preset_combo.setCurrentIndex(idx)

        # 4. Voice Settings
        saved_vengine = st.get("voice_engine")
        if saved_vengine and hasattr(self, "voice_engine_combo"):
            idx = self.voice_engine_combo.findData(saved_vengine)
            if idx < 0:
                idx = self.voice_engine_combo.findText(saved_vengine)
            if idx >= 0:
                self.voice_engine_combo.setCurrentIndex(idx)

        saved_voice = st.get("free_voice_name") or st.get("voice_name")
        if saved_voice and hasattr(self, "free_voice_combo"):
            idx = self.free_voice_combo.findText(saved_voice)
            if idx >= 0:
                self.free_voice_combo.setCurrentIndex(idx)

        saved_gender = st.get("voice_gender")
        if saved_gender and hasattr(self, "voice_gender_combo"):
            idx = self.voice_gender_combo.findText(saved_gender)
            if idx >= 0:
                self.voice_gender_combo.setCurrentIndex(idx)

        saved_speed = st.get("voice_speed")
        if saved_speed and hasattr(self, "voice_speed_spin"):
            self.voice_speed_spin.setCurrentText(str(saved_speed))

        saved_sync = st.get("voice_timing_sync_mode")
        if saved_sync and hasattr(self, "voice_timing_sync_combo"):
            idx = self.voice_timing_sync_combo.findText(saved_sync)
            if idx >= 0:
                self.voice_timing_sync_combo.setCurrentIndex(idx)
            if hasattr(self, "timeline") and self.timeline is not None:
                self.timeline.set_voice_sync_mode(saved_sync)

        # 4b. Video Filter Settings
        saved_vfilter = st.get("video_filter_state")
        if saved_vfilter and isinstance(saved_vfilter, dict) and hasattr(self, "video_filter_controller"):
            try:
                self.video_filter_controller.set_video_filter_state(
                    saved_vfilter.get("preset", "original"),
                    saved_vfilter.get("intensity", 75),
                    saved_vfilter.get("overrides") or saved_vfilter.get("final"),
                    saved_vfilter.get("modified"),
                )
            except Exception:
                pass

        # 5. Advanced Settings
        if "speaker_diarization" in st and hasattr(self, "speaker_diarization_cb"):
            self.speaker_diarization_cb.setChecked(bool(st.get("speaker_diarization")))
            if hasattr(self, "update_speaker_diarization_availability"):
                self.update_speaker_diarization_availability()

        saved_spk = st.get("speaker_diarization_num_speakers")
        if saved_spk is not None and hasattr(self, "speaker_diarization_speakers_combo"):
            try:
                idx = self.speaker_diarization_speakers_combo.findData(int(saved_spk))
                if idx >= 0:
                    self.speaker_diarization_speakers_combo.setCurrentIndex(idx)
            except Exception:
                pass

        if "ai_dubbing_rewrite" in st and hasattr(self, "ai_dubbing_rewrite_cb"):
            self.ai_dubbing_rewrite_cb.setChecked(bool(st.get("ai_dubbing_rewrite")))

        context = self.project_bridge.load_context(state)
        repaired_legacy_voice_timing = bool(context.get("repaired_voice_timing"))
        self._voice_track_partial = bool(
            getattr(state, "settings", {}).get("voice_track_partial", False)
        )
        self.processed_artifacts = {}
        # Restore project-scoped visibility. Old projects remain visible by
        # default because they have no saved value yet.
        preview_visibility = dict(getattr(state, "settings", {}).get("preview_track_visibility") or {})
        self._subtitle_track_preview_visible = bool(preview_visibility.get("TS1", True))
        self._text_track_preview_visible = bool(preview_visibility.get("T1 Text", True))
        self._logo_track_preview_visible = bool(preview_visibility.get("L1 Logo", True))
        self._mask_track_preview_visible = bool(preview_visibility.get("M1", True))
        saved_subtitle_style = dict(getattr(state, "settings", {}).get("subtitle_style_controls") or {})
        if saved_subtitle_style:
            self._apply_subtitle_style_controls_state(saved_subtitle_style)
            self._subtitle_custom_style_state = dict(saved_subtitle_style)
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_subtitle_track_visible"):
            self.video_view.set_subtitle_track_visible(self._subtitle_track_preview_visible)
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_track_visible"):
            self.video_view.set_logo_track_visible(self._logo_track_preview_visible)
        self.last_original_srt_path = ""
        self.last_translated_srt_path = ""
        self.last_extracted_audio = ""
        self.last_vocals_path = ""
        # Sync timeline track mute -> GUI per-track mute state
        self._sync_timeline_mute_to_gui()
        self.last_music_path = ""
        self.last_voice_vi_path = ""
        self.last_mixed_vi_path = ""
        self.current_segment_models = []
        self.current_translated_segment_models = []
        self.current_segments = []
        self.current_translated_segments = []
        if hasattr(self, "audio_source_edit"):
            self.audio_source_edit.clear()
        if hasattr(self, "transcript_text"):
            self.transcript_text.clear()
        if hasattr(self, "translated_text"):
            self.translated_text.clear()
        self._saved_timeline_model_restored = False
        if hasattr(self, "timeline"):
            self.timeline.set_segments([])
            self.timeline.set_video_thumbnails([])
            self.timeline.set_playing(False)
            # Restore optional tracks before apply_segments_to_timeline().
            # That method refreshes TS1, while preserving the restored Text,
            # Logo, Blur, and Mask tracks.
            self._saved_timeline_model_restored = bool(
                self._restore_saved_timeline_model(state)
            )
        if self._project_media_source_mismatch:
            self._detach_mismatched_media_artifacts(state)
            context = self.project_bridge.load_context(state)
            self.last_recap_video_path = ""
            self.current_auto_recap_edl = []
        self._timeline_video_thumb_cache_key = None
        self._timeline_video_thumbnails = []
        self.processed_artifacts.update(context["artifacts"])
        self.last_original_srt_path = self._normalize_local_file_path(context["last_original_srt_path"] or self.last_original_srt_path)
        self.last_translated_srt_path = self._normalize_local_file_path(context["last_translated_srt_path"] or self.last_translated_srt_path)
        self.last_extracted_audio = self._normalize_local_file_path(context["last_extracted_audio"] or self.last_extracted_audio)
        self.last_vocals_path = self._normalize_local_file_path(context["last_vocals_path"] or self.last_vocals_path)
        self.last_music_path = self._normalize_local_file_path(context["last_music_path"] or self.last_music_path)
        self.last_voice_vi_path = self._normalize_local_file_path(context["last_voice_vi_path"] or self.last_voice_vi_path)
        self.last_mixed_vi_path = self._normalize_local_file_path(context["last_mixed_vi_path"] or self.last_mixed_vi_path)
        self.current_segment_models = context["current_segment_models"]
        self.current_translated_segment_models = context["current_translated_segment_models"]
        self.current_segments = context["current_segments"]
        self.current_translated_segments = context["current_translated_segments"]
        self.refresh_detected_speakers_section()
        if self.current_translated_segments:
            self.refresh_auto_keyword_highlights(force=True)
        if self.get_audio_handling_mode() == "clean" and self.last_vocals_path and os.path.exists(self.last_vocals_path):
            self.audio_source_edit.setText(self.last_vocals_path)
        elif self.last_extracted_audio and os.path.exists(self.last_extracted_audio):
            self.audio_source_edit.setText(self.last_extracted_audio)
        elif self.last_vocals_path and os.path.exists(self.last_vocals_path):
            self.audio_source_edit.setText(self.last_vocals_path)
        if self.current_segments:
            self.transcript_text.setText(self.format_to_srt(self.current_segments))
        if self.current_translated_segments:
            self.translated_text.setText(self.format_to_srt(self.current_translated_segments))
        if self.current_translated_segments or self.current_segments:
            if bool(getattr(self, "subtitle_single_line_cb", None) and self.subtitle_single_line_cb.isChecked()):
                self._split_segments_for_single_line()
            self._enable_post_pipeline_preview_assets(refresh=True)
            self.apply_segments_to_timeline()
            if repaired_legacy_voice_timing:
                # The bridge restored the source cue timing from a legacy
                # artifact.  Treat it like any subtitle timing repair so the
                # old dub is invalidated and the translated SRT is rewritten.
                self._subtitle_timing_was_normalized = True
            if bool(getattr(self, "_subtitle_timing_was_normalized", False)):
                # Old project artifacts can contain duplicate/overlapping
                # cues written by earlier versions. Persist the repaired
                # sequence only after discarding its now-invalid dub. This
                # order matters: otherwise timeline.json would immediately
                # save stale audio_path values back into the TS1 layers.
                self._invalidate_dubbed_output_after_subtitle_edit()
                self.persist_current_timeline_project_data()
                self._regenerate_translated_srt_from_segments()
            # Loading/rebuilding a project starts at the playhead, not at the
            # first subtitle. Selecting cue 1 here made the Inspector and the
            # paused overlay show a future cue while timeline time was 00:00.
            self._selected_segment_index = -1
            self.sync_segment_editor_rows()
        # Restore A2 Dub track if TTS was generated
        voice_path = str(getattr(self, "last_voice_vi_path", "") or "")
        if voice_path and os.path.exists(voice_path) and hasattr(self, "timeline"):
            self.timeline.sync_tts_track(voice_path, segments=self.current_translated_segments or self.current_segments)
            # Enable Audio tab since voice generation was completed
            if hasattr(self, "audio_tab_btn"):
                self.audio_tab_btn.setEnabled(True)
        self._sync_timeline_mute_to_gui()
        if hasattr(self, "_sync_timeline_audio_volumes_to_gui"):
            self._sync_timeline_audio_volumes_to_gui()
        # OCR geometry is project-scoped.  For a reopened OCR project that has
        # not produced a transcript yet, keep the crop editor visible so the
        # user can configure the region before running Transcript.  Completed
        # projects return to an unobstructed preview until OCR is explicitly
        # reopened with the toolbar button.
        has_transcript = bool(
            self.current_segments
            or self.current_segment_models
            or (hasattr(self, "transcript_text") and self.transcript_text.toPlainText().strip())
        )
        if not bool(getattr(self, "_alternate_ocr_range_pending", None)):
            self._ocr_overlay_visible = project_engine == "ocr" and not has_transcript
        self._update_ocr_overlay()
        # Clear any stale layer selection from the previous project so
        # the inspector does not stay pinned to a track that no longer
        # exists (e.g. a BlurLayer from a previous project that was
        # removed by _restore_project_blur_state).
        if hasattr(self, "timeline"):
            try:
                self.timeline.select_layer("")
            except Exception:
                pass
        self._show_default_inspector()
        self._restore_project_blur_state(state)
        if hasattr(self, "_restore_project_mask_state"):
            try:
                self._restore_project_mask_state(state)
            except Exception:
                pass
        # Always start a reopened project focused on the source video layer,
        # never on an optional overlay that happened to be restored first.
        try:
            video_layer = None
            for track in self.timeline._timeline.tracks:
                if str(getattr(track, "name", "")) == "V1 Video" and track.layers:
                    video_layer = track.layers[0]
                    break
            if video_layer is not None:
                self.timeline.select_layer(video_layer.id)
                self.on_timeline_layer_selected(video_layer.id)
        except Exception:
            pass
        # Reconnect optional timeline layers to their preview overlays after
        # restoring the serialized model.  Timeline restoration alone is not
        # enough because these overlays are maintained by the video view.
        try:
            self._refresh_text_layer_preview(getattr(self.timeline, "_selected_layer_id", ""))
        except Exception:
            pass
        try:
            logo_track = next(
                (
                    track for track in self.timeline._timeline.tracks
                    if str(getattr(track, "name", "")) == "L1 Logo"
                    and getattr(track, "layers", None)
                ),
                None,
            )
            if logo_track is not None:
                logo_layer = next(
                    (candidate for candidate in logo_track.layers
                     if self._layer_is_active_at_preview_time(candidate)),
                    logo_track.layers[0],
                )
                self._show_logo_overlay(logo_track, logo_layer)
        except Exception:
            pass
        # Force the dual-track sidecar player to re-initialize for this
        # project. Without this, reopening a project would leave the
        # original/dubbed QMediaPlayer sidecars pointing at the previous
        # project's audio files (or empty), so the user hears nothing
        # until they press Generate.
        try:
            if hasattr(self, "sync_preview_audio_track_to_output"):
                self.sync_preview_audio_track_to_output(apply_to_player=True, force=True)
        except Exception:
            pass
        # Stop any active playback so the user re-presses Play after
        # reopening. Otherwise mpv / QMediaPlayer may keep playing the
        # previous source.
        try:
            if hasattr(self, "media_player") and self.media_player is not None:
                self.media_player.pause()
                self.media_player.setPosition(0)
            if hasattr(self, "timeline") and self.timeline is not None:
                self.timeline.set_position(0)
            if hasattr(self, "update_playback_subtitle_highlight"):
                self.update_playback_subtitle_highlight(0)
        except Exception:
            pass
        if hasattr(self, "refresh_source_video_list"):
            self.refresh_source_video_list()
