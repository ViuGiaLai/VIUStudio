import os
import copy
from uuid import uuid4
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QTextEdit, QComboBox,
                             QDoubleSpinBox,
                             QFrame, QMessageBox,
                             QDialog, QSizePolicy)
from PySide6.QtCore import Qt, QUrl, QTimer, QPoint, QRect

from worker_adapters import (
    AlternateRangeTranscriptionWorker,
)



class TimelineEditingMixin:
    def _commit_subtitle_mutation(self, *, selected_index=None, persist_empty=True, changed_indices=None):
        """Commit one subtitle edit to every runtime and project surface.

        Timeline blocks, hidden SRT editors, JSON artifacts, project-facing
        SRT files, live preview and generated voice must never be updated by
        separate best-effort paths.  Every user mutation funnels through this
        method so reopening/exporting cannot resurrect stale subtitle data.
        ``changed_indices`` identifies text-only cue edits; their old voice
        windows can be muted selectively while unchanged cues remain audible.
        """
        self._single_line_split_cache = None
        self.apply_segments_to_timeline()

        # Normalization in apply_segments_to_timeline may replace a list, so
        # rebuild both model collections and hidden editors afterwards.
        self.current_segment_models = self._dict_segments_to_models(
            self.current_segments or [], translated=False,
        )
        self.current_translated_segment_models = self._dict_segments_to_models(
            self.current_translated_segments or [], translated=True,
        )
        self._sync_hidden_transcript_text_from_segments()
        self._sync_hidden_translated_text_from_segments()

        # Keep the in-memory preview snapshot aligned at the commit boundary.
        # The debounce timer still rebuilds ASS/libass assets later, but the
        # visible overlay and playhead selection must never use the previous
        # cue list in the meantime (especially after SRT import/replacement).
        if hasattr(self, "live_preview_segments"):
            try:
                self.live_preview_segments = list(self.get_active_segments())
            except Exception:
                self.live_preview_segments = []

        if selected_index is not None:
            self.set_selected_segment_index(int(selected_index), sync_ui=True)
            if hasattr(self, "timeline"):
                self.timeline.set_active_segment_index(int(selected_index))

        self._invalidate_dubbed_output_after_subtitle_edit(changed_indices=changed_indices)

        state = getattr(self, "current_project_state", None)
        if persist_empty and state is not None:
            try:
                self.current_segment_models = self.project_bridge.persist_transcription(
                    state,
                    self.current_segments or [],
                    self.last_original_srt_path,
                )
                self.current_translated_segment_models = self.project_bridge.persist_translation(
                    state,
                    self.current_segment_models,
                    self.current_translated_segments or [],
                    self.last_translated_srt_path,
                )
            except Exception as exc:
                self.log(f"[Subtitle] Could not persist synchronized edit: {exc}")

        self.persist_current_timeline_project_data()
        self._regenerate_original_srt_from_segments()
        self._regenerate_translated_srt_from_segments()
        self.schedule_live_subtitle_preview_refresh()
        self.refresh_ui_state()

    def _sync_hidden_transcript_text_from_segments(self):
        if getattr(self, "_syncing_segment_editor", False):
            return
        self._syncing_hidden_editor_text = True
        try:
            self.transcript_text.setText(self.format_to_srt(self.current_segments))
        finally:
            self._syncing_hidden_editor_text = False

    def _apply_segment_timing(self, segment: dict, start: float, end: float):
        segment["start"] = float(start)
        segment["end"] = float(end)
        if "tts_group_start" in segment or "tts_group_end" in segment:
            segment["tts_group_start"] = float(start)
            segment["tts_group_end"] = float(end)

    def _build_split_segment_pair(self, segment: dict, split_time: float):
        first = dict(segment or {})
        second = dict(segment or {})

        first["start"] = float(segment.get("start", 0.0))
        first["end"] = float(split_time)
        second["start"] = float(split_time)
        second["end"] = float(segment.get("end", split_time))

        # Keep clip content unchanged on split; only timing is divided.
        first["text"] = str(segment.get("text", "") or "")
        second["text"] = str(segment.get("text", "") or "")
        first["tts_text"] = str(segment.get("tts_text", segment.get("text", "")) or "")
        second["tts_text"] = str(segment.get("tts_text", segment.get("text", "")) or "")
        first["words"] = []
        second["words"] = []
        first["manual_highlights"] = list(segment.get("manual_highlights", []))
        second["manual_highlights"] = list(segment.get("manual_highlights", []))
        if "tts_group_start" in first or "tts_group_end" in first:
            first["tts_group_start"] = float(first["start"])
            first["tts_group_end"] = float(first["end"])
            second["tts_group_start"] = float(second["start"])
            second["tts_group_end"] = float(second["end"])
        return first, second

    def _timeline_neighbor_bounds(self, index: int):
        active_segments = list(self.get_active_segments() or [])
        prev_end = 0.0
        next_start = max(0.0, float(getattr(self.timeline, "duration", 0)) / 1000.0)
        if index > 0 and index - 1 < len(active_segments):
            prev_end = float(active_segments[index - 1].get("end", 0.0))
        if index + 1 < len(active_segments):
            next_start = float(active_segments[index + 1].get("start", next_start))
        return prev_end, next_start

    def nudge_selected_timeline_segment(self, delta_seconds: float):
        segments = list(self.get_active_segments() or [])
        if not segments:
            return
        index = int(getattr(self, "_selected_segment_index", -1))
        if not (0 <= index < len(segments)):
            index = self._find_active_segment_index(self.media_player.position(), segments)
        if not (0 <= index < len(segments)):
            return

        target = segments[index]
        start = float(target.get("start", 0.0))
        end = float(target.get("end", 0.0))
        duration = max(0.0, end - start)
        gap = float(getattr(self.timeline, "SEGMENT_GAP", 0.03))
        prev_end, next_start = self._timeline_neighbor_bounds(index)
        max_timeline = max(0.0, float(getattr(self.timeline, "duration", 0)) / 1000.0)
        min_start = max(0.0, prev_end + gap)
        if index + 1 < len(segments):
            max_start = max(min_start, next_start - gap - duration)
        else:
            max_start = max(0.0, max_timeline - duration)
        new_start = min(max(start + float(delta_seconds), min_start), max_start)
        if abs(new_start - start) < 0.0001:
            return
        new_end = new_start + duration
        self.on_timeline_segment_timing_edit_started(index, start, end)
        self.on_timeline_segment_timing_changed(index, new_start, new_end)

    def ripple_nudge_selected_timeline_segment(self, delta_seconds: float):
        segments = list(self.get_active_segments() or [])
        if not segments:
            return
        index = int(getattr(self, "_selected_segment_index", -1))
        if not (0 <= index < len(segments)):
            index = self._find_active_segment_index(self.media_player.position(), segments)
        if not (0 <= index < len(segments)):
            return

        gap = float(getattr(self.timeline, "SEGMENT_GAP", 0.0))
        max_timeline = max(0.0, float(getattr(self.timeline, "duration", 0)) / 1000.0)
        prev_end, _next_start = self._timeline_neighbor_bounds(index)
        first_start = float(segments[index].get("start", 0.0))
        last_end = float(segments[-1].get("end", 0.0))
        min_delta = max(0.0, prev_end + gap) - first_start
        max_delta = max_timeline - last_end
        actual_delta = min(max(float(delta_seconds), min_delta), max_delta)
        if abs(actual_delta) < 0.0001:
            return

        history_entry = {
            "type": "batch_timing",
            "index": int(index),
            "selected_before": int(index),
            "selected_after": int(index),
            "current_before": [],
            "current_after": [],
            "translated_before": [],
            "translated_after": [],
        }

        if 0 <= index < len(self.current_segments or []):
            history_entry["current_before"] = [copy.deepcopy(seg) for seg in self.current_segments[index:]]
            for seg in self.current_segments[index:]:
                self._apply_segment_timing(
                    seg,
                    float(seg.get("start", 0.0)) + actual_delta,
                    float(seg.get("end", 0.0)) + actual_delta,
                )
            history_entry["current_after"] = [copy.deepcopy(seg) for seg in self.current_segments[index:]]
            self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
            self._sync_hidden_transcript_text_from_segments()

        if 0 <= index < len(self.current_translated_segments or []):
            history_entry["translated_before"] = [copy.deepcopy(seg) for seg in self.current_translated_segments[index:]]
            for seg in self.current_translated_segments[index:]:
                self._apply_segment_timing(
                    seg,
                    float(seg.get("start", 0.0)) + actual_delta,
                    float(seg.get("end", 0.0)) + actual_delta,
                )
            history_entry["translated_after"] = [copy.deepcopy(seg) for seg in self.current_translated_segments[index:]]
            self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
            self._sync_hidden_translated_text_from_segments()

        # A derived single-line cache is indexed against the pre-edit
        # subtitle list.  Reusing it after a delete can redraw a segment
        # which has just been removed, especially when a new segment is
        # inserted at the same point in the timeline.
        self._single_line_split_cache = None

        self._timeline_timing_undo_stack.append(history_entry)
        self._timeline_timing_redo_stack = []
        if len(self._timeline_timing_undo_stack) > 100:
            self._timeline_timing_undo_stack = self._timeline_timing_undo_stack[-100:]
        self._refresh_timeline_history_buttons()

        self.set_selected_segment_index(index, sync_ui=True)
        if hasattr(self, "timeline"):
            self.timeline.set_active_segment_index(index)
        self._commit_subtitle_mutation(selected_index=index)

    def _apply_timeline_structure_history_entry(self, entry: dict, *, use_after: bool):
        index = int(entry.get("index", -1))
        current_before = [copy.deepcopy(seg) for seg in list(entry.get("current_before", []) or [])]
        current_after = [copy.deepcopy(seg) for seg in list(entry.get("current_after", []) or [])]
        translated_before = [copy.deepcopy(seg) for seg in list(entry.get("translated_before", []) or [])]
        translated_after = [copy.deepcopy(seg) for seg in list(entry.get("translated_after", []) or [])]

        if self.current_segments is not None:
            replace_with = current_after if use_after else current_before
            replace_count = len(current_before if use_after else current_after)
            if current_before or current_after:
                self.current_segments[index:index + replace_count] = replace_with
                self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
                self._sync_hidden_transcript_text_from_segments()

        if self.current_translated_segments is not None:
            replace_with = translated_after if use_after else translated_before
            replace_count = len(translated_before if use_after else translated_after)
            if translated_before or translated_after:
                self.current_translated_segments[index:index + replace_count] = replace_with
                self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
                self._sync_hidden_translated_text_from_segments()

        target_index = int(entry.get("selected_after" if use_after else "selected_before", index))
        self.set_selected_segment_index(target_index, sync_ui=True)
        if hasattr(self, "timeline"):
            self.timeline.set_active_segment_index(target_index)
        self._commit_subtitle_mutation(selected_index=target_index)

    def split_selected_timeline_segment(self):
        if self._preview_is_playing():
            return
        selection = getattr(self.timeline, "selection_range", lambda: None)() if hasattr(self, "timeline") else None
        # A selected overlay always owns Split. The selection supplies cut
        # times only; it must never redirect the command to TS1.
        if self._split_selected_overlay_layer(selection):
            return
        if selection:
            start, end = selection
            if self._split_selected_subtitle_by_range(start, end):
                return
        # Overlay layers use the same Split action as subtitle/audio blocks.
        # Copying the layer preserves its style, transform and visibility;
        # only its identity and timing are changed.
        segments = list(self.get_active_segments() or [])
        if not segments:
            return
        index = int(getattr(self, "_selected_segment_index", -1))
        if not (0 <= index < len(segments)):
            index = self._find_active_segment_index(self.media_player.position(), segments)
        if not (0 <= index < len(segments)):
            QMessageBox.information(self, "Split Segment", "Please select an audio/subtitle block first.")
            return

        target = segments[index]
        split_time = self.timeline_position_seconds() if hasattr(self, "timeline_position_seconds") else float(self.media_player.position()) / 1000.0
        start = float(target.get("start", 0.0))
        end = float(target.get("end", 0.0))
        min_gap = max(0.12, getattr(self.timeline, "MIN_SEGMENT_DURATION", 0.1))
        if not (start + min_gap < split_time < end - min_gap):
            QMessageBox.information(
                self,
                "Split Segment",
                "Move the playhead inside the selected block before splitting.",
            )
            return

        split_history_entry = {
            "type": "split",
            "index": int(index),
            "selected_before": int(index),
            "selected_after": int(index + 1),
            "current_before": [],
            "current_after": [],
            "translated_before": [],
            "translated_after": [],
        }

        if 0 <= index < len(self.current_segments or []):
            split_history_entry["current_before"] = [copy.deepcopy(self.current_segments[index])]
            first, second = self._build_split_segment_pair(self.current_segments[index], split_time)
            self.current_segments[index:index + 1] = [first, second]
            split_history_entry["current_after"] = [copy.deepcopy(first), copy.deepcopy(second)]
            self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
            self._sync_hidden_transcript_text_from_segments()

        if 0 <= index < len(self.current_translated_segments or []):
            split_history_entry["translated_before"] = [copy.deepcopy(self.current_translated_segments[index])]
            first, second = self._build_split_segment_pair(self.current_translated_segments[index], split_time)
            self.current_translated_segments[index:index + 1] = [first, second]
            split_history_entry["translated_after"] = [copy.deepcopy(first), copy.deepcopy(second)]
            self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
            self._sync_hidden_translated_text_from_segments()

        self._timeline_timing_undo_stack.append(split_history_entry)
        self._timeline_timing_redo_stack = []
        if len(self._timeline_timing_undo_stack) > 100:
            self._timeline_timing_undo_stack = self._timeline_timing_undo_stack[-100:]
        self._refresh_timeline_history_buttons()

        self.set_selected_segment_index(index + 1, sync_ui=True)
        if hasattr(self, "timeline"):
            self.timeline.set_active_segment_index(index + 1)
        self._commit_subtitle_mutation(selected_index=index + 1)

    def _sync_preview_framing_to_player(self):
        """Keep native MPV crop framing consistent with the preview canvas."""
        view = getattr(self, "video_view", None)
        player = getattr(self, "media_player", None)
        if view is None or player is None or not hasattr(player, "set_preview_framing"):
            return
        try:
            source_w = float(getattr(view, "video_source_width", 0) or 0)
            source_h = float(getattr(view, "video_source_height", 0) or 0)
            canvas = view.get_preview_canvas_rect()
            source_ratio = source_w / source_h if source_w > 0 and source_h > 0 else 0.0
            canvas_ratio = canvas.width() / canvas.height() if canvas.height() > 0 else source_ratio
            focus_x, focus_y = self.get_output_fill_focus()
            player.set_preview_framing(
                source_ratio,
                canvas_ratio,
                self.get_output_scale_mode_key(),
                focus_x,
                focus_y,
            )
        except Exception as exc:
            self.log(f"[Preview] Could not sync canvas framing: {exc}")

    def _persist_video_filter_settings(self):
        """Persist realtime filter controls without requiring an Apply action."""
        try:
            self.save_user_settings()
        except Exception as exc:
            self.log(f"[Filter] Could not persist filter settings: {exc}")

    def transcribe_selected_range_alternate(self):
        timeline = getattr(self, "timeline", None)
        selection = timeline.selection_range() if timeline else None
        if not selection:
            QMessageBox.information(self, "Transcribe Selected Range", "Please create a Selection Range first.")
            return
        if getattr(self, "_alternate_range_transcription_worker", None) is not None:
            return
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        if not video_path or not os.path.isfile(video_path):
            QMessageBox.warning(self, "Transcribe Selected Range", "Please load a video first.")
            return
        pending = getattr(self, "_alternate_ocr_range_pending", None)
        pending_overlay = getattr(self, "ocr_region_overlay", None)
        # A hidden range-OCR editor is not actionable. It can happen after a
        # window switch or an older pending state, and must not bypass the
        # configuration dialog on the next Alt Transcribe click.
        if pending and (pending_overlay is None or not pending_overlay.isVisible()):
            self.log("[Range OCR] Cleared a stale pending OCR region request.")
            self._alternate_ocr_range_pending = None
            pending = None
            self._update_alt_transcribe_button_label()
        if pending:
            config = dict(pending)
            self._alternate_ocr_range_pending = None
            overlay = getattr(self, "ocr_region_overlay", None)
            if overlay is not None:
                overlay.set_editable(False)
                overlay.hide()
            self._update_alt_transcribe_button_label()
        else:
            config = self._show_range_transcription_dialog(selection)
            if config is None:
                return

        start, end = float(config["start"]), float(config["end"])
        engine_name = str(config["engine"])
        mode = str(config["mode"])
        if engine_name == "whisper" and not self.ensure_required_resources("Range Transcription", include_whisper=True):
            return
        if engine_name == "ocr" and not self.ensure_required_resources("Range Transcription", include_ocr=True):
            return
        if engine_name == "ocr" and not pending:
            overlay = getattr(self, "ocr_region_overlay", None)
            if overlay is None:
                QMessageBox.warning(self, "Range OCR", "The OCR region editor is unavailable.")
                return
            self._alternate_ocr_range_pending = dict(config)
            overlay._requested_visible = True
            overlay.set_editable(True)

            def _show_range_ocr_editor():
                view = getattr(overlay, "_target_view", None)
                if view is None:
                    return
                overlay.setGeometry(QRect(view.mapToGlobal(QPoint(0, 0)), view.size()))
                overlay.show()
                overlay.raise_()
                overlay.update()

            _show_range_ocr_editor()
            QTimer.singleShot(0, _show_range_ocr_editor)
            self._update_alt_transcribe_button_label()
            self.log(
                f"[Range OCR] Region editor opened for {start:.3f}s–{end:.3f}s; "
                f"fps={config['ocr_fps'] or 'Settings default'}. Adjust it, then click Run OCR."
            )
            return

        model = str(config.get("whisper_model", "")) if engine_name == "whisper" else ""
        language = str(config.get("language", "auto"))
        ocr_fps = config.get("ocr_fps") if engine_name == "ocr" else None
        ocr_region = str(config.get("ocr_region", "bottom"))
        settings_summary = (
            f"model={model}, language={language}" if engine_name == "whisper"
            else f"region={ocr_region}, fps={ocr_fps or 'Settings default'}"
        )
        self.log(
            f"[Range Transcription] Running {engine_name} for {start:.3f}s–{end:.3f}s "
            f"({mode}; {settings_summary})."
        )
        worker = AlternateRangeTranscriptionWorker(
            video_path, start, end, engine_name, model, language,
            ocr_region=ocr_region, ocr_fps=ocr_fps,
        )
        # Keep the QThread parented and referenced until its native finished
        # signal fires.  Clearing the only reference from the worker's custom
        # result signal could destroy the QThread while run() was unwinding.
        worker.setParent(self)
        self._alternate_range_transcription_worker = worker
        action_button = getattr(self, "timeline_alt_transcribe_btn", None)
        if action_button is not None:
            action_button.setEnabled(False)
            action_button.setText("Running…")
        def finished(segments, error):
            if action_button is not None:
                action_button.setEnabled(True)
                self._update_alt_transcribe_button_label()
            if error:
                QMessageBox.warning(self, "Transcribe Selected Range", f"{engine_name.title()} failed.\n\n{error}")
                return
            if not segments:
                QMessageBox.information(
                    self, "Transcribe Selected Range",
                    "No subtitle text was detected in this range. Existing subtitle segments were not changed.",
                )
                return
            self._apply_alternate_range_transcript(segments, start, end, mode)
        def cleanup_worker():
            if getattr(self, "_alternate_range_transcription_worker", None) is worker:
                self._alternate_range_transcription_worker = None
            # finished() runs while the worker reference is still retained,
            # so its label refresh intentionally does nothing. Refresh once
            # the native QThread has actually finished and been released.
            self._update_alt_transcribe_button_label()
            worker.deleteLater()
        worker.completed.connect(finished)
        worker.finished.connect(cleanup_worker)
        worker.start()

    def _show_range_transcription_dialog(self, selection):
        """Collect recognition options without changing the project's main source."""
        start, end = (float(selection[0]), float(selection[1]))
        overlaps = any(
            float(seg.get("end", 0.0)) > start and float(seg.get("start", 0.0)) < end
            for seg in list(self.current_segments or [])
        )
        dialog = QDialog(self)
        dialog.setWindowTitle("Transcribe Selected Range")
        dialog.setMinimumWidth(420)
        dialog.setStyleSheet(
            "QDialog { background: #101b2d; color: #e6eef9; } "
            "QLabel { color: #d7e4f5; } QComboBox { min-height: 28px; }"
        )
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)
        layout.addWidget(QLabel(f"Range: {start:.3f}s – {end:.3f}s", dialog))

        engine_label = QLabel("Engine", dialog)
        engine_combo = QComboBox(dialog)
        engine_combo.addItem("Whisper", "whisper")
        engine_combo.addItem("OCR", "ocr")
        default_engine = self._alternate_transcription_engine()
        engine_index = engine_combo.findData(default_engine)
        engine_combo.setCurrentIndex(engine_index if engine_index >= 0 else 0)
        layout.addWidget(engine_label)
        layout.addWidget(engine_combo)

        mode_label = QLabel("Existing subtitle segments", dialog)
        mode_combo = QComboBox(dialog)
        mode_combo.addItem("Replace overlapping segments (recommended)", "replace")
        mode_combo.addItem("Append new segments", "append")
        mode_combo.setCurrentIndex(0 if overlaps else 1)
        layout.addWidget(mode_label)
        layout.addWidget(mode_combo)

        whisper_box = QWidget(dialog)
        whisper_layout = QVBoxLayout(whisper_box)
        whisper_layout.setContentsMargins(0, 0, 0, 0)
        whisper_layout.setSpacing(6)
        whisper_layout.addWidget(QLabel("Whisper model", whisper_box))
        whisper_model_combo = QComboBox(whisper_box)
        whisper_model_combo.addItem("Base", "base")
        whisper_model_combo.addItem("Small (Fast)", "small")
        if os.environ.get("VIUSTUDIO_DEVICE", "cuda").strip().lower() == "cuda":
            whisper_model_combo.addItem("Medium (Quality)", "medium")
        current_model = str(self.get_whisper_model_name() or "small").strip().lower()
        model_index = whisper_model_combo.findData(current_model)
        whisper_model_combo.setCurrentIndex(model_index if model_index >= 0 else 0)
        whisper_layout.addWidget(whisper_model_combo)
        whisper_layout.addWidget(QLabel("Language", whisper_box))
        language_combo = QComboBox(whisper_box)
        source_language = str(self.get_source_language_code() or "auto")
        language_combo.addItem(f"Project language ({source_language})", source_language)
        if source_language != "auto":
            language_combo.addItem("Auto detect", "auto")
        for label, code in (("Chinese", "zh"), ("English", "en"), ("Vietnamese", "vi"), ("Japanese", "ja"), ("Korean", "ko")):
            if code != source_language:
                language_combo.addItem(label, code)
        whisper_layout.addWidget(language_combo)
        layout.addWidget(whisper_box)

        ocr_box = QWidget(dialog)
        ocr_layout = QVBoxLayout(ocr_box)
        ocr_layout.setContentsMargins(0, 0, 0, 0)
        ocr_layout.setSpacing(6)
        ocr_layout.addWidget(QLabel("OCR sampling rate", ocr_box))
        ocr_fps_combo = QComboBox(ocr_box)
        ocr_fps_combo.addItem("Use Settings default", "settings")
        ocr_fps_combo.addItem("1 FPS (lighter)", "1")
        ocr_fps_combo.addItem("1.5 FPS", "1.5")
        ocr_fps_combo.addItem("2 FPS", "2")
        ocr_fps_combo.addItem("3 FPS", "3")
        ocr_fps_combo.addItem("4 FPS (short flashes)", "4")
        current_fps = str(os.getenv("OCR_SAMPLING_FPS") or "auto").strip().lower()
        fps_index = ocr_fps_combo.findData(current_fps)
        ocr_fps_combo.setCurrentIndex(fps_index if fps_index >= 0 else 0)
        ocr_layout.addWidget(ocr_fps_combo)
        ocr_hint = QLabel("After continuing, adjust the current OCR region on the preview, then click Run OCR.", ocr_box)
        ocr_hint.setWordWrap(True)
        ocr_hint.setObjectName("helperLabel")
        ocr_layout.addWidget(ocr_hint)
        layout.addWidget(ocr_box)

        def update_engine_options():
            is_whisper = engine_combo.currentData() == "whisper"
            whisper_box.setVisible(is_whisper)
            ocr_box.setVisible(not is_whisper)
            dialog.adjustSize()

        engine_combo.currentIndexChanged.connect(update_engine_options)
        update_engine_options()

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton("Cancel", dialog)
        run_button = QPushButton("Continue", dialog)
        buttons.addWidget(cancel_button)
        buttons.addWidget(run_button)
        layout.addLayout(buttons)
        cancel_button.clicked.connect(dialog.reject)
        run_button.clicked.connect(dialog.accept)
        if dialog.exec() != QDialog.Accepted:
            return None

        engine_name = str(engine_combo.currentData() or "whisper")
        fps_value = str(ocr_fps_combo.currentData() or "settings")
        return {
            "start": start,
            "end": end,
            "engine": engine_name,
            "mode": str(mode_combo.currentData() or "replace"),
            "whisper_model": str(whisper_model_combo.currentData() or "small"),
            "language": str(language_combo.currentData() or "auto"),
            "ocr_region": str(os.getenv("OCR_SUBTITLE_REGION") or "bottom").strip().lower(),
            "ocr_fps": None if fps_value == "settings" else float(fps_value),
        }

    def _apply_alternate_range_transcript(self, segments, start, end, mode):
        fresh = [
            {"start": max(float(start), float(seg.get("start", start))), "end": min(float(end), float(seg.get("end", end))), "text": str(seg.get("text", "")).strip()}
            for seg in list(segments or []) if str(seg.get("text", "")).strip()
        ]
        if mode == "replace":
            self.current_segments = self._replace_subtitle_segments_in_range(
                self.current_segments, fresh, start, end,
            )
            if self.current_translated_segments:
                self.current_translated_segments = self._replace_subtitle_segments_in_range(
                    self.current_translated_segments, [dict(seg) for seg in fresh], start, end,
                )
        else:
            self.current_segments = sorted(self.current_segments + fresh, key=lambda seg: float(seg.get("start", 0.0)))
            if self.current_translated_segments:
                self.current_translated_segments = sorted(
                    self.current_translated_segments + [dict(seg) for seg in fresh],
                    key=lambda seg: float(seg.get("start", 0.0)),
                )
        self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._sync_hidden_transcript_text_from_segments()
        self._sync_hidden_translated_text_from_segments()
        self._commit_subtitle_mutation()
        self.log(f"[Range Transcription] Added {len(fresh)} alternate-engine segment(s).")

    @staticmethod
    def _replace_subtitle_segments_in_range(existing, replacement, start, end):
        """Replace only the selected interval, retaining cue portions outside it."""
        retained = []
        for source in list(existing or []):
            segment = dict(source)
            segment_start = float(segment.get("start", 0.0))
            segment_end = float(segment.get("end", 0.0))
            overlaps = segment_end > start and segment_start < end
            if not overlaps:
                retained.append(segment)
                continue
            # A cue can cross either selection boundary. Keep the unaffected
            # temporal portion instead of deleting the entire cue.
            if segment_start < start:
                before = dict(segment)
                before["end"] = float(start)
                if float(before["end"]) > float(before["start"]):
                    retained.append(before)
            if segment_end > end:
                after = dict(segment)
                after["start"] = float(end)
                if float(after["end"]) > float(after["start"]):
                    retained.append(after)
        return sorted(retained + [dict(item) for item in list(replacement or [])], key=lambda seg: float(seg.get("start", 0.0)))

    def _split_selected_subtitle_by_range(self, range_start: float, range_end: float) -> bool:
        """Split only the selected TS1 cue at the selection boundaries."""
        selected_id = str(getattr(getattr(self, "timeline", None), "_selected_layer_id", "") or "")
        if selected_id:
            for track in self.timeline._timeline.tracks:
                if any(layer.id == selected_id for layer in track.layers) and bool(getattr(track, "locked", False)):
                    QMessageBox.information(self, "Layer Locked", "Unlock this timeline layer before splitting it.")
                    return True
        index = int(getattr(self, "_selected_segment_index", -1))
        if not (0 <= index < len(self.get_active_segments() or [])):
            QMessageBox.information(self, "Split by Selection", "Select a subtitle segment before splitting it.")
            return True
        boundaries = (float(range_start), float(range_end))
        history = {"type": "range_split", "current_before": copy.deepcopy(self.current_segments), "translated_before": copy.deepcopy(self.current_translated_segments)}
        changed = False
        for attr, translated in (("current_segments", False), ("current_translated_segments", True)):
            source = list(getattr(self, attr, []) or [])
            if not (0 <= index < len(source)):
                continue
            rebuilt = list(source)
            pieces = [source[index]]
            for boundary in boundaries:
                next_pieces = []
                for piece in pieces:
                    start = float(piece.get("start", 0.0)); end = float(piece.get("end", 0.0))
                    if start + 0.01 < boundary < end - 0.01:
                        first, second = self._build_split_segment_pair(piece, boundary)
                        next_pieces.extend((first, second)); changed = True
                    else:
                        next_pieces.append(piece)
                pieces = next_pieces
            if changed:
                rebuilt[index:index + 1] = pieces
                setattr(self, attr, rebuilt)
                if translated:
                    self.current_translated_segment_models = self._dict_segments_to_models(rebuilt, translated=True)
                    self._sync_hidden_translated_text_from_segments()
                else:
                    self.current_segment_models = self._dict_segments_to_models(rebuilt, translated=False)
                    self._sync_hidden_transcript_text_from_segments()
        if not changed:
            QMessageBox.information(self, "Split by Selection", "No subtitle segment crosses the selection boundaries.")
            return False
        history["current_after"] = copy.deepcopy(self.current_segments)
        history["translated_after"] = copy.deepcopy(self.current_translated_segments)
        self._timeline_timing_undo_stack.append(history)
        self._timeline_timing_redo_stack = []
        self._refresh_timeline_history_buttons()
        self._commit_subtitle_mutation()
        self.log(f"[Timeline] Split subtitle segments at selection {range_start:.3f}s–{range_end:.3f}s.")
        return True

    def _split_selected_overlay_layer(self, selection=None) -> bool:
        """Split a selected Blur, Logo, Mask, or Text layer at the playhead."""
        timeline = getattr(self, "timeline", None)
        if timeline is None or not getattr(timeline, "_timeline", None):
            return False
        selected_id = str(getattr(timeline, "_selected_layer_id", "") or "")
        if not selected_id:
            return False
        selected_track = selected_layer = None
        for track in timeline._timeline.tracks:
            for layer in track.layers:
                if layer.id == selected_id:
                    selected_track, selected_layer = track, layer
                    break
            if selected_layer is not None:
                break
        if selected_layer is None:
            return False
        if bool(getattr(selected_track, "locked", False)):
            QMessageBox.information(self, "Layer Locked", "Unlock this timeline layer before splitting it.")
            return True
        if bool(getattr(selected_layer, "locked", False)):
            QMessageBox.information(self, "Layer Locked", "Unlock this layer before splitting it.")
            return True
        layer_type = str(getattr(getattr(selected_layer, "type", ""), "value", getattr(selected_layer, "type", ""))).lower()
        if layer_type == "video":
            split_time = self.timeline_position_seconds() if hasattr(self, "timeline_position_seconds") else float(self.media_player.position()) / 1000.0
            if selection:
                candidates = [float(value) for value in selection]
                split_time = next(
                    (value for value in candidates if selected_layer.start < value < selected_layer.end),
                    split_time,
                )
            start, end = float(selected_layer.start), float(selected_layer.end)
            min_duration = max(0.1, float(getattr(timeline, "MIN_DUR", 0.1)))
            if not (start + min_duration < split_time < end - min_duration):
                QMessageBox.information(self, "Split Video", "Place the playhead inside the selected video before splitting.")
                return True
            first = copy.deepcopy(selected_layer)
            second = copy.deepcopy(selected_layer)
            second.id = uuid4().hex[:12]
            first.end = split_time
            second.start = split_time
            second.source_start = float(selected_layer.source_start) + (split_time - start) * max(0.01, float(selected_layer.speed))
            second.name = f"{selected_layer.name} (part 2)"
            index = selected_track.layers.index(selected_layer)
            selected_track.layers[index:index + 1] = [first, second]
            from app.services.timeline_video_sequence import normalize_v1_sequence
            normalize_v1_sequence(timeline._timeline, selected_track.layers)
            timeline._selected_layer_id = second.id
            timeline.set_duration(int(timeline._timeline.duration * 1000))
            timeline._redraw()
            self.refresh_source_video_list()
            self.persist_current_timeline_project_data()
            return True
        is_logo = layer_type == "image" and str(getattr(selected_track, "name", "")) == "L1 Logo"
        if layer_type not in {"blur", "mask", "text"} and not is_logo:
            return False
        current_time = self.timeline_position_seconds() if hasattr(self, "timeline_position_seconds") else float(self.media_player.position()) / 1000.0
        split_times = list(selection or (current_time,))
        start, end = float(selected_layer.start), float(selected_layer.end)
        min_duration = max(0.1, float(getattr(timeline, "MIN_DUR", 0.1)))
        split_times = sorted({float(t) for t in split_times if start + min_duration < float(t) < end - min_duration})
        if not split_times:
            QMessageBox.information(
                self,
                "Split Layer",
                "Place the playhead or selection boundary inside the selected layer before splitting.",
            )
            return True
        index = selected_track.layers.index(selected_layer)
        before_layers = copy.deepcopy(selected_track.layers)
        pieces = []
        piece_start = start
        for part_index, split_time in enumerate(split_times + [end]):
            piece = copy.deepcopy(selected_layer)
            piece.id = selected_layer.id if part_index == 0 else uuid4().hex[:12]
            piece.name = str(getattr(selected_layer, "name", "Layer") or "Layer") if part_index == 0 else f"{str(getattr(selected_layer, 'name', 'Layer') or 'Layer')} {part_index + 1}"
            piece.start, piece.end = piece_start, split_time
            piece_start = split_time
            pieces.append(piece)
        selected_track.layers[index:index + 1] = pieces
        new_layer = pieces[-1]
        timeline._selected_layer_id = new_layer.id
        self._timeline_timing_undo_stack.append({"type": "overlay_split", "track_id": selected_track.id, "before_layers": before_layers, "after_layers": copy.deepcopy(selected_track.layers)})
        self._timeline_timing_redo_stack = []
        self._refresh_timeline_history_buttons()
        timeline._redraw()
        self.persist_current_timeline_project_data()
        self.on_timeline_layer_selected(new_layer.id)
        self.refresh_ui_state()
        return True

    def populate_timeline_layers_menu(self):
        """Build the Layers menu without touching project/preview visibility."""
        menu = getattr(self, "timeline_layers_menu", None)
        timeline = getattr(self, "timeline", None)
        if menu is None:
            return
        menu.clear()
        if timeline is None or not timeline._timeline:
            empty = menu.addAction("No layers")
            empty.setEnabled(False)
            return
        has_tracks = False
        for track in timeline._timeline.tracks:
            # Do not show empty/default tracks. The menu reflects only
            # tracks that currently contain project layers.
            if not track.layers:
                continue
            has_tracks = True
            action = menu.addAction(str(track.name or "Layer Track"))
            action.setCheckable(True)
            action.setChecked(timeline.is_track_shown_on_timeline(track))
            action.setToolTip("Only changes whether this entire track is displayed on the timeline.")
            action.toggled.connect(
                lambda shown, track_id=track.id: timeline.set_track_shown_on_timeline(track_id, shown)
            )
        if not has_tracks:
            empty = menu.addAction("No layer tracks")
            empty.setEnabled(False)

    def on_timeline_track_lock_toggled(self, track_name: str, locked: bool):
        timeline = getattr(self, "timeline", None)
        if timeline is None or not timeline._timeline:
            return
        for track in timeline._timeline.tracks:
            if track.name == track_name:
                track.locked = bool(locked)
                timeline._redraw()
                self.persist_current_timeline_project_data()
                self.refresh_ui_state()
                self.log(f"[Timeline] {'Locked' if locked else 'Unlocked'} track: {track.name}")
                return

    def toggle_selected_timeline_layer_lock(self, layer_id: str = ""):
        timeline = getattr(self, "timeline", None)
        selected_id = str(layer_id or getattr(timeline, "_selected_layer_id", "") or "") if timeline else ""
        if not timeline or not timeline._timeline or not selected_id:
            return
        for track in timeline._timeline.tracks:
            for layer in track.layers:
                if layer.id == selected_id:
                    layer.locked = not bool(getattr(layer, "locked", False))
                    timeline._redraw()
                    self.persist_current_timeline_project_data()
                    self.log(f"[Timeline] {'Locked' if layer.locked else 'Unlocked'} layer: {layer.name or layer.id}")
                    return

    def clear_timeline_track(self, track_name: str):
        if self._preview_is_playing():
            return
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
            
        target_track = None
        for track in self.timeline._timeline.tracks:
            if track.name == track_name:
                target_track = track
                break
                
        if target_track is None:
            return
            
        if bool(getattr(target_track, "locked", False)):
            QMessageBox.information(self, "Track Locked", f"Unlock the track '{track_name}' before clearing it.")
            return

        reply = QMessageBox.question(
            self, "Confirm",
            f"Are you sure you want to delete all layers in track '{track_name}'?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Clear track in backend
        target_track.layers.clear()
        
        # If it's a subtitle track, we also need to clear the canonical subtitle segments
        is_subtitle_track = (
            str(getattr(getattr(target_track, "type", ""), "value", getattr(target_track, "type", ""))).lower()
            in {"dub_subtitle", "subtitle"}
        )
        if is_subtitle_track:
            if hasattr(self, "current_segments"):
                self.current_segments = []
            if hasattr(self, "current_translated_segments"):
                self.current_translated_segments = []
            self.current_segment_models = []
            self.current_translated_segment_models = []
            self._single_line_split_cache = None
            self._selected_segment_index = -1
            if hasattr(self, "subtitle_list_model"):
                self.subtitle_list_model.layoutChanged.emit()
            if hasattr(self, "transcript_text"):
                self.transcript_text.clear()
            if hasattr(self, "translated_text"):
                self.translated_text.clear()
            self._invalidate_dubbed_output_after_subtitle_edit()
            self.last_original_srt_path = ""
            self.last_translated_srt_path = ""
            for key in ("srt_original", "srt_translated"):
                self.processed_artifacts.pop(key, None)

        # Update UI
        self.timeline._selected_layer_id = ""
        self.timeline._redraw()
        
        if is_subtitle_track:
            if hasattr(self, "sync_live_subtitle_preview"):
                self.sync_live_subtitle_preview()
            if hasattr(self, "_update_time_label"):
                self._update_time_label()
        else:
            if hasattr(self, "build_filtergraph_and_play"):
                self.build_filtergraph_and_play(float(self.video_view.position) if hasattr(self, "video_view") else 0.0)
            
        if is_subtitle_track:
            state = self.ensure_current_project()
            if state is not None:
                self.current_segment_models = self.project_bridge.persist_transcription(
                    state,
                    [],
                    "",
                )
                self.current_translated_segment_models = self.project_bridge.persist_translation(
                    state,
                    [],
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
        self.persist_current_timeline_project_data()
        self.refresh_ui_state()
        self.log(f"[Timeline] Cleared track: {track_name}")

    def delete_selected_timeline_segment(self):
        if self._preview_is_playing():
            return
        # If a layer is currently selected in the timeline, remove it
        # from its track. Handles blur (with overlay sync), image/logo,
        # text, and any other layer type.
        if hasattr(self, "timeline") and self.timeline._timeline:
            selected_id = str(getattr(self.timeline, "_selected_layer_id", "") or "")
            if selected_id:
                for track in self.timeline._timeline.tracks:
                    layer = None
                    layer_idx = -1
                    for li, l in enumerate(track.layers):
                        if l.id == selected_id:
                            layer = l
                            layer_idx = li
                            break
                    if layer is None:
                        continue
                    if bool(getattr(track, "locked", False)):
                        QMessageBox.information(self, "Layer Locked", "Unlock this timeline layer before deleting it.")
                        return
                    if bool(getattr(layer, "locked", False)):
                        QMessageBox.information(self, "Layer Locked", "Unlock this layer before deleting it.")
                        return
                    layer_type = str(
                        getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))
                    ).lower()
                    # TS1 is a projection of the canonical subtitle lists.
                    # Removing only its visual DubSubtitleLayer leaves the
                    # source segment intact; a later resize calls
                    # apply_segments_to_timeline() and recreates that "deleted"
                    # cue. Route it through the canonical segment deletion
                    # branch below instead.
                    is_subtitle_layer = (
                        layer_type == "dub_subtitle"
                        or str(getattr(getattr(track, "type", ""), "value", getattr(track, "type", ""))).lower() == "dub_subtitle"
                    )
                    if is_subtitle_layer:
                        if bool(getattr(track, "locked", False)) or bool(getattr(layer, "locked", False)):
                            QMessageBox.information(self, "Layer Locked", "Unlock this timeline layer before deleting it.")
                            return
                        segment_index = int(getattr(self.timeline, "_segment_indices", {}).get(layer.id, -1))
                        if segment_index < 0 and isinstance(getattr(layer, "metadata", None), dict):
                            try:
                                segment_index = int(layer.metadata.get("_seg_index", -1))
                            except (TypeError, ValueError):
                                segment_index = -1
                        if segment_index < 0:
                            QMessageBox.warning(self, "Delete Segment", "Could not identify the selected subtitle segment.")
                            return
                        # Carry the selected layer's timing/text into the
                        # canonical deletion path.  Segment indices can be
                        # renumbered after an insertion/deletion, so relying
                        # on a stale index can remove the adjacent cue.
                        self._pending_delete_segment_key = (
                            round(float(getattr(layer, "start", 0.0) or 0.0), 6),
                            round(float(getattr(layer, "end", 0.0) or 0.0), 6),
                            str(getattr(layer, "text", "") or ""),
                        )
                        self.timeline._selected_layer_id = ""
                        self._selected_segment_index = segment_index
                        return self.delete_selected_timeline_segment()
                    if layer_type == "video":
                        from app.services.timeline_video_sequence import ordered_video_layers, remove_video
                        if len(ordered_video_layers(self.timeline._timeline)) <= 1:
                            QMessageBox.information(self, "Delete Video", "A project must keep at least one video on V1.")
                            return
                        remove_video(self.timeline._timeline, layer.id)
                        self.timeline._selected_layer_id = ""
                        self.timeline.set_duration(int(self.timeline._timeline.duration * 1000))
                        self.timeline._redraw()
                        if hasattr(self, "_sync_canonical_source_after_change"):
                            self._sync_canonical_source_after_change()
                        if hasattr(self, "_invalidate_artifacts_after_timeline_change"):
                            self._invalidate_artifacts_after_timeline_change()
                        self.refresh_source_video_list()
                        self.persist_current_timeline_project_data()
                        return
                    # Use the layer-specific removal paths where they own
                    # preview state.  The Delete timeline button therefore
                    # removes the selected layer rather than merely deleting
                    # a timeline bar and leaving a stale overlay behind.
                    if layer_type == "image" and str(getattr(track, "name", "")) == "L1 Logo":
                        self._delete_logo_layer(layer)
                        return
                    if layer_type == "mask" or str(getattr(track, "name", "")) == "M1":
                        self._delete_mask_layer(layer)
                        return
                    # Blur: pop the corresponding overlay region first
                    if layer_type == "blur":
                        try:
                            overlay = getattr(self.video_view, "blur_overlay", None)
                            # A split BlurLayer can share one preview region
                            # with its sibling pieces. Only remove by index
                            # when preview regions and timeline layers are
                            # still one-to-one; otherwise deleting one split
                            # piece would remove the surviving blur region.
                            if (
                                overlay is not None
                                and len(overlay._regions) == len(track.layers)
                                and 0 <= layer_idx < len(overlay._regions)
                            ):
                                overlay._regions.pop(layer_idx)
                                overlay._active_index = min(
                                    layer_idx, len(overlay._regions) - 1
                                )
                                overlay.update()
                                if hasattr(overlay, "sync_to_view"):
                                    overlay.sync_to_view()
                        except Exception:
                            pass
                    # Remove the layer from the track
                    try:
                        if layer in track.layers:
                            track.layers.remove(layer)
                    except ValueError:
                        pass
                    # If the track is now empty, remove it (B1, L1, etc.)
                    if not track.layers:
                        try:
                            self.timeline._timeline.tracks.remove(track)
                        except ValueError:
                            pass
                        if hasattr(self.timeline, "_track_heights") and track.id in self.timeline._track_heights:
                            del self.timeline._track_heights[track.id]
                    # Sync blur overlay if needed
                    if layer_type == "blur":
                        try:
                            regions = self._current_blur_regions_payload() if hasattr(self, "_current_blur_regions_payload") else []
                            if hasattr(self.video_view, "set_blur_regions_normalized"):
                                self.video_view.set_blur_regions_normalized(regions)
                            if hasattr(self.timeline, "sync_blur_regions"):
                                self.timeline.sync_blur_regions(regions)
                            if hasattr(self, "apply_preview_blur_region"):
                                self.apply_preview_blur_region(force=True)
                            if hasattr(self, "persist_project_blur_state"):
                                self.persist_project_blur_state()
                        except Exception:
                            pass
                    # Clear selection and redraw
                    try:
                        self.timeline._selected_layer_id = ""
                    except Exception:
                        pass
                    if hasattr(self.timeline, "_redraw"):
                        self.timeline._redraw()
                    if hasattr(self.timeline, "viewport"):
                        self.timeline.viewport().update()
                    # Show default inspector
                    if hasattr(self, "_show_default_inspector"):
                        self._show_default_inspector()
                    # Keep remaining Logo / Mask layers visible. Clearing
                    # the whole overlay here used to hide every surviving
                    # layer until the user clicked one in the timeline.
                    if str(getattr(track, "name", "")) == "L1 Logo":
                        if track.layers:
                            next_layer = track.layers[min(layer_idx, len(track.layers) - 1)]
                            self.timeline._selected_layer_id = next_layer.id
                            self._show_logo_overlay(track, next_layer)
                        elif hasattr(self, "video_view") and hasattr(self.video_view, "clear_logo"):
                            self.video_view.clear_logo()
                    if str(getattr(track, "name", "")) == "M1":
                        if not track.layers and hasattr(self, "video_view") and hasattr(self.video_view, "clear_mask_region"):
                            self.video_view.clear_mask_region()
                        try:
                            if hasattr(self, "_apply_mask_to_preview"):
                                self._apply_mask_to_preview()
                        except Exception:
                            pass
                        try:
                            if hasattr(self, "persist_project_mask_state"):
                                self.persist_project_mask_state()
                        except Exception:
                            pass
                    if layer_type == "blur":
                        # Do not auto-select a surviving B1 layer. Leave the
                        # editor focused on V1 so the remaining effect is
                        # visible but not implicitly put into edit mode.
                        self._clear_effect_selection_after_delete()
                    if layer_type == "text":
                        # The preview overlay owns a list of all text layers;
                        # refresh it after deletion so only the selected
                        # layer is removed and surviving text stays visible.
                        self._refresh_text_layer_preview("")
                    try:
                        self.persist_current_timeline_project_data()
                    except Exception:
                        pass
                    return
        segments = list(self.get_active_segments() or [])
        if not segments:
            return
        index = int(getattr(self, "_selected_segment_index", -1))
        pending_key = getattr(self, "_pending_delete_segment_key", None)
        if pending_key:
            target_start, target_end, target_text = pending_key
            matching = [
                idx for idx, segment in enumerate(segments)
                if abs(float(segment.get("start", 0.0) or 0.0) - target_start) < 0.01
                and abs(float(segment.get("end", 0.0) or 0.0) - target_end) < 0.01
                and (not target_text or str(segment.get("text", "") or "") == target_text)
            ]
            if not matching:
                matching = [
                    idx for idx, segment in enumerate(segments)
                    if abs(float(segment.get("start", 0.0) or 0.0) - target_start) < 0.01
                    and abs(float(segment.get("end", 0.0) or 0.0) - target_end) < 0.01
                ]
            if matching:
                index = matching[0]
        if not (0 <= index < len(segments)):
            index = self._find_active_segment_index(self.media_player.position(), segments)
        if not (0 <= index < len(segments)):
            QMessageBox.information(self, "Delete Segment", "Please select an audio/subtitle block first.")
            return

        remaining_count = max(0, len(segments) - 1)
        target_selection = min(index, max(0, remaining_count - 1)) if remaining_count else -1
        delete_history_entry = {
            "type": "delete",
            "index": int(index),
            "selected_before": int(index),
            "selected_after": int(target_selection),
            "current_before": [],
            "current_after": [],
            "translated_before": [],
            "translated_after": [],
        }

        def _matching_index(items):
            if not pending_key:
                return index if 0 <= index < len(items) else -1
            target_start, target_end, target_text = pending_key
            for item_index, segment in enumerate(items):
                if abs(float(segment.get("start", 0.0) or 0.0) - target_start) < 0.01 \
                        and abs(float(segment.get("end", 0.0) or 0.0) - target_end) < 0.01 \
                        and (not target_text or str(segment.get("text", "") or "") == target_text):
                    return item_index
            for item_index, segment in enumerate(items):
                if abs(float(segment.get("start", 0.0) or 0.0) - target_start) < 0.01 \
                        and abs(float(segment.get("end", 0.0) or 0.0) - target_end) < 0.01:
                    return item_index
            return index if 0 <= index < len(items) else -1

        current_index = _matching_index(self.current_segments or [])
        if 0 <= current_index < len(self.current_segments or []):
            delete_history_entry["current_before"] = [copy.deepcopy(self.current_segments[current_index])]
            self.current_segments[current_index:current_index + 1] = []
            self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
            self._sync_hidden_transcript_text_from_segments()

        translated_index = _matching_index(self.current_translated_segments or [])
        if 0 <= translated_index < len(self.current_translated_segments or []):
            delete_history_entry["translated_before"] = [copy.deepcopy(self.current_translated_segments[translated_index])]
            self.current_translated_segments[translated_index:translated_index + 1] = []
            self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
            self._sync_hidden_translated_text_from_segments()

        # The optional one-line display cache is indexed against the old
        # subtitle list. It must never survive a deletion, otherwise a later
        # timing edit can redraw a stale cue from that cache.
        self._single_line_split_cache = None
        self._pending_delete_segment_key = None

        self._timeline_timing_undo_stack.append(delete_history_entry)
        self._timeline_timing_redo_stack = []
        if len(self._timeline_timing_undo_stack) > 100:
            self._timeline_timing_undo_stack = self._timeline_timing_undo_stack[-100:]
        self._refresh_timeline_history_buttons()

        self.set_selected_segment_index(target_selection, sync_ui=True)
        if hasattr(self, "timeline"):
            self.timeline.set_active_segment_index(target_selection)
        self._commit_subtitle_mutation(selected_index=target_selection)

    def on_timeline_segment_timing_changed(self, index: int, start: float, end: float):
        # A selection click used to reach this handler with the cue's existing
        # timestamps.  Treat an identical update as a no-op so it can never
        # invalidate an already-generated TTS track, even if another timeline
        # input path emits a redundant timing signal in the future.
        timing_targets = []
        for segments in (self.current_segments or [], self.current_translated_segments or []):
            if 0 <= index < len(segments):
                timing_targets.append(segments[index])
        if timing_targets and all(
            abs(float(segment.get("start", 0.0) or 0.0) - float(start)) <= 0.0001
            and abs(float(segment.get("end", 0.0) or 0.0) - float(end)) <= 0.0001
            for segment in timing_targets
        ):
            return
        updated = False
        if 0 <= index < len(self.current_segments or []):
            self._apply_segment_timing(self.current_segments[index], start, end)
            self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
            self._sync_hidden_transcript_text_from_segments()
            updated = True
        if 0 <= index < len(self.current_translated_segments or []):
            self._apply_segment_timing(self.current_translated_segments[index], start, end)
            self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
            self._sync_hidden_translated_text_from_segments()
            updated = True
        if not updated:
            return
        # Timing changes invalidate the optional derived one-line display
        # list. Otherwise it can retain deleted cues and overwrite the fresh
        # canonical subtitle state on the next redraw.
        self._single_line_split_cache = None
        # Rebuilding TS1 can briefly select the first cue. The shared commit
        # path restores the edited selection after rebuilding the track.
        self._commit_subtitle_mutation(selected_index=index)

    def _refresh_timeline_history_buttons(self):
        if hasattr(self, "timeline_undo_btn"):
            self.timeline_undo_btn.setEnabled(bool(self._timeline_timing_undo_stack))
        if hasattr(self, "timeline_redo_btn"):
            self.timeline_redo_btn.setEnabled(bool(self._timeline_timing_redo_stack))

    def undo_last_timeline_timing_edit(self):
        if self._preview_is_playing():
            return False
        if not self._timeline_timing_undo_stack:
            return False
        entry = self._timeline_timing_undo_stack.pop()
        if str(entry.get("type", "")) == "range_split":
            self._apply_range_split_history(entry, use_after=False)
            self._timeline_timing_redo_stack.append(entry)
            self._refresh_timeline_history_buttons()
            return True
        if str(entry.get("type", "")) == "overlay_split":
            self._apply_overlay_split_history(entry, use_after=False)
            self._timeline_timing_redo_stack.append(entry)
            self._refresh_timeline_history_buttons()
            return True
        if str(entry.get("type", "timing")) in {"insert", "split", "delete", "batch_timing"}:
            self._apply_timeline_structure_history_entry(entry, use_after=False)
            self._timeline_timing_redo_stack.append(entry)
            self._refresh_timeline_history_buttons()
            return True
        current_entry = None
        active_segments = self.get_active_segments()
        index = int(entry.get("index", -1))
        if 0 <= index < len(active_segments):
            current_entry = {
                "index": index,
                "start": float(active_segments[index].get("start", 0.0)),
                "end": float(active_segments[index].get("end", 0.0)),
            }
        self._suspend_timeline_undo = True
        try:
            self.on_timeline_segment_timing_changed(
                index,
                float(entry.get("start", 0.0)),
                float(entry.get("end", 0.0)),
            )
        finally:
            self._suspend_timeline_undo = False
        if current_entry:
            self._timeline_timing_redo_stack.append(current_entry)
        self._refresh_timeline_history_buttons()
        return True

    def redo_last_timeline_timing_edit(self):
        if self._preview_is_playing():
            return False
        if not self._timeline_timing_redo_stack:
            return False
        entry = self._timeline_timing_redo_stack.pop()
        if str(entry.get("type", "")) == "range_split":
            self._apply_range_split_history(entry, use_after=True)
            self._timeline_timing_undo_stack.append(entry)
            self._refresh_timeline_history_buttons()
            return True
        if str(entry.get("type", "")) == "overlay_split":
            self._apply_overlay_split_history(entry, use_after=True)
            self._timeline_timing_undo_stack.append(entry)
            self._refresh_timeline_history_buttons()
            return True
        if str(entry.get("type", "timing")) in {"insert", "split", "delete", "batch_timing"}:
            self._apply_timeline_structure_history_entry(entry, use_after=True)
            self._timeline_timing_undo_stack.append(entry)
            self._refresh_timeline_history_buttons()
            return True
        current_entry = None
        active_segments = self.get_active_segments()
        index = int(entry.get("index", -1))
        if 0 <= index < len(active_segments):
            current_entry = {
                "index": index,
                "start": float(active_segments[index].get("start", 0.0)),
                "end": float(active_segments[index].get("end", 0.0)),
            }
        self._suspend_timeline_undo = True
        try:
            self.on_timeline_segment_timing_changed(
                index,
                float(entry.get("start", 0.0)),
                float(entry.get("end", 0.0)),
            )
        finally:
            self._suspend_timeline_undo = False
        if current_entry:
            self._timeline_timing_undo_stack.append(current_entry)
        self._refresh_timeline_history_buttons()
        return True

    def _apply_overlay_split_history(self, entry, *, use_after: bool):
        timeline = getattr(self, "timeline", None)
        if timeline is None or not timeline._timeline:
            return
        track_id = str(entry.get("track_id", ""))
        for track in timeline._timeline.tracks:
            if track.id == track_id:
                track.layers = copy.deepcopy(entry.get("after_layers" if use_after else "before_layers", []))
                timeline._selected_layer_id = track.layers[-1].id if track.layers else ""
                timeline._redraw()
                self.persist_current_timeline_project_data()
                self.refresh_ui_state()
                return

    def _apply_range_split_history(self, entry, *, use_after: bool):
        suffix = "after" if use_after else "before"
        self.current_segments = copy.deepcopy(entry.get(f"current_{suffix}", []))
        self.current_translated_segments = copy.deepcopy(entry.get(f"translated_{suffix}", []))
        self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._sync_hidden_transcript_text_from_segments()
        self._sync_hidden_translated_text_from_segments()
        self._commit_subtitle_mutation()

    def step_selected_segment(self, direction: int):
        rows = self._segment_editor_display_rows()
        valid_indexes = [int(row.get("segment_index", idx)) for idx, row in enumerate(rows)]
        if not valid_indexes:
            self.set_selected_segment_index(-1)
            return
        current = self._get_effective_selected_segment_index(rows)
        try:
            current_pos = valid_indexes.index(current)
        except ValueError:
            current_pos = 0
        target_pos = max(0, min(len(valid_indexes) - 1, current_pos + int(direction)))
        self.set_selected_segment_index(valid_indexes[target_pos], sync_ui=True)

    def _find_segment_editor_row(self, segment_index: int):
        for row in getattr(self, "_segment_editor_rows", []):
            if int(row.get("segment_index", -1)) == int(segment_index):
                return row
        return None

    def _is_subtitle_inspector_details_visible(self) -> bool:
        stack = getattr(self, "inspector_stack", None)
        if not stack or stack.currentIndex() != 0:
            return False
        card = getattr(self, "subtitle_inspector_card", None)
        return bool(card and card.isVisible())

    def is_subtitle_inspector_anchored(self) -> bool:
        # Backwards-compatible alias - the anchor now applies to the
        # entire track inspector (subtitle, audio, blur, default).
        return self.is_inspector_anchored()

    def is_inspector_anchored(self) -> bool:
        checkbox = getattr(self, "anchor_inspector_cb", None)
        return bool(checkbox and checkbox.isChecked())

    def _sync_subtitle_inspector_shell_width(self, visible: bool = None):
        """Width of the inspector shell.

        The shell hosts a QStackedWidget that can show a subtitle, audio or
        default card. Width is driven by the `_inspector_collapsed` state:
        - collapsed=True  -> handle only
        - collapsed=False -> wide enough for the widest card

        The `visible` parameter is ignored (kept for API compatibility).
        """
        shell = getattr(self, "subtitle_inspector_shell", None)
        if shell is None:
            return
        # The handle was removed - no extra handle width to add.
        handle_width = 0

        if bool(getattr(self, "_inspector_collapsed", False)):
            target_width = handle_width
        else:
            responsive_width = int(getattr(self, "_responsive_inspector_width", 0) or 0)
            widest = responsive_width if responsive_width > 0 else 400
            for attr in ("subtitle_inspector_card", "audio_inspector_card", "default_inspector_card"):
                card = getattr(self, attr, None)
                if card is None:
                    continue
                try:
                    raw_max = int(card.maximumWidth() or 0)
                    if raw_max > 5000 or raw_max <= 0:
                        raw_max = 0
                    raw_min = int(card.minimumWidth() or 0)
                    if raw_min > 5000 or raw_min < 0:
                        raw_min = 0
                    raw_hint = int(card.sizeHint().width() or 0)
                    candidate = raw_max or raw_hint or raw_min or widest
                    widest = max(widest, candidate)
                except Exception:
                    pass
            if responsive_width > 0:
                widest = max(responsive_width, min(widest, 440))
            else:
                widest = max(400, min(widest, 560))
            target_width = handle_width + widest
        shell.setMinimumWidth(target_width)
        shell.setMaximumWidth(target_width)
        shell.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def _update_subtitle_inspector_summary(self, rows=None):
        rows = rows if rows is not None else self._segment_editor_display_rows()
        count = len(rows or [])
        translation_ready = self._translation_phase_complete()
        if not count:
            self._selected_segment_index = -1
            if hasattr(self, "subtitle_inspector_summary_label"):
                self.subtitle_inspector_summary_label.setText("Selected subtitle: none")
            if hasattr(self, "rewrite_selected_segment_btn"):
                self.rewrite_selected_segment_btn.setEnabled(False)
            return

        selected_index = self._get_effective_selected_segment_index(rows)
        if selected_index < 0 or selected_index >= count:
            selected_index = int(rows[0].get("segment_index", 0))
        self._selected_segment_index = selected_index
        if hasattr(self, "subtitle_inspector_summary_label"):
            self.subtitle_inspector_summary_label.setText(f"Selected subtitle: Block {selected_index + 1} / {count}")
        if hasattr(self, "rewrite_selected_segment_btn"):
            self.rewrite_selected_segment_btn.setEnabled(translation_ready)

    def _translation_phase_complete(self) -> bool:
        """Return whether translated subtitle data is a completed artifact."""
        state = getattr(self, "current_project_state", None)
        steps = getattr(state, "steps", {}) or {}
        status = str(steps.get("translate_raw", "") or "").strip().lower()
        if status in {"running", "failed", "cancelled", "pending"}:
            return False
        segments_ready = bool(getattr(self, "current_translated_segments", None))
        artifacts = getattr(state, "artifacts", {}) or {}
        artifact_path = str(artifacts.get("translation_final", "") or "").strip()
        artifact_ready = bool(artifact_path and os.path.exists(artifact_path))
        if not (segments_ready or artifact_ready):
            return False
        # Legacy projects may have the artifact but no explicit done status.
        return status == "done" or artifact_ready

    def set_subtitle_inspector_details_visible(self, visible: bool, *, sync: bool = True):
        if not visible and self.is_inspector_anchored():
            visible = True
        # The subtitle details widget (segment editor) visibility is
        # independent from the audio/default cards. The shell collapse
        # state is managed via `set_inspector_collapsed` (called from the
        # toggle button handler), not by this function.
        widget = getattr(self, "subtitle_inspector_details_widget", None)
        if widget is not None:
            widget.setVisible(bool(visible))
        toggle_btn = getattr(self, "subtitle_inspector_toggle_btn", None)
        if toggle_btn is not None:
            toggle_btn.blockSignals(True)
            toggle_btn.setChecked(bool(visible))
            if str(toggle_btn.objectName() or "") == "subtitleInspectorHandleBtn":
                toggle_btn.setText("▶" if visible else "◀")
                toggle_btn.setToolTip("Hide subtitle editor" if visible else "Show subtitle editor")
            else:
                toggle_btn.setText("Hide details" if visible else "Show details")
            toggle_btn.blockSignals(False)
        anchor_cb = getattr(self, "anchor_inspector_cb", None)
        if anchor_cb is not None:
            toggle_btn = getattr(self, "subtitle_inspector_toggle_btn", None)
            if toggle_btn is not None:
                toggle_btn.setEnabled(not self.is_inspector_anchored())
        if not visible:
            self._clear_segment_editor_rows()
            self._segment_editor_rows = []
            self._update_subtitle_inspector_summary()
        else:
            self._sync_selected_segment_to_playback_position()
            if sync:
                self.sync_segment_editor_rows()
        # Do NOT change the inspector collapsed state from here; the
        # toggle button drives the collapse. Other callers (e.g. media_utils
        # on Play) just hide the details without collapsing the shell.

    def set_inspector_collapsed(self, collapsed: bool):
        """Collapse or expand the inspector shell. The track layer
        inspector is always expanded - collapse is disabled.
        """
        collapsed = False
        self._inspector_collapsed = False
        # Sync shell width
        try:
            self._sync_subtitle_inspector_shell_width(visible=not bool(collapsed))
        except Exception:
            pass
        # Hide the entire stack so no card content is visible when collapsed
        stack = getattr(self, "inspector_stack", None)
        if stack is not None:
            stack.setVisible(not bool(collapsed))
        # Sync subtitle details widget visibility to match
        widget = getattr(self, "subtitle_inspector_details_widget", None)
        if widget is not None:
            widget.setVisible(not bool(collapsed))
        # Sync toggle button
        toggle_btn = getattr(self, "subtitle_inspector_toggle_btn", None)
        if toggle_btn is not None:
            toggle_btn.blockSignals(True)
            toggle_btn.setChecked(not bool(collapsed))
            toggle_btn.setText("▶" if collapsed else "◀")
            toggle_btn.setToolTip(
                "Show track inspector" if collapsed else "Hide track inspector"
            )
            toggle_btn.blockSignals(False)

    def show_subtitle_inspector_details(self):
        self.set_subtitle_inspector_details_visible(True, sync=True)

    def toggle_subtitle_inspector_details(self, checked: bool):
        # checked=True means "show details" (expand the inspector shell).
        # checked=False means "hide details" (collapse to handle only).
        self.set_inspector_collapsed(not bool(checked))
        # Also update the subtitle details widget visibility (so the
        # segment editor appears/disappears).
        widget = getattr(self, "subtitle_inspector_details_widget", None)
        if widget is not None:
            widget.setVisible(bool(checked))

    def on_anchor_inspector_toggled(self, checked: bool):
        if checked:
            # Anchor means: keep the track inspector shell expanded
            # (whichever card is currently shown: subtitle, audio, blur
            # or default).
            self.set_inspector_collapsed(False)
        toggle_btn = getattr(self, "subtitle_inspector_toggle_btn", None)
        if toggle_btn is not None:
            toggle_btn.setEnabled(not checked)
        self.save_user_settings()

    def _sync_selected_segment_to_playback_position(self, position_ms=None):
        """Select the subtitle cue that contains the current playhead.

        ``media_player.position()`` is asynchronous on some backends.  Seek
        handlers therefore pass the requested position explicitly so the
        Inspector cannot lag one signal behind the Preview.  Callers that do
        not have a requested position keep the historical player-position
        lookup behaviour.
        """
        if not hasattr(self, "media_player"):
            return
        # Use the committed editor data for selection.  The live preview list
        # is refreshed on a debounce timer and may intentionally lag during a
        # subtitle import/edit; using it here would map the playhead to an old
        # cue and show stale Inspector timing.
        segments = self.get_active_segments() or self.live_preview_segments
        if not segments:
            return
        if position_ms is None:
            try:
                position_ms = int(self.media_player.position())
            except Exception:
                return
        else:
            try:
                position_ms = int(position_ms)
            except (TypeError, ValueError):
                return
        active_index = self._find_active_segment_index(position_ms, segments)
        if active_index >= 0:
            current_selected = getattr(self, "_selected_segment_index", -1)
            should_sync_ui = (active_index != current_selected)
            self.set_selected_segment_index(active_index, sync_ui=should_sync_ui)
            if hasattr(self, "timeline"):
                self.timeline.set_active_segment_index(active_index)

    def sync_segment_editor_rows(self):
        if not hasattr(self, "segment_editor_layout") or getattr(self, "_syncing_segment_editor", False):
            return
        if not self._is_subtitle_inspector_details_visible():
            self._update_subtitle_inspector_summary()
            return

        self._syncing_segment_editor = True
        try:
            self._clear_segment_editor_rows()
            self._segment_editor_rows = []
            rows = self._segment_editor_display_rows()
            self._update_subtitle_inspector_summary(rows)
            if not rows:
                empty_state = QFrame(self.segment_editor_container if hasattr(self, "segment_editor_container") else None)
                empty_state.setObjectName("statusCard")
                empty_state.setMinimumHeight(180)
                empty_state.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                empty_state.setStyleSheet(
                    "QFrame#statusCard { background-color: #132132; border: 1px dashed #35506f; border-radius: 16px; }"
                )
                empty_layout = QVBoxLayout(empty_state)
                empty_layout.setContentsMargins(18, 18, 18, 18)
                empty_layout.setSpacing(8)
                empty_layout.addStretch()
                empty_title = QLabel("Subtitle editor is waiting for content")
                empty_title.setObjectName("statusHeadline")
                empty_title.setAlignment(Qt.AlignCenter)
                empty_body = QLabel("Subtitle editor will appear here once transcript or translation is ready.")
                empty_body.setObjectName("helperLabel")
                empty_body.setWordWrap(True)
                empty_body.setAlignment(Qt.AlignCenter)
                empty_layout.addWidget(empty_title)
                empty_layout.addWidget(empty_body)
                empty_layout.addStretch()
                self.segment_editor_layout.addWidget(empty_state, 1)
                return

            selected_index = self._get_effective_selected_segment_index(rows)
            visible_rows = [row for row in rows if int(row.get("segment_index", -1)) == selected_index]
            if not visible_rows:
                visible_rows = [rows[0]]
                selected_index = int(visible_rows[0].get("segment_index", 0))
            self._update_subtitle_inspector_summary(rows)

            show_original = True
            for row in visible_rows:
                idx = int(row.get("segment_index", 0))
                card = QFrame(self.segment_editor_container if hasattr(self, "segment_editor_container") else None)
                # No border on the subtitle display frame - blends into
                # the inspector shell.
                card.setFrameShape(QFrame.NoFrame)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(4, 4, 4, 4)
                card_layout.setSpacing(6)

                # Start/End timing chips with duration
                timing_meta_layout = QHBoxLayout()
                timing_meta_layout.setContentsMargins(0, 0, 0, 0)
                timing_meta_layout.setSpacing(6)
                start_label = QLabel(f"Start  {self.format_timestamp(row['start'])}")
                start_label.setObjectName("timingChip")
                start_label.setFixedHeight(24)
                end_label = QLabel(f"End  {self.format_timestamp(row['end'])}")
                end_label.setObjectName("timingChip")
                end_label.setFixedHeight(24)
                duration_sec = max(0.0, float(row.get('end', 0) or 0) - float(row.get('start', 0) or 0))
                dur_label = QLabel(f"{duration_sec:.2f}s")
                dur_label.setObjectName("durationChip")
                dur_label.setFixedHeight(24)
                dur_label.setToolTip("Duration of this subtitle cue")
                timing_meta_layout.addWidget(start_label)
                timing_meta_layout.addWidget(end_label)
                timing_meta_layout.addWidget(dur_label)
                timing_meta_layout.addStretch()
                card_layout.addLayout(timing_meta_layout)

                # Speaker & Voice Speed row (unified properties bar)
                props_row = QHBoxLayout()
                props_row.setContentsMargins(0, 0, 0, 0)
                props_row.setSpacing(8)

                speaker_ids = self._detected_speaker_ids()
                segment_source = self.current_translated_segments or self.current_segments or []
                selected_speaker = ""
                if 0 <= idx < len(segment_source):
                    selected_speaker = str(segment_source[idx].get("speaker", "") or "").strip()

                speaker_label = QLabel("Speaker:")
                speaker_label.setObjectName("helperLabel")
                speaker_combo = QComboBox()
                if not speaker_ids:
                    speaker_combo.addItem("Auto (No diarization)", "")
                    speaker_combo.setEnabled(False)
                else:
                    for position, speaker_id in enumerate(speaker_ids):
                        speaker_combo.addItem(self._speaker_display_name(speaker_id, position), speaker_id)
                    combo_index = speaker_combo.findData(selected_speaker)
                    if combo_index >= 0:
                        speaker_combo.setCurrentIndex(combo_index)
                    speaker_combo.setEnabled(True)
                speaker_combo.setFixedHeight(26)
                speaker_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                speaker_combo.setToolTip(
                    "Assign this subtitle segment to a detected speaker."
                    if speaker_ids else "Run Speaker Diarization first to assign a speaker."
                )
                speaker_combo.currentIndexChanged.connect(
                    lambda _value, segment_index=idx, combo=speaker_combo: self.on_segment_speaker_changed(
                        segment_index, str(combo.currentData() or "")
                    )
                )

                speed_label = QLabel("Speed:")
                speed_label.setObjectName("helperLabel")
                speed_spin = QDoubleSpinBox()
                speed_spin.setRange(0.5, 3.0)
                speed_spin.setSingleStep(0.1)
                speed_spin.setDecimals(1)
                speed_spin.setValue(float(row.get("voice_speed", 1.0)))
                speed_spin.setSuffix("x")
                speed_spin.setFixedHeight(26)
                speed_spin.setFixedWidth(70)
                speed_spin.valueChanged.connect(
                    lambda val, idx=idx: self.on_segment_voice_speed_changed(idx, val)
                )

                props_row.addWidget(speaker_label)
                props_row.addWidget(speaker_combo, 1)
                props_row.addWidget(speed_label)
                props_row.addWidget(speed_spin)
                card_layout.addLayout(props_row)

                # Original Transcript Frame
                orig_container = QFrame()
                orig_container.setObjectName("originalTextCard")
                orig_container.setStyleSheet(
                    "QFrame#originalTextCard { background-color: #0b111a; border: 1px solid #1c2738; border-radius: 6px; padding: 6px 10px; }"
                )
                orig_box_layout = QVBoxLayout(orig_container)
                orig_box_layout.setContentsMargins(6, 4, 6, 4)
                orig_box_layout.setSpacing(2)

                orig_title = QLabel("ORIGINAL TRANSCRIPT (BẢN GỐC)")
                orig_title.setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800; letter-spacing: 0.5px;")

                original_label = QLabel(row["original"] or "", card)
                original_label.setWordWrap(True)
                original_label.setObjectName("helperLabel")
                original_label.setStyleSheet("color: #cbd5e1; font-size: 12px;")

                orig_box_layout.addWidget(orig_title)
                orig_box_layout.addWidget(original_label)
                orig_container.setVisible(show_original and bool(str(row.get("original", "") or "").strip()))
                card_layout.addWidget(orig_container)

                # Translated Subtitle Editor
                editor_title = QLabel("ON-SCREEN SUBTITLE (BẢN DỊCH HIỂN THỊ)")
                editor_title.setStyleSheet("color: #818cf8; font-size: 9px; font-weight: 800; letter-spacing: 0.5px; margin-top: 2px;")
                card_layout.addWidget(editor_title)

                translated_editor = QTextEdit()
                translated_editor.setObjectName("segmentInspectorEditor")
                translated_editor.setAcceptRichText(False)
                translated_editor.setPlainText(row["translated"])
                translated_editor.setMinimumHeight(84)
                translated_editor.setMaximumHeight(84)
                translated_editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                translated_editor.setPlaceholderText("Text shown on screen.")
                translated_editor.textChanged.connect(
                    lambda idx=idx, editor=translated_editor: self.on_segment_translation_edited(idx, editor)
                )
                translated_editor.selectionChanged.connect(
                    lambda idx=idx, editor=translated_editor: self._update_segment_highlight_button_state(idx, editor)
                )
                highlight_btn = QPushButton("✨ Add highlight from selection")
                highlight_btn.setObjectName("subtitleHighlightBtn")
                highlight_btn.setEnabled(False)
                highlight_btn.setFixedHeight(28)
                highlight_btn.setCursor(Qt.PointingHandCursor)
                highlight_btn.clicked.connect(
                    lambda _=False, idx=idx, editor=translated_editor: self.add_segment_manual_highlight(idx, editor)
                )

                highlight_action_layout = QHBoxLayout()
                highlight_action_layout.setContentsMargins(0, 0, 0, 0)
                highlight_action_layout.setSpacing(8)
                highlight_action_layout.addWidget(highlight_btn)
                highlight_action_layout.addStretch()

                highlight_meta_layout = QHBoxLayout()
                highlight_meta_layout.setContentsMargins(0, 0, 0, 0)
                highlight_meta_layout.setSpacing(6)
                highlight_placeholder = QLabel("")
                highlight_placeholder.setObjectName("helperLabel")
                highlight_chip_container = QWidget()
                highlight_chip_layout = QHBoxLayout(highlight_chip_container)
                highlight_chip_layout.setContentsMargins(0, 0, 0, 0)
                highlight_chip_layout.setSpacing(6)
                highlight_meta_layout.addWidget(highlight_placeholder)
                highlight_meta_layout.addWidget(highlight_chip_container, 1)

                card_layout.addWidget(translated_editor, 0)
                card_layout.addLayout(highlight_action_layout)
                card_layout.addLayout(highlight_meta_layout)

                self.segment_editor_layout.addWidget(card, 0)
                self._segment_editor_rows.append(
                    {
                        "segment_index": idx,
                        "frame": card,
                        "original_label": original_label,
                        "translated_editor": translated_editor,
                        "highlight_button": highlight_btn,
                        "highlight_placeholder": highlight_placeholder,
                        "highlight_chip_layout": highlight_chip_layout,
                    }
                )
                self._update_segment_highlight_button_state(idx, translated_editor)
                self._sync_segment_highlight_chip_row(idx)
                self._update_segment_spoken_status(idx)

            self._set_segment_editor_highlight(selected_index)
        finally:
            self._syncing_segment_editor = False

    def sync_segment_editor_from_hidden_text(self):
        if getattr(self, "_syncing_hidden_editor_text", False):
            return

        transcript_text = self.transcript_text.toPlainText().strip()
        if transcript_text and not transcript_text.lower().startswith("transcribing..."):
            # Preserve non-SRT metadata (notably diarization speaker IDs)
            # when the hidden SRT editor is populated during project load.
            parsed_transcript = self._segments_from_editor_text(
                transcript_text, self.current_segments
            )
            if parsed_transcript:
                self.current_segments = parsed_transcript

        translated_text = self.translated_text.toPlainText().strip()
        if translated_text and not translated_text.lower().startswith("translating with "):
            base_segments = self.current_translated_segments or self.current_segments
            parsed_translated = self._segments_from_editor_text(translated_text, base_segments)
            if parsed_translated:
                self.current_translated_segments = parsed_translated

        self.sync_segment_editor_rows()

    def _sync_hidden_translated_text_from_segments(self):
        if getattr(self, "_syncing_segment_editor", False):
            return
        self._syncing_hidden_editor_text = True
        try:
            self.translated_text.setText(self.format_to_srt(self.current_translated_segments))
        finally:
            self._syncing_hidden_editor_text = False

    def on_segment_translation_edited(self, index: int, editor: QTextEdit):
        if getattr(self, "_syncing_segment_editor", False):
            return

        base_segments = self.current_segments or self.current_translated_segments
        if not base_segments or index >= len(base_segments):
            return

        if len(self.current_translated_segments) != len(base_segments):
            self.current_translated_segments = [
                {
                    "start": float(base.get("start", 0.0)),
                    "end": float(base.get("end", 0.0)),
                    "text": str(self.current_translated_segments[idx].get("text", "")) if idx < len(self.current_translated_segments) else "",
                    "tts_text": str(self.current_translated_segments[idx].get("tts_text", base.get("tts_text", "")) or "") if idx < len(self.current_translated_segments) else str(base.get("tts_text", "") or ""),
                    "tts_group_id": self.current_translated_segments[idx].get("tts_group_id", base.get("tts_group_id", "")) if idx < len(self.current_translated_segments) else base.get("tts_group_id", ""),
                    "tts_group_start": float(self.current_translated_segments[idx].get("tts_group_start", base.get("tts_group_start", base.get("start", 0.0))) or base.get("start", 0.0)) if idx < len(self.current_translated_segments) else float(base.get("tts_group_start", base.get("start", 0.0)) or base.get("start", 0.0)),
                    "tts_group_end": float(self.current_translated_segments[idx].get("tts_group_end", base.get("tts_group_end", base.get("end", 0.0))) or base.get("end", 0.0)) if idx < len(self.current_translated_segments) else float(base.get("tts_group_end", base.get("end", 0.0)) or base.get("end", 0.0)),
                    "words": list(base.get("words", [])),
                    "manual_highlights": list(base.get("manual_highlights", [])),
                    "speaker": str(base.get("speaker", "") or ""),
                }
                for idx, base in enumerate(base_segments)
            ]

        segment = self.current_translated_segments[index]
        new_text = editor.toPlainText().strip()
        if new_text == str(segment.get("text", "") or ""):
            return
        segment["text"] = new_text
        segment["final_text"] = new_text
        segment["subtitle_vi"] = new_text
        # A subtitle text edit must not keep speaking an earlier manual or AI
        # rewrite. The next TTS run uses the freshly edited subtitle text.
        segment["tts_text"] = ""
        segment["dubbing_vi"] = ""
        segment["voice_edited"] = False
        segment.setdefault("manual_highlights", [])
        self._reconcile_manual_highlights(segment)
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._sync_segment_highlight_chip_row(index)
        self._sync_hidden_translated_text_from_segments()
        self._commit_subtitle_mutation(selected_index=index, changed_indices={int(index)})

    def on_segment_voice_speed_changed(self, index: int, value: float):
        if getattr(self, "_syncing_segment_editor", False):
            return
        updated = False
        new_speed = round(float(value), 1)
        for segments_list in (self.current_translated_segments, self.current_segments):
            if segments_list and 0 <= index < len(segments_list):
                if segments_list[index].get("voice_speed") != new_speed:
                    segments_list[index]["voice_speed"] = new_speed
                    updated = True
                self._voiceover_force_refresh = True
        if updated:
            if self.current_translated_segments:
                self.current_translated_segment_models = self._dict_segments_to_models(
                    self.current_translated_segments, translated=True
                )
            if self.current_segments:
                self.current_segment_models = self._dict_segments_to_models(
                    self.current_segments, translated=False
                )
            self._invalidate_dubbed_output_after_subtitle_edit()
            state = getattr(self, "current_project_state", None)
            if state is not None and hasattr(self, "project_bridge"):
                try:
                    self.current_translated_segment_models = self.project_bridge.persist_translation(
                        state,
                        self.current_segment_models or [],
                        self.current_translated_segments or [],
                        self.last_translated_srt_path,
                    )
                except Exception as exc:
                    if hasattr(self, "log"):
                        self.log(f"[Subtitle] Could not persist voice speed change: {exc}")
            self.persist_current_timeline_project_data()

    def _set_segment_editor_highlight(self, active_index: int):
        rows = getattr(self, "_segment_editor_rows", [])
        target_frame = None
        for row in rows:
            row_index = int(row.get("segment_index", -1))
            if row_index == active_index:
                row["frame"].setStyleSheet("QFrame#statusCard { background-color: #153149; border: 1px solid #5fb9ff; border-radius: 14px; }")
                target_frame = row["frame"]
            else:
                row["frame"].setStyleSheet("")
        # Scroll the outer inspector card so the highlighted segment
        # is visible. The inner segment_editor_scroll was flattened;
        # the QScrollArea wrapping the subtitle card is at stack index 0.
        if target_frame is not None and hasattr(self, "inspector_stack"):
            try:
                scroll = self.inspector_stack.widget(0)
                if scroll is not None and hasattr(scroll, "ensureWidgetVisible"):
                    scroll.ensureWidgetVisible(target_frame, 0, 36)
            except Exception:
                pass

    def play_audio_preview_file(self, audio_path: str):
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError("Audio preview file was not found.")
        if os.path.getsize(audio_path) <= 44:
            raise RuntimeError("Audio preview file is empty or invalid.")
        if hasattr(self, "media_player") and self.media_player.is_playing():
            self.media_player.pause()
            if hasattr(self, "timeline"):
                self.timeline.set_playing(False)
        self.audio_preview_player.stop()
        self.audio_preview_player.setSource(QUrl.fromLocalFile(audio_path))
        self.audio_preview_player.play()
        self._last_audio_preview_path = audio_path

    def preview_current_audio_track(self):
        audio_path = self.resolve_selected_audio_path()
        if not audio_path or not os.path.exists(audio_path):
            QMessageBox.warning(self, "Missing Voice", "Please generate voice first before using Preview audio.")
            return
        try:
            self.play_audio_preview_file(audio_path)
            self.log(f"[Audio Preview] playing {audio_path}")
        except Exception as exc:
            self.show_error("Audio Preview Failed", "Could not preview the current audio track.", str(exc))

    def _blur_effect_enabled(self) -> bool:
        return bool(hasattr(self, "blur_area_btn") and self.blur_area_btn.isChecked())

    def _sync_blur_controls(self):
        video_view = getattr(self, "video_view", None)
        blur_btn = getattr(self, "blur_area_btn", None)
        blur_add_btn = getattr(self, "blur_add_btn", None)
        if video_view is None or blur_btn is None:
            return
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        has_video = bool(source_path and os.path.exists(source_path))
        blur_enabled = self._blur_effect_enabled()
        is_playing = False
        media_player = getattr(self, "media_player", None)
        if media_player is not None:
            try:
                is_playing = bool(media_player.is_playing())
            except Exception:
                is_playing = False
        # The blur overlay (the draggable rectangle) is only shown
        # when the blur effect is ON. Turning the effect OFF hides
        # the rectangle; turning it ON shows it again for drag.
        has_regions = bool(self._current_blur_regions_payload())
        selected_id = str(getattr(getattr(self, "timeline", None), "_selected_layer_id", "") or "")
        selected_blur = False
        timeline_model = getattr(getattr(self, "timeline", None), "_timeline", None)
        for track in getattr(timeline_model, "tracks", []):
            if str(getattr(track, "name", "")) != "B1":
                continue
            selected_blur = any(str(getattr(layer, "id", "")) == selected_id for layer in getattr(track, "layers", []))
            break
        editing_allowed = (
            blur_enabled
            and has_video
            and has_regions
            and selected_blur
            and not is_playing
            and not bool(getattr(self, "_filter_thumbnail_visible", False))
        )
        if hasattr(video_view, "set_blur_edit_enabled"):
            video_view.set_blur_edit_enabled(editing_allowed)
        if blur_add_btn is not None:
            # The "+" button must be clickable even when the blur effect
            # toggle is OFF: pressing it should both enable the effect
            # AND add a region. Requiring the user to toggle first is
            # unnecessary friction.
            blur_add_btn.setEnabled(
                bool(getattr(self, "_optional_layer_controls_ready", False))
                and has_video
                and not is_playing
                and not bool(getattr(self, "_filter_thumbnail_visible", False))
            )

    def toggle_blur_effect_enabled(self, checked: bool):
        if not hasattr(self, "video_view") or not hasattr(self, "blur_area_btn"):
            return
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        has_video = bool(source_path and os.path.exists(source_path))
        if checked and not has_video:
            self.blur_area_btn.blockSignals(True)
            self.blur_area_btn.setChecked(False)
            self.blur_area_btn.blockSignals(False)
            QMessageBox.warning(self, "Blur Area", "Please load a video before adding a blur area.")
            return
        # The B1 header visibility control is the single visibility source.
        # Update the managed MPV effect immediately, including while paused.
        self._sync_blur_controls()
        if hasattr(self, "media_player"):
            if checked:
                self.apply_preview_blur_region(force=True)
            else:
                self.media_player.clear_blur_region()
        self.persist_project_blur_state()
        # Sync the B1 track label so the ON/OFF indicator matches
        if hasattr(self, "track_label_bar"):
            try:
                self.track_label_bar.set_blur_on("B1", bool(checked))
            except Exception:
                pass
        if checked:
            self.log("[Blur Area] blur effect enabled.")

    def add_blur_region(self):
        if not hasattr(self, "video_view"):
            return
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        has_video = bool(source_path and os.path.exists(source_path))
        if not has_video:
            QMessageBox.warning(self, "Blur Area", "Please load a video before adding a blur area.")
            return
        if hasattr(self, "blur_area_btn") and not self.blur_area_btn.isChecked():
            self.blur_area_btn.blockSignals(True)
            self.blur_area_btn.setChecked(True)
            self.blur_area_btn.blockSignals(False)
        if hasattr(self.video_view, "add_blur_region"):
            self.video_view.add_blur_region()
        # Do NOT call on_add_timeline_layer("blur") here. The
        # blurRegionChanged signal emitted by add_blur_region() will
        # trigger on_preview_blur_region_changed() which (with the
        # recent fix) syncs the B1 track from the overlay regions
        # even when the blur effect is on. Adding a BlurLayer here too
        # would create a duplicate.
        self._sync_blur_controls()
        self._blur_region_preview_dirty = True
        if hasattr(self, "media_player"):
            self.media_player.clear_blur_region()
        self.persist_project_blur_state()

    def on_blur_edit_finished(self):
        if getattr(self, "_blur_edit_finish_syncing", False):
            return
        if not self._blur_effect_enabled():
            return
        self._blur_region_preview_dirty = True
        self.schedule_timeline_project_persist(blur_state=True)

    def toggle_ocr_region_editing(self, checked: bool):
        return self.ocr_controller.toggle_ocr_region_editing(checked)

    def toggle_ocr_translator(self, checked: bool):
        return self.ocr_controller.toggle_ocr_translator(checked)

    def _on_ocr_translator_rect_changed(self, rect):
        return self.ocr_controller.on_ocr_translator_rect_changed(rect)

    def capture_ocr_translator_region(self):
        return self.ocr_controller.capture_ocr_translator_region()

    def _on_ocr_translator_capture_finished(self, text, error):
        return self.ocr_controller.on_ocr_translator_capture_finished(text, error)

    def _show_ocr_translator_dialog(self, original_text):
        return self.ocr_controller.show_ocr_translator_dialog(original_text)

    def on_preview_blur_region_changed(self):
        if self._preview_is_playing():
            return
        if self._blur_effect_enabled():
            self._blur_region_preview_dirty = True
            # Even when the blur effect is on, the B1 track in the
            # timeline must stay in sync with the overlay regions. Without
            # this, deleting a region from the overlay leaves a stale
            # BlurLayer behind in the timeline. The actual mpv blur
            # effect is only updated when the video plays, to keep
            # editing fast.
            if hasattr(self, "timeline"):
                try:
                    regions = self._current_blur_regions_payload() if hasattr(self, "_current_blur_regions_payload") else []
                    self.timeline.sync_blur_regions(regions)
                    # Keep the real effect attached to the editable frame.
                    # Previously only the dashed outline moved while the
                    # selected B1 effect remained at its old coordinates.
                    self.apply_preview_blur_region(regions=regions, force=True)
                    self.schedule_timeline_project_persist(blur_state=True)
                except Exception:
                    pass
            return
        self.apply_preview_blur_region()
        self.schedule_timeline_project_persist(blur_state=True)
        if hasattr(self, "timeline"):
            regions = self._current_blur_regions_payload() if hasattr(self, "_current_blur_regions_payload") else []
            self.timeline.sync_blur_regions(regions)

    def apply_preview_blur_region(self, *, regions=None, force: bool = False):
        if not hasattr(self, "media_player") or not hasattr(self, "video_view"):
            return
        self._blur_region_preview_dirty = False
        blur_enabled = self._blur_effect_enabled()
        if regions is not None:
            blur_region = regions
        else:
            blur_region = self._current_blur_regions_payload()
        # Always apply the blur when enabled and regions exist, even
        # when the video is paused, so the user can see the cached
        # blur effect on the video preview.
        if blur_enabled and blur_region:
            self.media_player.set_blur_region(blur_region)
        else:
            self.media_player.clear_blur_region()

    def _current_blur_regions_payload(self):
        if not hasattr(self, "video_view") or not hasattr(self.video_view, "get_blur_region_normalized"):
            return []
        raw_regions = self.video_view.get_blur_region_normalized()
        if isinstance(raw_regions, dict):
            raw_regions = [raw_regions]
        if not isinstance(raw_regions, list):
            return []
        regions = []
        for region in raw_regions:
            if not isinstance(region, dict):
                continue
            try:
                x = max(0.0, min(1.0, float(region.get("x", 0.0))))
                y = max(0.0, min(1.0, float(region.get("y", 0.0))))
                width = max(0.0, min(1.0 - x, float(region.get("width", 0.0))))
                height = max(0.0, min(1.0 - y, float(region.get("height", 0.0))))
            except (TypeError, ValueError):
                continue
            if width <= 0.0 or height <= 0.0:
                continue
            entry = {
                "x": round(x, 6),
                "y": round(y, 6),
                "width": round(width, 6),
                "height": round(height, 6),
            }
            # Per-region style (radius, opacity, pixelate). Defaults
            # are chosen so an existing region without these keys
            # behaves the same as before the inspector was added.
            try:
                strength = region.get("blur_strength", region.get("strength"))
                if strength is not None:
                    entry["blur_strength"] = int(round(float(strength)))
            except (TypeError, ValueError):
                pass
            try:
                opacity = region.get("blur_opacity", region.get("opacity"))
                if opacity is not None:
                    entry["blur_opacity"] = round(float(opacity), 4)
            except (TypeError, ValueError):
                pass
            if bool(region.get("pixelate", False)):
                entry["pixelate"] = True
                try:
                    entry["pixelate_size"] = int(region.get("pixelate_size", 12))
                except (TypeError, ValueError):
                    entry["pixelate_size"] = 12
            regions.append(entry)
        # Preview rectangles store geometry only. Preserve timing and per-layer
        # style from B1 whenever its layers correspond one-to-one with those
        # rectangles. This is essential after splitting: a blur piece remains
        # an independent timed layer instead of being rebuilt as a full-video
        # region by the preview-to-timeline sync.
        blur_layers = []
        timeline_model = getattr(getattr(self, "timeline", None), "_timeline", None)
        for track in list(getattr(timeline_model, "tracks", []) or []):
            if str(getattr(track, "name", "") or "") == "B1":
                blur_layers = list(getattr(track, "layers", []) or [])
                break
        if blur_layers and len(blur_layers) != len(regions):
            # A split layer can produce several timeline clips that share
            # one original preview rectangle. In that case the timeline is
            # authoritative: expand its independent clips back into payload
            # entries rather than collapsing them to the single rectangle.
            regions = []
            for layer in blur_layers:
                try:
                    regions.append({
                        "x": round(float(getattr(layer, "position_x", 0.0) or 0.0), 6),
                        "y": round(float(getattr(layer, "position_y", 0.0) or 0.0), 6),
                        "width": round(float(getattr(layer, "width", 0.0) or 0.0), 6),
                        "height": round(float(getattr(layer, "height", 0.0) or 0.0), 6),
                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                        "blur_strength": float(getattr(layer, "blur_strength", 20.0) or 20.0),
                        "blur_opacity": float(getattr(layer, "blur_opacity", 1.0) or 1.0),
                        "pixelate": bool(getattr(layer, "pixelate", False)),
                        "pixelate_size": int(getattr(layer, "pixelate_size", 12) or 12),
                    })
                except (TypeError, ValueError):
                    continue
        elif len(blur_layers) == len(regions):
            for entry, layer in zip(regions, blur_layers):
                try:
                    entry["start"] = float(getattr(layer, "start", 0.0) or 0.0)
                    entry["end"] = float(getattr(layer, "end", 0.0) or 0.0)
                    entry["blur_strength"] = float(getattr(layer, "blur_strength", entry.get("blur_strength", 20)) or 20)
                    entry["blur_opacity"] = float(getattr(layer, "blur_opacity", entry.get("blur_opacity", 1.0)) or 1.0)
                    entry["pixelate"] = bool(getattr(layer, "pixelate", entry.get("pixelate", False)))
                    entry["pixelate_size"] = int(getattr(layer, "pixelate_size", entry.get("pixelate_size", 12)) or 12)
                except (TypeError, ValueError):
                    continue
        return regions

    def persist_project_blur_state(self, *, regions=None, enabled=None):
        state = getattr(self, "current_project_state", None)
        if not state:
            return
        if regions is None:
            regions = self._current_blur_regions_payload()
        if enabled is None:
            enabled = self._blur_effect_enabled()
        blur_state = {
            "enabled": bool(enabled),
            "regions": list(regions or []),
        }
        if state.settings.get("blur_state") == blur_state:
            return
        state.set_setting("blur_state", blur_state)
        self.project_service.save_project(state)



    def _restore_project_blur_state(self, state):
        blur_state = dict(getattr(state, "settings", {}).get("blur_state") or {})
        regions = blur_state.get("regions", [])
        # A serialized timeline is authoritative for optional layers.  The
        # legacy blur_state setting can be stale after deleting the last B1
        # layer, so never use it to recreate a deleted layer on reopen.
        if getattr(self, "_saved_timeline_model_restored", False):
            timeline_model = getattr(getattr(self, "timeline", None), "_timeline", None)
            timeline_layers = []
            for track in getattr(timeline_model, "tracks", []) or []:
                if str(getattr(track, "name", "") or "") == "B1":
                    timeline_layers = list(getattr(track, "layers", []) or [])
                    break
            regions = []
            for layer in timeline_layers:
                try:
                    regions.append({
                        "x": float(getattr(layer, "position_x", 0.0) or 0.0),
                        "y": float(getattr(layer, "position_y", 0.0) or 0.0),
                        "width": float(getattr(layer, "width", 0.0) or 0.0),
                        "height": float(getattr(layer, "height", 0.0) or 0.0),
                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                        "blur_strength": float(getattr(layer, "blur_strength", 20.0) or 20.0),
                        "blur_opacity": float(getattr(layer, "blur_opacity", 1.0) or 1.0),
                        "pixelate": bool(getattr(layer, "pixelate", False)),
                        "pixelate_size": int(getattr(layer, "pixelate_size", 12) or 12),
                    })
                except (TypeError, ValueError):
                    continue
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_blur_regions_normalized"):
            self.video_view.set_blur_regions_normalized(regions)
        # Restore the B1 track visibility instead of forcing Blur back on.
        # Older projects did not save this value and therefore default to ON.
        blur_enabled = bool(blur_state.get("enabled", True))
        if hasattr(self, "blur_area_btn"):
            self.blur_area_btn.blockSignals(True)
            self.blur_area_btn.setChecked(blur_enabled)
            self.blur_area_btn.blockSignals(False)
        self._sync_blur_controls()
        if hasattr(self, "track_label_bar"):
            try:
                self.track_label_bar.set_blur_on("B1", blur_enabled)
            except Exception:
                pass
        if hasattr(self, "timeline") and not getattr(self, "_saved_timeline_model_restored", False):
            self.timeline.sync_blur_regions(regions)
        if hasattr(self, "media_player"):
            try:
                if blur_enabled:
                    self.apply_preview_blur_region(force=True)
                else:
                    self.media_player.clear_blur_region()
            except Exception:
                self.media_player.clear_blur_region()

    # ---- Mask layer (M1) ----
    def _current_mask_regions_payload(self, *, time_seconds=None, include_inactive=False,
                                      exclude_layer_id: str = ""):
        """Build the mask payload from the M1 track's MaskLayers.

        Visibility is NOT checked here — the play-state gate in
        _apply_mask_to_preview is the single source of truth for
        whether the mask is shown on the video. The payload always
        includes every M1 layer so the mask is ready the moment the
        user presses play.
        """
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return []
        items: list[dict] = []
        for tr in self.timeline._timeline.tracks:
            if tr.name != "M1":
                continue
            for layer in tr.layers:
                if exclude_layer_id and str(getattr(layer, "id", "") or "") == str(exclude_layer_id):
                    continue
                if not include_inactive and not self._layer_is_active_at_preview_time(layer, time_seconds):
                    continue
                try:
                    items.append({
                        "x": float(getattr(layer, "position_x", 0.3)),
                        "y": float(getattr(layer, "position_y", 0.4)),
                        "width": float(getattr(layer, "width", 0.4)),
                        "height": float(getattr(layer, "height", 0.2)),
                        "color": str(getattr(layer, "color", "#000000")),
                        "mode": str(getattr(layer, "mode", "solid")),
                        "opacity": float(getattr(layer, "opacity", 1.0)),
                        "pixelate_size": int(getattr(layer, "pixelate_size", 12)),
                        "blur_strength": int(getattr(layer, "blur_strength", 20)),
                        "start": float(getattr(layer, "start", 0.0) or 0.0),
                        "end": float(getattr(layer, "end", 0.0) or 0.0),
                    })
                except (TypeError, ValueError):
                    continue
        return items

    def _apply_mask_to_preview(self, *, regions=None, force: bool = False):
        """Push the M1 mask track into the mpv filter chain.

        The mask effect is independent of timeline selection and playback
        state.  Pausing or selecting another layer must not remove it from
        the preview; only the dedicated M1 visibility control (or an empty
        mask track) may clear the effect.  The editable outline/handles are
        managed separately by the timeline selection.

        `force=True` bypasses the play-state gate (used by direct
        calls from `toggle_play` so the mask is applied/cleared in
        the same code path as the play/pause).
        """
        if not hasattr(self, "media_player"):
            return
        # M1 Hide/Show must survive play/pause, project restoration, and
        # native-window focus changes.  Never rebuild a hidden mask graph.
        if not bool(getattr(self, "_mask_track_preview_visible", True)):
            self.media_player.clear_mask_region()
            return
        if regions is None:
            regions = self._current_mask_regions_payload(
                include_inactive=True,
                exclude_layer_id=self._deferred_effect_layer_id_for("mask"),
            )
        if force:
            if regions:
                self.media_player.set_mask_region(regions)
            else:
                self.media_player.clear_mask_region()
            return
        if regions:
            self.media_player.set_mask_region(regions)
        else:
            self.media_player.clear_mask_region()

    def _on_preview_state_changed(self, _state: int):
        """Re-apply the M1 mask filter when the player state changes.

        The mask is only applied to the video while the player is
        playing. Hooked from `media_player.stateChanged` in
        `setup_media_player` so the mpv filter chain is updated on
        play / pause / stop. The mask overlay is also locked
        (`set_editable(False)`) while the video is playing so the
        user cannot accidentally drag or resize the region during
        playback. Also sync the timeline play state so the timeline
        stops running when the video ends (Bug 2).
        """
        try:
            is_playing = bool(self.media_player.is_playing())
        except Exception:
            is_playing = False
        was_review_mode = bool(getattr(self, "_review_mode_active", False))
        self._review_mode_active = is_playing
        if is_playing:
            # Entering review mode is an explicit commit boundary. This
            # restores a deferred Blur/Mask at its final geometry before the
            # next frame is shown, then removes every preview edit target.
            self._preview_edit_layer_id = ""
        if is_playing or was_review_mode:
            # Borders are selection chrome, not rendered layer content.
            # Clear their active state on both Review entry and its pause
            # transition; a subsequent explicit paused selection re-enables
            # only the requested layer.
            if hasattr(self, "video_view") and hasattr(self.video_view, "subtitle_item"):
                self.video_view.subtitle_item.set_editable(False)
            self._refresh_text_layer_preview("")
        if hasattr(self, "track_label_bar"):
            self.track_label_bar.set_controls_enabled(not is_playing)
        splitter = getattr(self, "preview_timeline_splitter", None)
        if splitter is not None:
            try:
                # Review Mode keeps the preview geometry stable so native
                # overlays and MPV effects cannot be disturbed mid-playback.
                # Disable only the handle; never disable the child widgets.
                splitter.handle(1).setEnabled(not is_playing)
            except Exception:
                pass
        # Sync the timeline's "playing" flag to the real player state.
        # Without this the timeline keeps animating past the end of the
        # video because the player auto-pauses (keep_open="always") but
        # nothing tells the timeline to stop.
        try:
            if hasattr(self, "timeline") and self.timeline is not None:
                self.timeline.set_playing(is_playing)
        except Exception:
            pass
        # Lock / unlock editing based on both play state and timeline
        # selection. Pausing must not make every region editable.
        try:
            selected_id = str(getattr(getattr(self, "timeline", None), "_selected_layer_id", "") or "")
            selected_type = ""
            selected_track_name = ""
            for track in getattr(getattr(self.timeline, "_timeline", None), "tracks", []) if hasattr(self, "timeline") else []:
                for layer in getattr(track, "layers", []):
                    if str(getattr(layer, "id", "")) == selected_id:
                        selected_type = str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower()
                        selected_track_name = str(getattr(track, "name", ""))
                        break
                if selected_type:
                    break
            if is_playing:
                effect_edit_changed = self.commit_deferred_effect_editing(refresh=False)
            else:
                # Pausing enters Edit Mode, but does not automatically start
                # editing the layer selected before playback. Effects remain
                # rendered and handles remain hidden until the user selects
                # a layer again.
                effect_edit_changed = False
            if effect_edit_changed:
                self.refresh_timed_layer_preview()
            mask_overlay = getattr(self.video_view, "mask_overlay", None)
            if mask_overlay is not None and mask_overlay._regions:
                mask_overlay.set_editable(bool(
                    not is_playing
                    and selected_type == "mask"
                    and selected_track_name == "M1"
                    and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                    and self._deferred_effect_layer_id_for("mask") == selected_id
                ))
            if hasattr(self, "video_view") and hasattr(self.video_view, "set_blur_edit_enabled"):
                self.video_view.set_blur_edit_enabled(
                    bool(
                        not is_playing
                        and selected_type == "blur"
                        and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                        and self._deferred_effect_layer_id_for("blur") == selected_id
                        and self._blur_effect_enabled()
                    )
                )
            logo_overlay = getattr(self.video_view, "logo_overlay", None)
            if logo_overlay is not None and getattr(logo_overlay, "_regions", None):
                logo_overlay.set_editable(bool(
                    not is_playing
                    and selected_type == "image"
                    and selected_track_name == "L1 Logo"
                    and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                ))
            if hasattr(self, "video_view") and getattr(self.video_view, "text_overlay", None) is not None:
                # Keep text content visible but make its top-level overlay
                # click-through in review mode and immediately after pause.
                self.video_view.text_overlay.set_editable(False if (is_playing or was_review_mode) else bool(
                    selected_type == "text" and selected_id == str(getattr(self, "_preview_edit_layer_id", "") or "")
                ))
        except Exception:
            pass
        # When playback just ended, pause both audio sidecars so they
        # don't drift ahead of the held last frame.
        if not is_playing and hasattr(self, "media_player"):
            try:
                if hasattr(self.media_player, "_original_loaded_path") and getattr(self.media_player, "_original_loaded_path", ""):
                    self.media_player._original_player.pause()
            except Exception:
                pass
            try:
                if hasattr(self.media_player, "_dubbed_loaded_path") and getattr(self.media_player, "_dubbed_loaded_path", ""):
                    self.media_player._dubbed_player.pause()
            except Exception:
                pass
        try:
            self._apply_mask_to_preview()
        except Exception:
            pass
        QTimer.singleShot(0, self.refresh_ui_state)

    def persist_project_mask_state(self, *, regions=None):
        state = getattr(self, "current_project_state", None)
        if not state:
            return
        if regions is None:
            regions = self._current_mask_regions_payload()
        mask_state = {
            "enabled": bool(getattr(self, "_mask_track_preview_visible", True)),
            "regions": list(regions or []),
        }
        if state.settings.get("mask_state") == mask_state:
            return
        state.set_setting("mask_state", mask_state)
        self.project_service.save_project(state)

    def _restore_project_mask_state(self, state):
        mask_state = dict(getattr(state, "settings", {}).get("mask_state") or {})
        regions = mask_state.get("regions", [])
        timeline_model_restored = bool(getattr(self, "_saved_timeline_model_restored", False))
        if timeline_model_restored:
            # The saved M1 track is authoritative.  In particular, an empty
            # M1 track means the user deleted the final mask and must not be
            # reconstructed from the legacy mask_state setting.
            regions = self._current_mask_regions_payload(include_inactive=True)
        if hasattr(self, "media_player"):
            self._apply_mask_to_preview(regions=regions, force=True)
        if hasattr(self, "track_label_bar"):
            try:
                self.track_label_bar.set_mask_shown(
                    "M1", bool(getattr(self, "_mask_track_preview_visible", True))
                )
            except Exception:
                pass
        # Sync the M1 track from legacy settings only when no serialized
        # timeline was available.  Otherwise this method must not recreate
        # deleted layers or overwrite their timing/style properties.
        if hasattr(self, "timeline") and regions and not timeline_model_restored:
            try:
                from app.layers.mask import MaskLayer
                from app.layers.sync_bridge import find_or_create_track
                from app.layers.base import LayerType
                tl = self.timeline._timeline
                track = find_or_create_track(tl, "M1", LayerType.MASK, 60)
                track.layers.clear()
                # Mask layers span the full video duration (like the
                # audio track) so the M1 row matches the video length
                # rather than collapsing to a zero-width clip (Bug 1).
                mask_end = tl.duration if tl.duration > 0 else (
                    self.timeline._duration if hasattr(self.timeline, "_duration") else 0.0
                )
                if mask_end <= 0:
                    mask_end = 5.0
                for i, r in enumerate(regions):
                    layer = MaskLayer(
                        name=f"Mask {i + 1}",
                        position_x=float(r.get("x", 0.3)),
                        position_y=float(r.get("y", 0.4)),
                        width=float(r.get("width", 0.4)),
                        height=float(r.get("height", 0.2)),
                        color=str(r.get("color", "#000000")),
                        mode=str(r.get("mode", "solid")),
                        pixelate_size=int(r.get("pixelate_size", 12)),
                        blur_strength=int(r.get("blur_strength", 20)),
                        start=0.0,
                        end=float(mask_end),
                    )
                    layer.z_index = i
                    track.layers.append(layer)
                if hasattr(self.timeline, "_track_heights"):
                    self.timeline._track_heights[track.id] = 60
                self.timeline._redraw()
                # Keep the restored mask available for preview/editing. The
                # caller selects V1 after all tracks are restored, so this
                # does not steal the default project focus.
                if track.layers:
                    try:
                        first_layer = track.layers[0]
                        self.timeline._selected_layer_id = first_layer.id
                        self._show_mask_overlay(track, first_layer)
                    except Exception:
                        pass
            except Exception:
                pass

    def _show_mask_inspector_for_track(self, track, layer=None):
        """Show the Mask Track Inspector populated with the selected M1 layer.

        The inspector only exposes the mask's colour + opacity. Position,
        size and mode are not configurable here — the user positions /
        resizes the region via the draggable overlay on the video. The
        mask is only applied to the video while the player is playing.
        """
        self._switch_inspector("mask")
        self._wire_mask_inspector_controls()
        self._wire_layer_timing_controls("mask")
        if layer is None:
            return
        self._set_layer_timing_controls("mask", layer)
        color = str(getattr(layer, "color", "#000000"))
        if hasattr(self, "mask_inspector_color_btn"):
            self.mask_inspector_color_btn.blockSignals(True)
            self.mask_inspector_color_btn.setText(color)
            self.mask_inspector_color_btn.setStyleSheet(
                f"background-color: {color}; color: #fff;"
            )
            self.mask_inspector_color_btn.blockSignals(False)
        try:
            opacity = float(getattr(layer, "opacity", 1.0))
        except (TypeError, ValueError):
            opacity = 1.0
        opacity = max(0.0, min(1.0, opacity))
        if hasattr(self, "mask_inspector_opacity_slider"):
            self.mask_inspector_opacity_slider.blockSignals(True)
            self.mask_inspector_opacity_slider.setValue(int(round(opacity * 100)))
            self.mask_inspector_opacity_slider.blockSignals(False)
        if hasattr(self, "mask_inspector_opacity_value_label"):
            self.mask_inspector_opacity_value_label.setText(f"{int(round(opacity * 100))}%")
        if hasattr(self, "mask_inspector_summary_label"):
            tname = getattr(track, "name", "M1")
            lname = getattr(layer, "name", "Mask")
            self.mask_inspector_summary_label.setText(
                f"Selected: {tname} → {lname}. Drag the mask on the video "
                "to move it. Drag a corner to resize. The X button deletes "
                "the mask. The mask is applied while the video is playing."
            )

    def _wire_mask_inspector_controls(self):
        """One-time wiring of the Mask Inspector controls.

        Only colour + opacity are wired here. Position / size / mode
        are not configurable in the inspector; the user positions and
        resizes the mask via the draggable overlay on the video.
        """
        if getattr(self, "_mask_inspector_wired", False):
            return
        self._mask_inspector_wired = True

        def _selected_mask_layer():
            if not hasattr(self, "timeline") or not self.timeline._timeline:
                return None, None
            sid = getattr(self.timeline, "_selected_layer_id", "") or ""
            for tr in self.timeline._timeline.tracks:
                for l in tr.layers:
                    if l.id == sid:
                        return l, tr
            return None, None

        def _sync_preview(l):
            try:
                self._apply_mask_to_preview()
            except Exception:
                pass
            try:
                if hasattr(self, "persist_project_mask_state"):
                    self.persist_project_mask_state()
            except Exception:
                pass

        def _on_opacity_changed(v):
            layer, _ = _selected_mask_layer()
            if layer is None:
                return
            opacity = max(0.0, min(1.0, float(v) / 100.0))
            try:
                layer.opacity = opacity
            except Exception:
                pass
            if hasattr(self, "mask_inspector_opacity_value_label"):
                self.mask_inspector_opacity_value_label.setText(f"{int(v)}%")
            _sync_preview(layer)

        self._mask_opacity_handler = _on_opacity_changed
        if hasattr(self, "mask_inspector_opacity_slider"):
            self.mask_inspector_opacity_slider.valueChanged.connect(_on_opacity_changed)

        # Color picker
        from PySide6.QtWidgets import QColorDialog
        def _on_color_clicked():
            from PySide6.QtGui import QColor
            layer, _ = _selected_mask_layer()
            current = QColor(str(getattr(layer, "color", "#000000")))
            chosen = QColorDialog.getColor(current, self, "Pick mask colour")
            if not chosen.isValid():
                return
            hex_str = chosen.name()
            if hasattr(self, "mask_inspector_color_btn"):
                self.mask_inspector_color_btn.setText(hex_str)
                self.mask_inspector_color_btn.setStyleSheet(
                    f"background-color: {hex_str}; color: #fff;"
                )
            if layer is not None:
                try:
                    layer.color = hex_str
                except Exception:
                    pass
                _sync_preview(layer)

        self._mask_color_handler = _on_color_clicked
        if hasattr(self, "mask_inspector_color_btn"):
            self.mask_inspector_color_btn.clicked.connect(_on_color_clicked)
