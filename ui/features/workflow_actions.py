import os
from PySide6.QtWidgets import (
    QToolButton, QMessageBox)
from PySide6.QtCore import Qt, QUrl

from widgets.progress_dialog import BackgroundableProgressDialog
from worker_adapters import (
    ExtractionWorker,
    VocalSeparationWorker,
)



class WorkflowActionsMixin:
    def refresh_ui_state(self):
        """Basic enable/disable rules to guide user flow."""
        review_mode = self._preview_is_playing()
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        v_ok = bool(source_path and os.path.exists(source_path))
        a_ok = bool(self.audio_source_edit.text().strip()) and os.path.exists(self.audio_source_edit.text().strip())
        has_translated_text = bool(self.translated_text.toPlainText().strip())
        has_any_subtitles = bool(self.current_translated_segments or self.current_segments)
        translation_ready = self._translation_phase_complete()
        mode = self.get_output_mode_key()
        # A persisted project can contain a stale ``running`` step when a
        # previous process was interrupted between TTS and audio mixing.
        # Persisted workflow history must never keep playback disabled after
        # reopening the project; only a live worker/operation owns that lock.
        voice_thread = getattr(self, "voice_thread", None)
        try:
            live_voice_worker = bool(voice_thread and voice_thread.isRunning())
        except RuntimeError:
            live_voice_worker = False
        voice_running = bool(
            getattr(self, "_voice_generation_active", False)
            or live_voice_worker
        )
        # Translation is sufficient for a final subtitle-only export.  TTS
        # remains optional: if it has not been generated, Export and Fast
        # Preview retain the source audio and burn the translated subtitles.
        # Voice-only projects without subtitles keep their historical rule.
        # A loaded video is always exportable. Subtitle/voice work is
        # optional: when neither exists, Export creates a source-video copy
        # instead of leaving a valid project with a disabled primary action.
        export_thread = getattr(self, "export_thread", None)
        try:
            export_running = bool(export_thread and export_thread.isRunning())
        except RuntimeError:
            export_running = False
        can_export = v_ok and not export_running

        self.extract_btn.setEnabled(v_ok)
        vocal_running = bool(getattr(self, "vocal_thread", None) and self.vocal_thread.isRunning())
        can_separate = bool((a_ok or v_ok) and not vocal_running)
        self.vocal_sep_btn.setEnabled(can_separate)
        if hasattr(self, "audio_separation_btn"):
            self.audio_separation_btn.setEnabled(can_separate)
        if hasattr(self, "_refresh_audio_stem_controls"):
            self._refresh_audio_stem_controls()
        if hasattr(self, "voice_timing_sync_combo") and hasattr(self, "voice_speed_spin"):
            sync_mode = self.voice_timing_sync_combo.currentText().strip().lower()
            self.voice_speed_spin.setEnabled(sync_mode != "off")
        self.transcribe_btn.setEnabled(a_ok)
        self.translate_btn.setEnabled(bool(self.transcript_text.toPlainText().strip()))
        self.apply_translated_btn.setEnabled(translation_ready and has_translated_text)
        if hasattr(self, "rewrite_translation_btn"):
            self.rewrite_translation_btn.setEnabled(
                translation_ready and bool(self.transcript_text.toPlainText().strip()) and has_translated_text
            )
        if hasattr(self, "subtitle_editor_btn"):
            # Original-only projects need the editor in order to export the
            # review XLSX, fill Translated text externally, and import it.
            self.subtitle_editor_btn.setEnabled(has_any_subtitles and not review_mode)
        if hasattr(self, "rewrite_selected_segment_btn"):
            has_selected_segment = 0 <= int(getattr(self, "_selected_segment_index", -1)) < len(self.current_translated_segments or [])
            self.rewrite_selected_segment_btn.setEnabled(
                translation_ready and bool(self.transcript_text.toPlainText().strip()) and has_translated_text and has_selected_segment
            )
        if hasattr(self, "_refresh_audio_inspector_dub_voice_buttons"):
            self._refresh_audio_inspector_dub_voice_buttons()
        generated_mode = not self.using_existing_audio_source()
        if hasattr(self, "voiceover_btn"):
            self.voiceover_btn.setEnabled(translation_ready and has_translated_text and generated_mode and mode in ("voice", "both"))
        preview_enabled = v_ok and not voice_running
        if hasattr(self, "quick_preview_btn"):
            self.quick_preview_btn.setEnabled(preview_enabled)
        if hasattr(self, "styled_preview_btn"):
            self.styled_preview_btn.setEnabled(preview_enabled)
        if hasattr(self, "preview_btn"):
            self.preview_btn.setVisible(True)
            self.preview_btn.setEnabled(preview_enabled and not getattr(self, "_styled_preview_running", False))
        if hasattr(self, "video_filter_apply_btn"):
            has_active_filters = self.has_active_video_filters() if hasattr(self, "has_active_video_filters") else False
            self.video_filter_apply_btn.setVisible(True)
            self.video_filter_apply_btn.setEnabled(
                self.is_filter_workflow_active()
                and v_ok
                and has_active_filters
                and not getattr(self, "_styled_preview_running", False)
            )
            self.video_filter_apply_btn.setText("Applying..." if getattr(self, "_video_filter_apply_requested", False) and getattr(self, "_styled_preview_running", False) else "Apply Filter")
        is_rendering_filter_preview = bool(getattr(self, "_video_filter_apply_requested", False) and getattr(self, "_styled_preview_running", False))
        if hasattr(self, "video_filter_render_status_label"):
            status_text = ""
            if not self.is_filter_workflow_active():
                status_text = ""
            elif getattr(self, "_video_filter_apply_requested", False) and getattr(self, "_styled_preview_running", False):
                status_text = "Rendering filtered preview video..."
            elif getattr(self, "_video_filter_preview_dirty", False):
                status_text = "Filter changes pending. Click Apply Filter to render motion preview."
            elif self._is_realtime_color_filter_state():
                status_text = "Realtime MPV preview active."
            elif self.has_active_video_filters() if hasattr(self, "has_active_video_filters") else False:
                status_text = "Filtered preview video is ready."
            self.video_filter_render_status_label.setText(status_text)
            self.video_filter_render_status_label.setVisible(bool(status_text))
        if hasattr(self, "video_filter_render_progress"):
            self.video_filter_render_progress.setVisible(self.is_filter_workflow_active() and is_rendering_filter_preview)
        if hasattr(self, "reset_framing_btn"):
            scale_mode = self.get_output_scale_mode_key() if hasattr(self, "get_output_scale_mode_key") else "fit"
            focus_x, focus_y = self.get_output_fill_focus() if hasattr(self, "get_output_fill_focus") else (0.5, 0.5)
            framing_dirty = abs(float(focus_x) - 0.5) > 0.001 or abs(float(focus_y) - 0.5) > 0.001
            # The action is only meaningful for a filled canvas whose focus
            # has actually moved.  Keeping a disabled, empty-looking button
            # in the compact workbench wastes a row and made the Canvas
            # controls appear clipped in the UI.
            reset_available = bool(v_ok and scale_mode == "fill")
            self.reset_framing_btn.setVisible(reset_available)
            self.reset_framing_btn.setEnabled(reset_available and framing_dirty)
        if hasattr(self, "play_btn"):
            self.play_btn.setEnabled(v_ok and not voice_running and not getattr(self, "_styled_preview_running", False))
        if hasattr(self, "stop_btn"):
            self.stop_btn.setEnabled(v_ok and not voice_running)
        if hasattr(self, "blur_area_btn"):
            self.blur_area_btn.setEnabled(v_ok and not review_mode)
        # Visual layers operate directly on the loaded source video; they do
        # not require transcript, translation, or a generated output first.
        self._optional_layer_controls_ready = bool(v_ok and not voice_running and not review_mode)
        for button_name in ("blur_add_btn", "add_logo_btn", "add_mask_btn", "add_text_btn"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(self._optional_layer_controls_ready)
        # Subtitle segments are valid as soon as a transcript/translation is
        # available. Keep the shared + Layer menu usable for manual fixes
        # without unlocking the unrelated overlay-layer actions early.
        if hasattr(self, "add_layer_btn"):
            self.add_layer_btn.setEnabled(v_ok and not voice_running and not review_mode)
        if hasattr(self, "blur_add_btn"):
            self.blur_add_btn.setEnabled(
                self._optional_layer_controls_ready
                and not bool(getattr(self, "_filter_thumbnail_visible", False))
            )
        if hasattr(self, "ocr_region_btn"):
            self.ocr_region_btn.setEnabled(v_ok)
        if hasattr(self, "ocr_translator_btn"):
            self.ocr_translator_btn.setEnabled(v_ok)
        if hasattr(self, "_sync_blur_controls"):
            self._sync_blur_controls()
        if hasattr(self, "free_voice_combo"):
            self.free_voice_combo.setEnabled(
                generated_mode
                and mode in ("voice", "both")
            )
        if hasattr(self, "voice_engine_combo"):
            self.voice_engine_combo.setEnabled(generated_mode and mode in ("voice", "both"))
        if hasattr(self, "premium_voice_combo"):
            self.premium_voice_combo.setEnabled(False)
        if hasattr(self, "bg_music_edit"):
            self.bg_music_edit.setEnabled(generated_mode and mode in ("voice", "both"))
        if hasattr(self, "mixed_audio_edit"):
            self.mixed_audio_edit.setEnabled(mode in ("voice", "both") and bool(hasattr(self, "use_existing_audio_radio") and self.use_existing_audio_radio.isChecked()))
        if hasattr(self, "preview_voice_btn"):
            self.preview_voice_btn.setVisible(mode in ("voice", "both"))
            self.preview_voice_btn.setEnabled(bool(self.voice_catalog_entries_all))
        has_timeline_segments = bool(self.get_active_segments())
        selected_overlay_is_splittable = False
        selected_layer_locked = False
        has_selected_timeline_layer = False
        selected_layer_id = str(getattr(getattr(self, "timeline", None), "_selected_layer_id", "") or "")
        if selected_layer_id and getattr(getattr(self, "timeline", None), "_timeline", None):
            for track in self.timeline._timeline.tracks:
                for layer in track.layers:
                    if layer.id != selected_layer_id:
                        continue
                    has_selected_timeline_layer = True
                    selected_layer_locked = bool(getattr(track, "locked", False)) or bool(getattr(layer, "locked", False))
                    layer_type = str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower()
                    selected_overlay_is_splittable = layer_type in {"blur", "mask", "text"} or (
                        layer_type == "image" and str(getattr(track, "name", "")) == "L1 Logo"
                    )
                    break
                if selected_overlay_is_splittable:
                    break
        if hasattr(self, "timeline_split_btn"):
            self.timeline_split_btn.setEnabled(
                (has_timeline_segments or selected_overlay_is_splittable)
                and (not has_selected_timeline_layer or not selected_layer_locked)
                and not review_mode
            )
        if hasattr(self, "timeline_delete_btn"):
            self.timeline_delete_btn.setEnabled(
                (has_timeline_segments or selected_overlay_is_splittable)
                and (not has_selected_timeline_layer or not selected_layer_locked)
                and not review_mode
            )
        if hasattr(self, "inspector_delete_segment_btn"):
            self.inspector_delete_segment_btn.setEnabled(
                (has_timeline_segments or selected_overlay_is_splittable)
                and (not has_selected_timeline_layer or not selected_layer_locked)
                and not review_mode
            )

        # Keep the timeline readable and fully seekable during playback, but
        # make every state-changing control unavailable in Review Mode.
        if review_mode:
            for button_name in (
                "timeline_undo_btn", "timeline_redo_btn", "timeline_selection_mode_btn",
                "timeline_clear_selection_btn", "timeline_alt_transcribe_btn",
            ):
                button = getattr(self, button_name, None)
                if button is not None:
                    button.setEnabled(False)
        else:
            self._refresh_timeline_history_buttons()
            selection_exists = bool(getattr(self.timeline, "selection_range", lambda: None)()) if hasattr(self, "timeline") else False
            if hasattr(self, "timeline_selection_mode_btn"):
                self.timeline_selection_mode_btn.setEnabled(bool(v_ok))
            if hasattr(self, "timeline_clear_selection_btn"):
                self.timeline_clear_selection_btn.setEnabled(selection_exists)
            if hasattr(self, "timeline_alt_transcribe_btn"):
                self.timeline_alt_transcribe_btn.setVisible(selection_exists)
                self.timeline_alt_transcribe_btn.setEnabled(selection_exists and not bool(getattr(self, "_alternate_range_transcription_worker", None)))
        if hasattr(self, "inspector_stack"):
            self.inspector_stack.setEnabled(not review_mode)
        # Lock only the layout handle while playing.  The splitter's child
        # widgets remain enabled so playback/seek controls still work.
        splitter = getattr(self, "preview_timeline_splitter", None)
        if splitter is not None:
            try:
                splitter.handle(1).setEnabled(not review_mode)
            except Exception:
                pass

        self._update_generate_button_menu(has_data=has_translated_text or has_timeline_segments)
        self.update_workflow_stage_badges()

        if hasattr(self, "clean_project_action"):
            self.clean_project_action.setEnabled(self._has_cleanable_project_data())
        self.run_all_btn.setEnabled((v_ok or has_translated_text) and not self._pipeline_active)
        self.preview_frame_btn.setEnabled(v_ok and bool(self.get_active_segments()))
        self.preview_5s_btn.setEnabled(v_ok)
        if hasattr(self, "preview_5s_action"):
            self.preview_5s_action.setEnabled(v_ok)
        self.export_btn.setEnabled(can_export)
        if hasattr(self, "download_subtitle_action"):
            self.download_subtitle_action.setEnabled(bool(self.translated_text.toPlainText().strip()))
        if hasattr(self, "download_original_action"):
            self.download_original_action.setEnabled(bool(self.transcript_text.toPlainText().strip()))
        if hasattr(self, "export_voice_action"):
            has_voice = bool(getattr(self, "last_voice_vi_path", "") and os.path.exists(self.last_voice_vi_path))
            self.export_voice_action.setEnabled(has_voice or has_translated_text)
        if hasattr(self, "tabs"):
            self.tabs.setTabEnabled(1, v_ok)
            self.tabs.setTabEnabled(2, v_ok and mode in ("voice", "both"))
        # Audio Source and related controls are needed before Transcript, so
        # the workflow Audio tab must be available as soon as a video is
        # selected—not only after the optional TTS stage completes.
        if hasattr(self, "audio_tab_btn"):
            self.audio_tab_btn.setEnabled(v_ok)
        self.update_workflow_availability()
        self.update_guidance_panel()
        self._update_ocr_overlay()

    def _update_generate_button_menu(self, has_data: bool):
        if not hasattr(self, "run_all_btn"):
            return
        btn = self.run_all_btn
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction
        if btn.menu() is None:
            menu = QMenu(btn)
            menu.setObjectName("generateMenu")
            menu.setMinimumWidth(240)

            # --- ✨ Auto Edit Recap Top Actions ---
            recap_action = QAction("✨ Run Auto Edit Recap", menu)
            if hasattr(self, "run_auto_recap_workflow"):
                recap_action.triggered.connect(self.run_auto_recap_workflow)
            else:
                recap_action.triggered.connect(self.run_all_pipeline)
            menu.addAction(recap_action)

            recap_custom_action = QAction("⚙ Customize Auto Recap Rules...", menu)
            if hasattr(self, "open_auto_recap_settings_dialog"):
                recap_custom_action.triggered.connect(self.open_auto_recap_settings_dialog)
            menu.addAction(recap_custom_action)

            menu.addSeparator()

            step_menu = menu.addMenu("Step-by-Step")
            step_menu.setObjectName("generateStepMenu")
            step_menu.setMinimumWidth(220)
            transcript_action = QAction("Run to Original Transcript", step_menu)
            transcript_action.triggered.connect(lambda: self.run_pipeline_to_stage("transcript"))
            translate_menu = step_menu.addMenu("Run to Translate")
            translate_menu.setObjectName("generateStepMenu")
            translate_menu.setMinimumWidth(220)
            translate_action = QAction("Auto Translate", translate_menu)
            translate_action.triggered.connect(lambda: self.run_pipeline_to_stage("translate"))
            import_translation_action = QAction("Import Translated File…", translate_menu)
            import_translation_action.triggered.connect(self.import_translated_srt)
            translate_menu.addActions([translate_action, import_translation_action])
            tts_menu = step_menu.addMenu("Generate Voice / TTS")
            tts_menu.setObjectName("generateStepMenu")
            tts_menu.setMinimumWidth(220)
            tts_action = QAction("TTS", tts_menu)
            tts_action.triggered.connect(lambda: self.run_pipeline_to_stage("tts"))
            tts_skip_action = QAction("Skip", tts_menu)
            tts_skip_action.triggered.connect(self.skip_tts_stage)
            tts_menu.addActions([tts_action, tts_skip_action])
            step_menu.insertAction(translate_menu.menuAction(), transcript_action)
            step_menu.addAction(tts_menu.menuAction())
            full_menu = menu.addMenu("Full Pipeline")
            full_menu.setObjectName("generateStepMenu")
            full_menu.setMinimumWidth(220)
            full_action = QAction("Run full pipeline", full_menu)
            full_action.triggered.connect(self.run_all_pipeline)
            full_menu.addAction(full_action)
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.InstantPopup)
            btn.setText("Generate")
            self._generate_transcript_action = transcript_action
            self._generate_translate_action = translate_action
            self._generate_import_translated_srt_action = import_translation_action
            self._generate_tts_action = tts_action
            self._generate_tts_skip_action = tts_skip_action
        self.update_workflow_stage_badges()

    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            for url in mime_data.urls():
                local_path = url.toLocalFile()
                if local_path and os.path.splitext(local_path)[1].lower() in {".mp4", ".mkv", ".avi", ".mov"}:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return
        for url in mime_data.urls():
            local_path = url.toLocalFile()
            if local_path and os.path.splitext(local_path)[1].lower() in {".mp4", ".mkv", ".avi", ".mov"}:
                if getattr(self, "current_project_state", None) is not None:
                    try:
                        self.persist_current_timeline_project_data()
                    except Exception:
                        pass
                if hasattr(self, "project_controller"):
                    self.project_controller.reset_project_runtime_state()
                self.ensure_media_backend_ready()
                self._current_video_path = os.path.abspath(local_path)
                self.video_path_edit.setText(local_path)
                self.media_player.setSource(QUrl.fromLocalFile(local_path))
                self.refresh_video_dimensions(local_path)
                self.play_btn.setText("Play")
                self.timeline.set_segments([])
                self.timeline.set_playing(False)
                self.current_segments = []
                self.current_translated_segments = []
                self.current_segment_models = []
                self.current_translated_segment_models = []
                self.current_project_state = self.ensure_current_project()
                self._allow_post_pipeline_preview_assets = False
                self.load_project_context(self.current_project_state)
                if hasattr(self, "timeline") and hasattr(self.timeline, "set_video_source"):
                    duration = float(self.timeline._probe_video_duration(local_path))
                    self.timeline.set_video_source(self._current_video_path, duration)
                if hasattr(self, "refresh_source_video_list"):
                    self.refresh_source_video_list()
                self.media_player.pause()
                self.media_player.setPosition(0)
                self.refresh_ui_state()
                self.sync_live_subtitle_preview()
                event.acceptProposedAction()
                return
        event.ignore()

    def run_extraction(self):
        v_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text()
        if not v_path: return

        target_dir = self.audio_folder_edit.text()
        file_basename = os.path.splitext(os.path.basename(v_path))[0]
        a_path = os.path.join(target_dir, file_basename + ".wav")

        print(f"[Extraction] start: video={v_path} audio={a_path}")
        self.progress_bar.setValue(10)
        self.update_project_step("extract_audio", "running")
        self.extraction_thread = ExtractionWorker(v_path, a_path)
        self.extraction_thread.finished.connect(self.on_extraction_finished)
        self.extraction_thread.start()

    def on_extraction_finished(self, success, path):
        print(f"[Extraction] finished: success={success} path={path}")
        self.progress_bar.setValue(30)
        self.extract_btn.setEnabled(True)
        if success:
            self.last_extracted_audio = path
            self.audio_source_edit.setText(path)
            self.processed_artifacts["audio_extracted"] = path
            self.update_project_artifact("extracted_audio", path)
            self.update_project_step("extract_audio", "done")
            self.log(f"[Audio] Original audio extracted: {path}")
            self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)
        else:
            self.update_project_step("extract_audio", "failed")
            self.show_error("Error", "Extraction failed.", str(path))
            self._pipeline_fail("Extraction failed.")
            return

        self.refresh_ui_state()
        self._pipeline_advance("extraction")

    def run_vocal_separation(self):
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (
            self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else ""
        )
        audio_src = self.audio_source_edit.text().strip() if hasattr(self, "audio_source_edit") else ""
        target_dir = self.audio_folder_edit.text().strip() if hasattr(self, "audio_folder_edit") else ""
        if not target_dir:
            target_dir = os.path.join(self.workspace_root, "temp")
        os.makedirs(target_dir, exist_ok=True)

        video_for_worker = None
        if not audio_src or not os.path.exists(audio_src):
            if source_path and os.path.exists(source_path):
                file_basename = os.path.splitext(os.path.basename(source_path))[0]
                audio_src = os.path.join(target_dir, file_basename + ".wav")
                video_for_worker = source_path
            else:
                QMessageBox.warning(self, "Error", "Please import a video or select an audio file first!")
                return

        try:
            from services.resource_download_service import ResourceDownloadService
            if not ResourceDownloadService(self.workspace_root).is_resource_installed("separation:uvr_mdx"):
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle("Separation model missing")
                box.setText("Mô hình tách giọng nói / nhạc nền (UVR MDX) chưa được cài đặt.")
                box.setInformativeText("Nhấn 'Tải mô hình ngay' để tự động tải và cài đặt (~66 MB), hoặc mở 'Manage Resources' để quản lý.")
                install_btn = box.addButton("Tải mô hình ngay (Install Now)", QMessageBox.AcceptRole)
                manage_btn = box.addButton("Manage Resources", QMessageBox.ActionRole)
                box.addButton("Hủy (Cancel)", QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() is install_btn:
                    self.open_resource_manager_dialog(focus_resource_id="separation:uvr_mdx", auto_start=True)
                elif box.clickedButton() is manage_btn:
                    self.open_resource_manager_dialog(focus_resource_id="separation:uvr_mdx")
                return
        except Exception as exc:
            self.log(f"[Audio] Separation model preflight failed: {exc}")
            return

        self.progress_bar.setValue(35)
        if hasattr(self, "audio_separation_btn") and self.audio_separation_btn is not None:
            self.audio_separation_btn.setEnabled(False)
            self.audio_separation_btn.setText("Separating Voice.wav + Music.wav (0%)…")
        if hasattr(self, "vocal_sep_btn") and self.vocal_sep_btn is not None:
            self.vocal_sep_btn.setEnabled(False)
            self.vocal_sep_btn.setText("Separating... 0%")
        if hasattr(self, "audio_stem_status_label") and self.audio_stem_status_label is not None:
            self.audio_stem_status_label.setText("⏳ Đang chuẩn bị tách nhạc & giọng… (0%)")
        if hasattr(self, "mini_status_bar") and self.mini_status_bar is not None:
            self.mini_status_bar.set_active("Vocal Separation", "Tách Voice.wav & Music.wav…")
            self.mini_status_bar.set_progress(percent=0, detail="Chuẩn bị tách nhạc & giọng…", chip="UVR MDX")
        self.update_project_step("separate_audio", "running")

        self.vocal_thread = VocalSeparationWorker(audio_src, target_dir, video_path=video_for_worker)
        self.vocal_thread.progress.connect(self.on_vocal_separation_progress)
        self.vocal_thread.finished.connect(self.on_vocal_separation_finished)
        self.vocal_thread.start()

    def on_vocal_separation_progress(self, percent: int, message: str):
        pct = max(0, min(100, int(percent)))
        btn_text = f"Separating Voice.wav + Music.wav ({pct}%)…"
        if hasattr(self, "audio_separation_btn") and self.audio_separation_btn is not None:
            self.audio_separation_btn.setText(btn_text)
        if hasattr(self, "vocal_sep_btn") and self.vocal_sep_btn is not None:
            self.vocal_sep_btn.setText(f"Separating... {pct}%")
        if hasattr(self, "audio_stem_status_label") and self.audio_stem_status_label is not None:
            self.audio_stem_status_label.setText(f"⏳ {message}" if message else f"⏳ Đang tách âm thanh: {pct}%")
        if hasattr(self, "mini_status_bar") and self.mini_status_bar is not None:
            self.mini_status_bar.set_progress(
                percent=pct,
                detail=str(message or f"Đang tách âm thanh ({pct}%)"),
                chip="UVR MDX",
            )
        mapped = 35 + int(pct * 0.15)
        if hasattr(self, "progress_bar") and self.progress_bar is not None:
            self.progress_bar.setValue(mapped)

    def on_vocal_separation_finished(self, vocal, music, error):
        if hasattr(self, "vocal_sep_btn") and self.vocal_sep_btn is not None:
            self.vocal_sep_btn.setEnabled(True)
            self.vocal_sep_btn.setText("Separate Voice and Background")
        if hasattr(self, "audio_separation_btn") and self.audio_separation_btn is not None:
            self.audio_separation_btn.setEnabled(True)
            self.audio_separation_btn.setText("Separate Voice and Music")
        if hasattr(self, "progress_bar") and self.progress_bar is not None:
            self.progress_bar.setValue(50)

        if error:
            if hasattr(self, "audio_stem_status_label") and self.audio_stem_status_label is not None:
                self.audio_stem_status_label.setText(f"❌ Tách âm thất bại: {error}")
            if hasattr(self, "mini_status_bar") and self.mini_status_bar is not None:
                self.mini_status_bar.set_error(f"Tách âm thất bại: {error}")
            self.update_project_step("separate_audio", "failed")
            err_lower = error.lower()
            missing_demucs = (
                "no module named" in err_lower and "demucs" in err_lower
            ) or (
                "demucs is not installed" in err_lower
            ) or (
                "requires the 'demucs' library" in err_lower
            )
            if missing_demucs:
                QMessageBox.warning(
                    self,
                    "Dependency Missing",
                    "Vocal Separation requires the 'demucs' library.\n\n"
                    "Please run (using the same Python you run this app with):\n"
                    "python -m pip install demucs\n\n"
                    f"Details:\n{error}",
                )
            else:
                QMessageBox.critical(self, "Error", f"Separation failed:\n\n{error}")
            self.log(error)
            self.refresh_ui_state()
            return

        if hasattr(self, "mini_status_bar") and self.mini_status_bar is not None:
            self.mini_status_bar.set_done("✨ Tách Voice.wav & Music.wav thành công!")

        if vocal and os.path.exists(vocal):
            selected_mode = getattr(self, "audio_separation_mode_combo", None)
            selected_mode = selected_mode.currentData() if selected_mode is not None else "voice"
            selected_audio = music if selected_mode == "music" and music and os.path.exists(music) else vocal
            self.audio_source_edit.setText(selected_audio)
            self.last_extracted_audio = selected_audio
            self.last_vocals_path = vocal
            self.last_music_path = music
            self.processed_artifacts["vocals"] = vocal
            self.update_project_artifact("vocals", vocal)
            if music:
                self.processed_artifacts["music"] = music
                self.update_project_artifact("music", music)
            if getattr(self, "vocal_thread", None) and getattr(self.vocal_thread, "audio_path", None):
                extracted_path = self.vocal_thread.audio_path
                if os.path.exists(extracted_path) and not self.processed_artifacts.get("audio_extracted"):
                    self.processed_artifacts["audio_extracted"] = extracted_path
                    self.update_project_artifact("extracted_audio", extracted_path)
            if hasattr(self, "schedule_timeline_visual_refresh"):
                self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)
            self._refresh_audio_stem_controls()
            self.update_project_step("separate_audio", "done")
            QMessageBox.information(self, "Success",
                f"Audio stems separated!\n\nVoice.wav: {os.path.basename(vocal)}\nMusic.wav: {os.path.basename(music)}\n\nSelected for transcription: {os.path.basename(selected_audio)}")
            self._pipeline_advance("separation")
        else:
            self.update_project_step("separate_audio", "failed")
            self._pipeline_fail("Separation did not produce output.")
        self.refresh_ui_state()

    def _refresh_audio_stem_controls(self):
        """Refresh the explicit Voice/Music stem actions after separation or reload."""
        artifacts = getattr(self, "processed_artifacts", {}) or {}
        vocal = str(getattr(self, "last_vocals_path", "") or artifacts.get("vocals", ""))
        music = str(getattr(self, "last_music_path", "") or artifacts.get("music", ""))
        vocal_ok = bool(vocal and os.path.isfile(vocal))
        music_ok = bool(music and os.path.isfile(music))
        for attr, enabled in (("add_voice_stem_btn", vocal_ok), ("add_music_stem_btn", music_ok)):
            if hasattr(self, attr):
                getattr(self, attr).setEnabled(enabled)
        if hasattr(self, "audio_stem_status_label"):
            names = []
            if vocal_ok:
                names.append(f"Voice.wav: {os.path.basename(vocal)}")
            if music_ok:
                names.append(f"Music.wav: {os.path.basename(music)}")
            self.audio_stem_status_label.setText("Ready: " + " · ".join(names) if names else "No separated stems yet")

    def _add_audio_stem_to_timeline(self, path: str, track_name: str, label: str):
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Audio stem", f"{label} was not found. Separate the audio first.")
            return
        try:
            from app.layers.audio import AudioLayer
            from app.layers.base import LayerType
            from app.layers.sync_bridge import find_or_create_track
            timeline_model = self.timeline._timeline
            duration = max(0.1, float(getattr(self.timeline, "_duration", 0.0) or 0.0))
            track = find_or_create_track(timeline_model, track_name, LayerType.AUDIO, 80)
            track.visible = True
            track.layers = [layer for layer in track.layers if str(getattr(layer, "source", "")) != path]
            volume_attr = "audio_music_volume_slider" if "Music" in track_name else "audio_voice_volume_slider"
            volume = (getattr(self, volume_attr).value() / 100.0) if hasattr(self, volume_attr) else 1.0
            track.layers.append(AudioLayer(
                name=track_name, source=path, start=0.0, end=duration,
                source_start=0.0, speed=1.0, volume=volume,
            ))
            track.metadata["stem"] = "music" if "Music" in track_name else "voice"
            self.timeline._track_heights[track.id] = self.timeline._compute_track_height(track)
            self.timeline._redraw()
            self.persist_current_timeline_project_data()
            self.log(f"[Audio] {label} added to timeline: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Timeline error", f"Could not add {label} to the timeline:\n{exc}")

    def add_music_stem_to_timeline(self):
        artifacts = getattr(self, "processed_artifacts", {}) or {}
        self._add_audio_stem_to_timeline(
            str(getattr(self, "last_music_path", "") or artifacts.get("music", "")),
            "A2 Music", "Music.wav",
        )

    def add_voice_stem_to_timeline(self):
        artifacts = getattr(self, "processed_artifacts", {}) or {}
        self._add_audio_stem_to_timeline(
            str(getattr(self, "last_vocals_path", "") or artifacts.get("vocals", "")),
            "A3 Voice", "Voice.wav",
        )

    def _set_stem_track_volume(self, track_name: str, value: int, label_attr: str):
        if hasattr(self, label_attr):
            getattr(self, label_attr).setText(f"{int(value)}%")
        timeline_model = getattr(getattr(self, "timeline", None), "_timeline", None)
        if timeline_model is None:
            return
        for track in timeline_model.tracks:
            if track.name == track_name:
                track.metadata["_volume"] = float(value)
                for layer in track.layers:
                    layer.volume = max(0.0, float(value) / 100.0)
        self.timeline._redraw()
        self.persist_current_timeline_project_data()

    def on_audio_music_volume_changed(self, value: int):
        self._set_stem_track_volume("A2 Music", value, "audio_music_volume_label")

    def on_audio_voice_volume_changed(self, value: int):
        self._set_stem_track_volume("A3 Voice", value, "audio_voice_volume_label")

    def run_transcription(self):
        is_ocr = self.get_transcription_engine() == "ocr"
        if not self.ensure_required_resources(
            "Transcription",
            include_whisper=not is_ocr,
            include_ocr=is_ocr,
            validate_pipeline_runtime=True,
        ):
            return
        self.subtitle_controller.run_transcription()

    def on_transcription_finished(self, segments, error=""):
        self.subtitle_controller.on_transcription_finished(segments, error)

    def run_translation(self):
        self.subtitle_controller.run_translation()

    def on_translation_finished(self, translated_srt, error, fallback_notice=""):
        self.subtitle_controller.on_translation_finished(translated_srt, error, fallback_notice)

    def run_rewrite_translation(self):
        self.subtitle_controller.run_rewrite_translation()

    def run_rewrite_selected_segment(self):
        self.subtitle_controller.run_rewrite_selected_segment()

    def on_rewrite_translation_finished(self, translated_srt, error):
        self.subtitle_controller.on_rewrite_translation_finished(translated_srt, error)

    def on_rewrite_selected_segment_finished(self, translated_srt, error):
        self.subtitle_controller.on_rewrite_selected_segment_finished(translated_srt, error)

    def _close_export_progress_dialog(self):
        try:
            dlg = getattr(self, "export_progress_dialog", None)
            if dlg is not None:
                self._unregister_progress_dialog(dlg)
                dlg.hide()
                dlg.deleteLater()
        finally:
            self.export_progress_dialog = None

    def _ensure_export_progress_dialog(self):
        dlg = getattr(self, "export_progress_dialog", None)
        if dlg is not None:
            return dlg
        dlg = BackgroundableProgressDialog("Preparing final export...", "Hide", 0, 100, self)
        dlg.setWindowTitle("Exporting Video")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoReset(False)
        dlg.setAutoClose(False)
        dlg.setMinimumWidth(520)
        dlg.setValue(0)
        dlg.setLabelText("Exporting final video...\n\nWaiting to start...")
        dlg.setStyleSheet(
            "QProgressDialog { background-color: #101826; color: #e6eef9; }"
            "QLabel { color: #e6eef9; background: transparent; }"
            "QPushButton { background-color: #24364f; color: #ffffff; border: 1px solid #335171; border-radius: 10px; padding: 8px 14px; font-weight: 700; }"
            "QPushButton:hover { background-color: #2d4665; border-color: #4575a8; }"
            "QProgressBar { border: 1px solid #2a3a50; border-radius: 10px; text-align: center; background-color: #111927; color: white; min-height: 16px; }"
            "QProgressBar::chunk { background-color: #4ed0b3; border-radius: 10px; }"
        )
        try:
            dlg.setCancelButtonText("Run in background")
            dlg.canceled.connect(dlg.hide)
        except Exception:
            pass
        self.export_progress_dialog = dlg
        self._register_progress_dialog(dlg)
        dlg.show()
        return dlg

    def on_export_progress(self, percent: int, message: str):
        dlg = self._ensure_export_progress_dialog()
        if dlg is None:
            return
        message_text = str(message or "Exporting final video...").strip() or "Exporting final video..."
        history = list(getattr(self, "_export_progress_messages", []) or [])
        if not history or history[-1] != message_text:
            history.append(message_text)
        self._export_progress_messages = history[-4:]
        dlg.setLabelText("Exporting final video...\n\n" + "\n".join(self._export_progress_messages))
        if percent is None or int(percent) < 0:
            dlg.setRange(0, 0)
        else:
            if dlg.maximum() == 0:
                dlg.setRange(0, 100)
            value = max(0, min(100, int(percent)))
            dlg.setValue(value)
            try:
                self.progress_bar.setValue(value)
            except Exception:
                pass
        dlg.show()

    def get_whisper_model_name(self) -> str:
        selected = str(getattr(self, "selected_whisper_model_name", "auto") or "auto").strip().lower()
        is_gpu_mode = os.environ.get("VIUSTUDIO_DEVICE", "cuda").strip().lower() == "cuda"
        if not is_gpu_mode and selected == "medium":
            selected = "auto"
        if selected and selected != "auto":
            return selected
        model_root = os.path.join(self.workspace_root, "models", "faster_whisper")
        preferred_models = ("medium", "small", "base", "tiny") if is_gpu_mode else ("small", "base", "tiny")
        for candidate in preferred_models:
            model_dir = os.path.join(model_root, candidate)
            if os.path.isdir(model_dir) and any(
                name.endswith(".bin") for name in os.listdir(model_dir)
            ):
                return candidate
            snapshots_dir = os.path.join(
                model_root,
                f"models--Systran--faster-whisper-{candidate}",
                "snapshots",
            )
            if os.path.isdir(snapshots_dir):
                for snapshot_name in os.listdir(snapshots_dir):
                    if os.path.isfile(os.path.join(snapshots_dir, snapshot_name, "model.bin")):
                        return candidate
        return "medium"

    def get_whisper_model_path(self) -> str:
        return os.path.join(self.workspace_root, "models", "ggml-medium.bin")
