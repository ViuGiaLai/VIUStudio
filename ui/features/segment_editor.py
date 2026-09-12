import os
import re
import copy
from PySide6.QtWidgets import (
    QPushButton, QTextEdit, QMessageBox,
                             QColorDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from new_highlight_selector import auto_select_matches



class SegmentEditorMixin:
    def export_final_video(self, *, automatic: bool = False):
        self.preview_controller.export_final_video(automatic=automatic)

    def preview_five_seconds(self):
        self.preview_controller.preview_five_seconds()

    def preview_exact_frame(self):
        self.preview_controller.start_exact_frame_preview(show_dialog=True)

    def build_subtitle_preview_srt(self, start_seconds: float, duration_seconds: float):
        return self.preview_controller.build_subtitle_preview_srt(start_seconds, duration_seconds)

    def build_full_active_subtitle_srt(self):
        return self.preview_controller.build_full_active_subtitle_srt()

    def _format_compact_editor_timestamp(self, seconds: float) -> str:
        total_seconds = max(0, int(seconds))
        minutes, sec = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:02d}:{sec:02d}"

    def _segment_editor_display_rows(self):
        base_segments = self.current_segments or []
        translated_segments = self.current_translated_segments or []
        source_models = self.current_segment_models or []
        # Segment lists normally remain index-aligned, but imported SRTs and
        # manual timing edits may add/remove cues on only one side.  Retain a
        # fast timing lookup so the inspector can still show the matching
        # source transcript instead of an empty "Original" field.
        base_by_time = {
            (
                round(float(segment.get("start", 0.0)), 3),
                round(float(segment.get("end", 0.0)), 3),
            ): segment
            for segment in base_segments
            if isinstance(segment, dict)
        }
        # Timeline subtitle layers retain their visible `text` separately
        # from `_seg_dict`.  Keep this as the final recovery source for a
        # cue whose in-memory dictionary was rebuilt from SRT timing data.
        timeline_text_by_index = {}
        timeline_model = getattr(getattr(self, "timeline", None), "_timeline", None)
        for track in list(getattr(timeline_model, "tracks", []) or []):
            if str(getattr(getattr(track, "type", ""), "value", getattr(track, "type", ""))).lower() not in {"subtitle", "dub_subtitle"}:
                continue
            for layer in list(getattr(track, "layers", []) or []):
                metadata = getattr(layer, "metadata", {}) or {}
                try:
                    segment_index = int(metadata.get("_seg_index", -1))
                except (TypeError, ValueError):
                    continue
                if segment_index >= 0:
                    timeline_text_by_index[segment_index] = str(
                        getattr(layer, "text", "") or getattr(layer, "dub_text", "") or ""
                    )
        row_count = max(len(base_segments), len(translated_segments))
        rows = []
        for idx in range(row_count):
            base = base_segments[idx] if idx < len(base_segments) else {}
            translated = translated_segments[idx] if idx < len(translated_segments) else {}
            if translated:
                time_key = (
                    round(float(translated.get("start", 0.0)), 3),
                    round(float(translated.get("end", 0.0)), 3),
                )
                timed_base = base_by_time.get(time_key)
                if timed_base is not None:
                    base = timed_base
            reference = translated or base
            # Imported/manual translated segments do not always retain a
            # parallel original item at the same index.  Prefer the actual
            # transcript, then the source-text metadata retained by the
            # translation workflow, so the inspector never loses the source
            # text while the preview/timeline still has a visible cue.
            model_original = ""
            if idx < len(source_models):
                model_original = str(getattr(source_models[idx], "original_text", "") or "")
            original_text = str(
                translated.get("source_text", "")
                or translated.get("original_text", "")
                or translated.get("original", "")
                or base.get("original_text", "")
                or base.get("original", "")
                or base.get("text", "")
                or model_original
                or timeline_text_by_index.get(idx, "")
                or ""
            )
            shown_text = str(
                translated.get("final_text", "")
                or translated.get("text", "")
                or translated.get("translated", "")
                or original_text
            )
            rows.append(
                {
                    "segment_index": idx,
                    "start": float(reference.get("start", 0.0)),
                    "end": float(reference.get("end", 0.0)),
                    "original": original_text,
                    # Before translation this is the original transcript,
                    # which is also the text currently shown on screen.
                    "translated": shown_text,
                    "spoken": str(translated.get("tts_text") or translated.get("dubbing_vi") or translated.get("text", "")),
                    "subtitle_vi": str(translated.get("subtitle_vi") or translated.get("text", "")),
                    "dubbing_vi": str(translated.get("dubbing_vi") or translated.get("tts_text") or translated.get("text", "")),
                    "ratio": float(translated.get("ratio", 0.0) or 0.0),
                    "attempt_count": int(translated.get("attempt_count", 0) or 0),
                    "action_taken": str(translated.get("action_taken", "")),
                    "voice_speed": float(reference.get("voice_speed", 1.0)),
                    "manual_highlights": list(translated.get("manual_highlights", [])),
                }
            )
        return rows

    def _update_segment_spoken_status(self, index: int):
        row = self._find_segment_editor_row(index)
        if not row:
            return
        segment = {}
        if 0 <= index < len(self.current_translated_segments or []):
            segment = self.current_translated_segments[index] or {}
        subtitle_text = " ".join(str(segment.get("text", "") or "").split()).strip()
        spoken_text = " ".join(str(segment.get("tts_text") or segment.get("dubbing_vi") or segment.get("text", "")).split()).strip()
        # The per-segment status label was moved to the A2 Dub
        # Track Inspector. Update it there so the inspector reflects
        # whether the spoken text matches the subtitle.
        status_label = getattr(self, "audio_inspector_spoken_status_label", None)
        if status_label is not None:
            if spoken_text and subtitle_text and spoken_text != subtitle_text:
                status_label.setText("Spoken text differs from subtitle.")
            elif spoken_text:
                status_label.setText("Spoken text matches subtitle.")
            else:
                status_label.setText("")

    def _resolve_segment_voice_text(self, segment: dict) -> str:
        current = dict(segment or {})
        subtitle_text = " ".join(str(current.get("text", "") or "").split()).strip()
        if bool(current.get("voice_edited")):
            edited_text = " ".join(str(current.get("tts_text") or current.get("dubbing_vi") or "").split()).strip()
            if edited_text:
                return edited_text
        return subtitle_text

    def on_segment_spoken_text_edited(self, index: int, editor: QTextEdit):
        if getattr(self, "_syncing_segment_editor", False):
            return
        if not (0 <= index < len(self.current_translated_segments or [])):
            return
        value = " ".join(editor.toPlainText().split()).strip()
        segment = self.current_translated_segments[index]
        segment["tts_text"] = value
        segment["dubbing_vi"] = value
        segment["voice_edited"] = True
        self._voiceover_force_refresh = True
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._invalidate_dubbed_output_after_subtitle_edit(changed_indices={int(index)})
        self.persist_current_timeline_project_data()
        self._update_segment_spoken_status(index)
        self.refresh_ui_state()

    def use_spoken_text_for_subtitle(self, index: int):
        if not (0 <= index < len(self.current_translated_segments or [])):
            return
        segment = self.current_translated_segments[index]
        spoken_text = " ".join(str(segment.get("tts_text") or segment.get("dubbing_vi") or "").split()).strip()
        if not spoken_text:
            QMessageBox.information(self, "Nothing To Match", "This line does not have voice text yet.")
            return
        segment["text"] = spoken_text
        segment["subtitle_vi"] = spoken_text
        segment["voice_edited"] = True
        self._voiceover_force_refresh = True
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._sync_hidden_translated_text_from_segments()
        self._commit_subtitle_mutation(selected_index=index, changed_indices={int(index)})
        self.sync_segment_editor_rows()

    def _normalize_manual_highlight(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").replace("\u2029", " ").replace("\n", " ")).strip()

    def refresh_auto_keyword_highlights(self, force: bool = False):
        if not getattr(self, "current_translated_segments", None):
            return
        if not getattr(self, "subtitle_keyword_highlight_cb", None) or not self.subtitle_keyword_highlight_cb.isChecked():
            return
        if not hasattr(self, "subtitle_highlight_mode_combo") or self.subtitle_highlight_mode_combo.currentText().strip() not in ("Auto", "Auto + Manual"):
            return

        pending_indexes = []
        pending_texts = []
        for idx, segment in enumerate(self.current_translated_segments or []):
            text = ' '.join(str(segment.get("text") or "").replace("\n", " ").split()).strip()
            if not text:
                segment["auto_highlights"] = []
                continue
            cached_key = segment.get("_auto_highlights_source_text", "")
            if not force and cached_key == text and isinstance(segment.get("auto_highlights"), list):
                continue
            pending_indexes.append(idx)
            pending_texts.append(text)

        if not pending_texts:
            return

        self.log(f"[Auto Highlight] Generating highlight phrases for {len(pending_texts)} subtitle lines...")
        resolved_batches = [
            [candidate.text for candidate in auto_select_matches(text, max_keywords=2)]
            for text in pending_texts
        ]

        for idx, phrases in zip(pending_indexes, resolved_batches):
            segment = self.current_translated_segments[idx]
            text = ' '.join(str(segment.get("text") or "").replace("\n", " ").split()).strip()
            cleaned = []
            seen = set()
            lowered = text.lower()
            for phrase in phrases or []:
                normalized = self._normalize_manual_highlight(phrase)
                key = normalized.lower()
                if not normalized or key in seen or key not in lowered:
                    continue
                seen.add(key)
                cleaned.append(normalized)
            segment["auto_highlights"] = cleaned
            segment["_auto_highlights_source_text"] = text

        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)

    def _reconcile_manual_highlights(self, segment: dict):
        text = str(segment.get("text", ""))
        cleaned = []
        seen = set()
        for phrase in segment.get("manual_highlights", []):
            normalized = self._normalize_manual_highlight(phrase)
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen or key not in text.lower():
                continue
            seen.add(key)
            cleaned.append(normalized)
        segment["manual_highlights"] = cleaned

    def _sync_segment_highlight_chip_row(self, index: int):
        row = self._find_segment_editor_row(index)
        if not row:
            return
        chip_layout = row.get("highlight_chip_layout")
        placeholder = row.get("highlight_placeholder")
        if chip_layout is None:
            return

        while chip_layout.count():
            item = chip_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        highlights = []
        if index < len(self.current_translated_segments):
            highlights = list(self.current_translated_segments[index].get("manual_highlights", []))

        if placeholder:
            placeholder.setVisible(not highlights)

        for phrase in highlights:
            chip = QPushButton(f"[ {phrase} ]")
            chip.setCursor(Qt.PointingHandCursor)
            chip.setStyleSheet(
                "QPushButton { background-color: #173049; color: #9fe5ff; border: 1px solid #356081; border-radius: 999px; padding: 4px 10px; font-size: 11px; }"
                "QPushButton:hover { background-color: #214161; }"
            )
            chip.clicked.connect(lambda _=False, idx=index, value=phrase: self.remove_segment_manual_highlight(idx, value))
            chip_layout.addWidget(chip)
        chip_layout.addStretch()

    def add_segment_manual_highlight(self, index: int, editor: QTextEdit):
        if index < 0 or index >= len(self.current_translated_segments):
            QMessageBox.warning(self, "Highlight", "Please prepare translated subtitles first.")
            return

        selected_text = self._normalize_manual_highlight(editor.textCursor().selectedText())
        if not selected_text:
            QMessageBox.warning(self, "Highlight", "Select the translated text you want to highlight first.")
            return

        segment = self.current_translated_segments[index]
        segment.setdefault("manual_highlights", [])
        existing = {self._normalize_manual_highlight(item).lower() for item in segment.get("manual_highlights", [])}
        if selected_text.lower() not in existing:
            segment["manual_highlights"].append(selected_text)
        self._reconcile_manual_highlights(segment)
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._sync_segment_highlight_chip_row(index)
        self._sync_hidden_translated_text_from_segments()
        self.schedule_live_subtitle_preview_refresh()
        self.refresh_ui_state()

    def remove_segment_manual_highlight(self, index: int, phrase: str):
        if index < 0 or index >= len(self.current_translated_segments):
            return
        target = self._normalize_manual_highlight(phrase).lower()
        segment = self.current_translated_segments[index]
        segment["manual_highlights"] = [
            item for item in segment.get("manual_highlights", [])
            if self._normalize_manual_highlight(item).lower() != target
        ]
        self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
        self._sync_segment_highlight_chip_row(index)
        self._sync_hidden_translated_text_from_segments()
        self.schedule_live_subtitle_preview_refresh()
        self.refresh_ui_state()

    def _update_segment_highlight_button_state(self, index: int, editor: QTextEdit):
        row = self._find_segment_editor_row(index)
        if not row:
            return
        button = row.get("highlight_button")
        if button is None:
            return
        has_selection = bool(self._normalize_manual_highlight(editor.textCursor().selectedText()))
        button.setEnabled(has_selection)

    def _clear_segment_editor_rows(self):
        if not hasattr(self, "segment_editor_layout"):
            return
        while self.segment_editor_layout.count():
            item = self.segment_editor_layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif child_layout:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    child_widget = child_item.widget()
                    if child_widget:
                        child_widget.hide()
                        child_widget.setParent(None)
                        child_widget.deleteLater()




    def _get_effective_selected_segment_index(self, rows=None) -> int:
        rows = rows if rows is not None else self._segment_editor_display_rows()
        if not rows:
            return -1
        selected = int(getattr(self, "_selected_segment_index", -1))
        valid_indexes = [int(row.get("segment_index", idx)) for idx, row in enumerate(rows)]
        if selected in valid_indexes:
            return selected
        # The editor/timeline arrays are canonical.  ``live_preview_segments``
        # is a debounced preview snapshot and can briefly contain the
        # previous subtitle set after an import or edit.
        active_index = self._find_active_segment_index(self.media_player.position(), self.get_active_segments() or self.live_preview_segments)
        if active_index in valid_indexes:
            return active_index
        return valid_indexes[0]

    def set_selected_segment_index(self, index: int, *, sync_ui: bool = True):
        rows = self._segment_editor_display_rows()
        valid_indexes = [int(row.get("segment_index", idx)) for idx, row in enumerate(rows)]
        if not valid_indexes:
            self._selected_segment_index = -1
        elif index in valid_indexes:
            self._selected_segment_index = int(index)
        else:
            self._selected_segment_index = valid_indexes[0]
        if sync_ui:
            self.sync_segment_editor_rows()
        if hasattr(self, "_refresh_audio_inspector_dub_voice_buttons"):
            try:
                self._refresh_audio_inspector_dub_voice_buttons()
            except Exception:
                pass

    def on_timeline_segment_timing_edit_started(self, index: int, start: float, end: float):
        if self._suspend_timeline_undo:
            return
        last_entry = self._timeline_timing_undo_stack[-1] if self._timeline_timing_undo_stack else None
        if last_entry and str(last_entry.get("type", "timing")) == "timing" and int(last_entry.get("index", -1)) == int(index):
            if abs(float(last_entry.get("start", 0.0)) - float(start)) < 0.0001 and abs(float(last_entry.get("end", 0.0)) - float(end)) < 0.0001:
                return
        self._timeline_timing_undo_stack.append(
            {
                "type": "timing",
                "index": int(index),
                "start": float(start),
                "end": float(end),
            }
        )
        self._timeline_timing_redo_stack = []
        if len(self._timeline_timing_undo_stack) > 100:
            self._timeline_timing_undo_stack = self._timeline_timing_undo_stack[-100:]
        self._refresh_timeline_history_buttons()

    def on_timeline_segment_selected(self, index: int):
        self.set_selected_segment_index(index, sync_ui=True)
        if hasattr(self, "timeline"):
            self.timeline.set_active_segment_index(index)
        segments = self.get_active_segments() or getattr(self, "live_preview_segments", [])
        if segments and 0 <= index < len(segments):
            try:
                start_s = float(segments[index].get("start", 0.0) or 0.0)
                target_pos_ms = max(0, int(round(start_s * 1000.0)))
                current_pos = int(getattr(self.media_player, "position", lambda: 0)() or 0)
                if abs(current_pos - target_pos_ms) > 100:
                    self.set_position(target_pos_ms)
                else:
                    self.update_playback_subtitle_highlight(target_pos_ms)
            except Exception:
                pass

    def _show_default_inspector(self):
        self._switch_inspector("default")

    def _text_layers(self):
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return []
        return [layer for track in self.timeline._timeline.tracks for layer in track.layers
                if str(getattr(getattr(layer, "type", ""), "value", getattr(layer, "type", ""))).lower() == "text"]

    def _refresh_text_layer_preview(self, active_id=""):
        if not hasattr(self, "video_view") or not hasattr(self.video_view, "set_text_layers"):
            return
        from app.layers.text import TEXT_LAYER_EXPORT_SCALE
        # Use the same source-to-preview calibration as the editable
        # subtitle overlay. TextLayer.font_size is authored at source-video
        # scale (60 px at 100%), while QFont draws in preview pixels.
        render_h = max(1, int(getattr(self.video_view, "subtitle_render_height", 0) or 0))
        if render_h <= 1:
            _render_w, render_h = self._subtitle_render_dimensions()
        preview_rect = self.video_view.get_preview_canvas_rect()
        # Preview canvases can be smaller than the output canvas on laptops
        # or after moving the Preview/Timeline splitter. Preserve the real
        # source-to-preview scale in both directions; the old 1.0 floor kept
        # Text at export size instead of matching the visible canvas.
        preview_scale = max(
            0.01,
            float(preview_rect.height() or self.video_view.height() or 1.0) / max(1, render_h),
        )
        preview_text_scale = preview_scale * TEXT_LAYER_EXPORT_SCALE
        items = []
        is_editable = (
            not self._preview_is_playing()
            and str(active_id or "")
            and str(active_id or "") == str(getattr(self, "_preview_edit_layer_id", "") or "")
        )
        effective_active_id = str(active_id or "") if is_editable else ""
        if not bool(getattr(self, "_text_track_preview_visible", True)):
            self.video_view.set_text_layers([], active_id or getattr(self.timeline, "_selected_layer_id", ""))
            return
        for layer in self._text_layers():
            if not self._layer_is_active_at_preview_time(layer):
                continue
            transform = getattr(layer, "transform", None)
            items.append({
                "id": layer.id, "text": getattr(layer, "text", ""),
                "font_name": getattr(layer, "font_name", "Arial"),
                "font_size": max(1, int(round(float(getattr(layer, "font_size", 60)) * preview_text_scale))),
                "font_color": getattr(layer, "font_color", "#FFFFFF"),
                "background_color": getattr(layer, "background_color", ""),
                "background_opacity": max(0.0, min(1.0, float(getattr(layer, "background_opacity", 0.5) or 0.0))),
                "opacity": max(0.0, min(1.0, float(getattr(layer, "opacity", 1.0) if getattr(layer, "opacity", None) is not None else 1.0))),
                "font_bold": getattr(layer, "font_bold", False),
                "font_italic": getattr(layer, "font_italic", False),
                "font_underline": getattr(layer, "font_underline", False),
                # The shared Qt renderer scales its source-space padding with
                # the preview canvas just like glyph size, so export and the
                # editor use the same physical box geometry.
                "padding_scale": preview_scale,
                "x": getattr(transform, "x", .5) if transform else .5,
                "y": getattr(transform, "y", .5) if transform else .5,
            })
        self.video_view.set_text_layers(items, effective_active_id)
        if getattr(self.video_view, "text_overlay", None) is not None:
            self.video_view.text_overlay.set_editable(bool(is_editable))

    def _show_text_inspector_for_track(self, track, layer):
        self._switch_inspector("text")
        self._wire_text_inspector_controls()
        self._wire_layer_timing_controls("text")
        self._set_layer_timing_controls("text", layer)
        self.text_inspector_content.blockSignals(True)
        self.text_inspector_content.setPlainText(str(getattr(layer, "text", "")))
        self.text_inspector_content.blockSignals(False)
        self.text_inspector_font_combo.blockSignals(True)
        font_name = str(getattr(layer, "font_name", "Arial"))
        if self.text_inspector_font_combo.findText(font_name) < 0:
            self.text_inspector_font_combo.addItem(font_name)
        self.text_inspector_font_combo.setCurrentText(font_name)
        self.text_inspector_font_combo.blockSignals(False)
        size = int(getattr(layer, "font_size", 60))
        choices = [int(self.text_inspector_size_combo.itemData(i)) for i in range(self.text_inspector_size_combo.count())]
        nearest = min(choices, key=lambda percent: abs(60 * percent / 100.0 - size))
        self.text_inspector_size_combo.blockSignals(True)
        self.text_inspector_size_combo.setCurrentIndex(self.text_inspector_size_combo.findData(nearest))
        self.text_inspector_size_combo.blockSignals(False)
        color = str(getattr(layer, "font_color", "#FFFFFF"))
        self.text_inspector_color_btn.setText(color)
        self.text_inspector_color_btn.setStyleSheet(f"background-color: {color}; color: #fff;")
        bg = str(getattr(layer, "background_color", "") or "")
        self.text_inspector_background_btn.setText(bg or "None")
        self.text_inspector_background_btn.setStyleSheet(f"background-color: {bg or '#26364a'}; color: #fff;")
        opacity = max(0, min(100, int(round(float(getattr(layer, "background_opacity", 0.5) or 0.0) * 100))))
        self.text_inspector_background_opacity_slider.blockSignals(True)
        self.text_inspector_background_opacity_slider.setValue(opacity)
        self.text_inspector_background_opacity_slider.blockSignals(False)
        self.text_inspector_background_opacity_value.setText(f"{opacity}%")
        self.text_inspector_summary_label.setText(f"Selected: {getattr(track, 'name', 'T1 Text')} → {getattr(layer, 'name', 'Text')}. Drag it on the preview to move it.")

    def _wire_text_inspector_controls(self):
        if getattr(self, "_text_inspector_wired", False):
            return
        self._text_inspector_wired = True
        def selected():
            sid = getattr(self.timeline, "_selected_layer_id", "")
            return next((layer for layer in self._text_layers() if layer.id == sid), None)
        def changed():
            layer = selected()
            if layer:
                self._refresh_text_layer_preview(layer.id)
                self.schedule_timeline_project_persist()
        def content_changed():
            layer = selected()
            if layer:
                text = self.text_inspector_content.toPlainText()
                if not text.strip():
                    text = "Text"
                    self.text_inspector_content.blockSignals(True)
                    self.text_inspector_content.setPlainText(text)
                    self.text_inspector_content.blockSignals(False)
                layer.text = text
                first_line = next((line.strip() for line in text.splitlines() if line.strip()), "Text")
                layer.name = first_line[:24] or "Text"
                self.timeline._redraw(); changed()
        def size_changed(_index):
            layer = selected()
            if layer:
                percent = int(self.text_inspector_size_combo.currentData() or 100)
                layer.font_size = int(round(60 * percent / 100.0)); changed()
        def font_changed(value):
            layer = selected()
            if layer: layer.font_name = str(value); changed()
        def color_changed():
            from PySide6.QtWidgets import QColorDialog
            from PySide6.QtGui import QColor
            layer = selected()
            chosen = QColorDialog.getColor(QColor(getattr(layer, "font_color", "#FFFFFF")), self, "Pick text color")
            if layer and chosen.isValid():
                layer.font_color = chosen.name(); self.text_inspector_color_btn.setText(layer.font_color)
                self.text_inspector_color_btn.setStyleSheet(f"background-color: {layer.font_color}; color: #fff;"); changed()
        def background_changed():
            layer = selected()
            if layer is None: return
            current = QColor(str(getattr(layer, "background_color", "") or "#000000"))
            chosen = QColorDialog.getColor(current, self, "Choose Text Background Color")
            if chosen.isValid():
                layer.background_color = chosen.name()
                self.text_inspector_background_btn.setText(layer.background_color)
                self.text_inspector_background_btn.setStyleSheet(f"background-color: {layer.background_color}; color: #fff;"); changed()
        def background_opacity_changed(value):
            layer = selected()
            if layer is not None:
                value = max(0, min(100, int(value)))
                layer.background_opacity = value / 100.0
                self.text_inspector_background_opacity_value.setText(f"{value}%")
                changed()
        self.text_inspector_content.textChanged.connect(content_changed)
        self.text_inspector_size_combo.currentIndexChanged.connect(size_changed)
        self.text_inspector_font_combo.currentTextChanged.connect(font_changed)
        self.text_inspector_color_btn.clicked.connect(color_changed)
        self.text_inspector_background_btn.clicked.connect(background_changed)
        self.text_inspector_background_opacity_slider.valueChanged.connect(background_opacity_changed)

    def _on_logo_moved(self, layer, x, y, w, h):
        """Update the ImageLayer's transform from the logo overlay drag."""
        if self._preview_is_playing():
            return
        try:
            from app.layers.transform import Transform
            transform = getattr(layer, "transform", None) or Transform()
            transform.x = float(x)
            transform.y = float(y)
            transform.scale_x = float(w)
            transform.scale_y = float(h)
            layer.transform = transform
        except Exception:
            pass
        # Coalesce the disk write while the overlay emits drag events.
        self.schedule_timeline_project_persist()

    def _show_logo_inspector_for_track(self, track, layer=None):
        """Show the Logo Track Inspector populated with the selected L1 layer."""
        self._switch_inspector("logo")
        self._wire_layer_timing_controls("logo")
        if layer is not None:
            self._set_layer_timing_controls("logo", layer)
        self._sync_logo_inspector_for_layer(track, layer)

    def _sync_logo_inspector_for_layer(self, track, layer):
        """Sync Logo Inspector controls to match the selected ImageLayer."""
        self._wire_logo_inspector_controls()
        self._logo_overlay_layer = layer

        if layer is None:
            return

        # Push the layer's saved opacity, rotation, scale, position to the
        # inspector controls.
        opacity = float(getattr(layer, "opacity", 1.0) if getattr(layer, "opacity", None) is not None else 1.0)
        rotation = 0.0
        scale = 0.2
        pos_x = 0.0
        pos_y = 0.0
        try:
            transform = getattr(layer, "transform", None)
            if transform is not None:
                val_rot = getattr(transform, "rotation", 0.0)
                rotation = float(val_rot if val_rot is not None else 0.0)
                val_s = getattr(transform, "scale_x", 0.2)
                raw_s = float(val_s if val_s is not None else 0.2)
                scale = raw_s / 100.0 if raw_s > 1.0 else raw_s
                val_x = getattr(transform, "x", 0.0)
                raw_x = float(val_x if val_x is not None else 0.0)
                pos_x = raw_x / 100.0 if raw_x > 1.0 else raw_x
                val_y = getattr(transform, "y", 0.0)
                raw_y = float(val_y if val_y is not None else 0.0)
                pos_y = raw_y / 100.0 if raw_y > 1.0 else raw_y
        except Exception:
            pass
        if hasattr(self, "logo_inspector_scale_slider"):
            self.logo_inspector_scale_slider.blockSignals(True)
            self.logo_inspector_scale_slider.setValue(int(round(scale * 100)))
            self.logo_inspector_scale_slider.blockSignals(False)
        if hasattr(self, "logo_inspector_scale_value_label"):
            self.logo_inspector_scale_value_label.setText(f"{int(round(scale * 100))}%")

        if hasattr(self, "logo_inspector_opacity_slider"):
            self.logo_inspector_opacity_slider.blockSignals(True)
            self.logo_inspector_opacity_slider.setValue(int(round(opacity * 100)))
            self.logo_inspector_opacity_slider.blockSignals(False)
        if hasattr(self, "logo_inspector_opacity_value_label"):
            self.logo_inspector_opacity_value_label.setText(f"{int(round(opacity * 100))}%")

        if hasattr(self, "logo_inspector_rotation_slider"):
            self.logo_inspector_rotation_slider.blockSignals(True)
            self.logo_inspector_rotation_slider.setValue(int(round(rotation)))
            self.logo_inspector_rotation_slider.blockSignals(False)
        if hasattr(self, "logo_inspector_rotation_value_label"):
            self.logo_inspector_rotation_value_label.setText(f"{int(round(rotation))}°")

        if hasattr(self, "logo_inspector_pos_x_slider"):
            self.logo_inspector_pos_x_slider.blockSignals(True)
            self.logo_inspector_pos_x_slider.setValue(int(round(pos_x * 100)))
            self.logo_inspector_pos_x_slider.blockSignals(False)
        if hasattr(self, "logo_inspector_pos_x_value_label"):
            self.logo_inspector_pos_x_value_label.setText(f"{int(round(pos_x * 100))}%")

        if hasattr(self, "logo_inspector_pos_y_slider"):
            self.logo_inspector_pos_y_slider.blockSignals(True)
            self.logo_inspector_pos_y_slider.setValue(int(round(pos_y * 100)))
            self.logo_inspector_pos_y_slider.blockSignals(False)
        if hasattr(self, "logo_inspector_pos_y_value_label"):
            self.logo_inspector_pos_y_value_label.setText(f"{int(round(pos_y * 100))}%")

        if hasattr(self, "logo_inspector_summary_label"):
            tname = getattr(track, "name", "L1 Logo")
            lname = getattr(layer, "name", "Logo")
            self.logo_inspector_summary_label.setText(
                f"Selected: {tname} → {lname}. "
                "Adjust scale, position, rotation, and opacity below."
            )

    def _wire_logo_inspector_controls(self):
        """One-time wiring of the Logo Inspector's scale/opacity/rotation/position controls."""
        if getattr(self, "_logo_inspector_wired", False):
            return
        self._logo_inspector_wired = True

        def _on_scale_changed(value, l=None):
            if hasattr(self, "logo_inspector_scale_value_label"):
                self.logo_inspector_scale_value_label.setText(f"{int(value)}%")
            scale = max(0.02, min(1.0, float(value) / 100.0))
            if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_scale"):
                self.video_view.set_logo_scale(scale)
            if l is None:
                l = getattr(self, "_logo_overlay_layer", None)
            if l is not None:
                try:
                    from app.layers.transform import Transform
                    transform = getattr(l, "transform", None) or Transform()
                    transform.scale_x = scale
                    transform.scale_y = scale
                    l.transform = transform
                    self.schedule_timeline_project_persist()
                except Exception:
                    pass

        def _on_opacity_changed(value, l=None):
            if hasattr(self, "logo_inspector_opacity_value_label"):
                self.logo_inspector_opacity_value_label.setText(f"{int(value)}%")
            opacity = max(0.0, min(1.0, float(value) / 100.0))
            if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_opacity"):
                self.video_view.set_logo_opacity(opacity)
            if l is None:
                l = getattr(self, "_logo_overlay_layer", None)
            if l is not None:
                try:
                    l.opacity = opacity
                    self.schedule_timeline_project_persist()
                except Exception:
                    pass

        def _on_rotation_changed(value, l=None):
            if hasattr(self, "logo_inspector_rotation_value_label"):
                self.logo_inspector_rotation_value_label.setText(f"{int(value)}°")
            rotation = float(value)
            if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_rotation"):
                self.video_view.set_logo_rotation(rotation)
            if l is None:
                l = getattr(self, "_logo_overlay_layer", None)
            if l is not None:
                try:
                    from app.layers.transform import Transform
                    transform = getattr(l, "transform", None) or Transform()
                    transform.rotation = rotation
                    l.transform = transform
                    self.schedule_timeline_project_persist()
                except Exception:
                    pass

        def _on_pos_x_changed(value, l=None):
            if hasattr(self, "logo_inspector_pos_x_value_label"):
                self.logo_inspector_pos_x_value_label.setText(f"{int(value)}%")
            pos_x = max(0.0, min(1.0, float(value) / 100.0))
            pos_y = 0.0
            if l is None:
                l = getattr(self, "_logo_overlay_layer", None)
            if l is not None:
                try:
                    from app.layers.transform import Transform
                    transform = getattr(l, "transform", None) or Transform()
                    transform.x = pos_x
                    l.transform = transform
                    val_y = getattr(transform, "y", 0.0)
                    pos_y = float(val_y if val_y is not None else 0.0)
                    self.schedule_timeline_project_persist()
                except Exception:
                    pass
            elif hasattr(self, "logo_inspector_pos_y_slider"):
                pos_y = float(self.logo_inspector_pos_y_slider.value()) / 100.0
            if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_position"):
                self.video_view.set_logo_position(pos_x, pos_y)

        def _on_pos_y_changed(value, l=None):
            if hasattr(self, "logo_inspector_pos_y_value_label"):
                self.logo_inspector_pos_y_value_label.setText(f"{int(value)}%")
            pos_y = max(0.0, min(1.0, float(value) / 100.0))
            pos_x = 0.0
            if l is None:
                l = getattr(self, "_logo_overlay_layer", None)
            if l is not None:
                try:
                    from app.layers.transform import Transform
                    transform = getattr(l, "transform", None) or Transform()
                    transform.y = pos_y
                    l.transform = transform
                    val_x = getattr(transform, "x", 0.0)
                    pos_x = float(val_x if val_x is not None else 0.0)
                    self.schedule_timeline_project_persist()
                except Exception:
                    pass
            elif hasattr(self, "logo_inspector_pos_x_slider"):
                pos_x = float(self.logo_inspector_pos_x_slider.value()) / 100.0
            if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_position"):
                self.video_view.set_logo_position(pos_x, pos_y)

        def _apply_preset(x, y):
            if hasattr(self, "logo_inspector_pos_x_slider"):
                self.logo_inspector_pos_x_slider.setValue(int(round(x * 100)))
            if hasattr(self, "logo_inspector_pos_y_slider"):
                self.logo_inspector_pos_y_slider.setValue(int(round(y * 100)))

        def _on_replace_logo():
            from PySide6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Logo / Watermark Image", "",
                "Image Files (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)"
            )
            if file_path and os.path.exists(file_path):
                l = getattr(self, "_logo_overlay_layer", None)
                if l is not None:
                    l.source = file_path
                logos = [{"source": file_path, "x": 0.0, "y": 0.0, "width": 0.2, "height": 0.2, "opacity": 1.0}]
                if hasattr(self, "video_view") and hasattr(self.video_view, "set_logos"):
                    self.video_view.set_logos(logos, active_index=0)
                self.schedule_timeline_project_persist()

        def _on_reset_logo():
            if hasattr(self, "logo_inspector_scale_slider"):
                self.logo_inspector_scale_slider.setValue(20)
            if hasattr(self, "logo_inspector_opacity_slider"):
                self.logo_inspector_opacity_slider.setValue(100)
            if hasattr(self, "logo_inspector_rotation_slider"):
                self.logo_inspector_rotation_slider.setValue(0)
            _apply_preset(0.0, 0.0)

        def _on_delete_logo():
            if hasattr(self, "video_view") and hasattr(self.video_view, "clear_logo"):
                self.video_view.clear_logo()
            if hasattr(self, "timeline") and self.timeline is not None:
                try:
                    selected_id = getattr(self.timeline, "_selected_layer_id", "")
                    if selected_id:
                        self.timeline.delete_layer(selected_id)
                except Exception:
                    pass
            self._show_default_inspector()
            self.schedule_timeline_project_persist()

        if hasattr(self, "logo_inspector_scale_slider"):
            self.logo_inspector_scale_slider.valueChanged.connect(_on_scale_changed)
        if hasattr(self, "logo_inspector_opacity_slider"):
            self.logo_inspector_opacity_slider.valueChanged.connect(_on_opacity_changed)
        if hasattr(self, "logo_inspector_rotation_slider"):
            self.logo_inspector_rotation_slider.valueChanged.connect(_on_rotation_changed)
        if hasattr(self, "logo_inspector_pos_x_slider"):
            self.logo_inspector_pos_x_slider.valueChanged.connect(_on_pos_x_changed)
        if hasattr(self, "logo_inspector_pos_y_slider"):
            self.logo_inspector_pos_y_slider.valueChanged.connect(_on_pos_y_changed)

        if hasattr(self, "logo_pos_tl_btn"):
            self.logo_pos_tl_btn.clicked.connect(lambda: _apply_preset(0.0, 0.0))
        if hasattr(self, "logo_pos_tr_btn"):
            self.logo_pos_tr_btn.clicked.connect(lambda: _apply_preset(0.80, 0.0))
        if hasattr(self, "logo_pos_bl_btn"):
            self.logo_pos_bl_btn.clicked.connect(lambda: _apply_preset(0.0, 0.80))
        if hasattr(self, "logo_pos_br_btn"):
            self.logo_pos_br_btn.clicked.connect(lambda: _apply_preset(0.80, 0.80))
        if hasattr(self, "logo_pos_center_btn"):
            self.logo_pos_center_btn.clicked.connect(lambda: _apply_preset(0.40, 0.40))

        if hasattr(self, "logo_replace_btn"):
            self.logo_replace_btn.clicked.connect(_on_replace_logo)
        if hasattr(self, "logo_reset_btn"):
            self.logo_reset_btn.clicked.connect(_on_reset_logo)
        if hasattr(self, "logo_delete_btn"):
            self.logo_delete_btn.clicked.connect(_on_delete_logo)

    def _show_video_inspector_for_track(self, track, layer=None):
        """Show the Video Track Inspector (V1 Video)."""
        if not self._video_filter_inspector_available():
            self._switch_inspector("default")
            if hasattr(self, "default_inspector_summary_label"):
                self.default_inspector_summary_label.setText(
                    "Video filters are unavailable in the current preview mode. "
                    "Switch to GPU preview in Settings to edit them; the source "
                    "video, captions, and export workflow are still available."
                )
            return
        self._switch_inspector("video")
        if track is None:
            return
        if hasattr(self, "video_inspector_summary_label"):
            self.video_inspector_summary_label.setText(
                "Adjust the preset, intensity and fine-tune each channel below."
            )
        # Populate the inline filter controls
        self._wire_video_inspector_controls()
        self._refresh_video_inspector_status()

    def _wire_video_inspector_controls(self):
        """One-time wiring of the inline video filter controls."""
        if getattr(self, "_video_inspector_wired", False):
            return
        # Preset combo
        if hasattr(self, "video_inspector_preset_combo"):
            preset_keys = (
                list(self._video_filter_presets().keys())
                if hasattr(self, "_video_filter_presets")
                else ["original", "bright", "warm", "vivid", "cool", "soft"]
            )
            preset_labels = {
                "original": "Original",
                "bright": "Bright",
                "warm": "Warm",
                "vivid": "Vivid",
                "cool": "Cool",
                "soft": "Soft",
            }
            for key in preset_keys:
                label = preset_labels.get(str(key), str(key).title())
                self.video_inspector_preset_combo.addItem(label, str(key))
            self.video_inspector_preset_combo.currentIndexChanged.connect(
                self._on_video_inspector_preset_changed
            )
        # Intensity
        if hasattr(self, "video_inspector_intensity_slider"):
            self.video_inspector_intensity_slider.valueChanged.connect(
                self._on_video_inspector_intensity_changed
            )
            self.video_inspector_intensity_slider.sliderReleased.connect(
                self._on_video_inspector_intensity_released
            )
        # Adjust sliders
        if hasattr(self, "video_inspector_adjust_sliders"):
            for field_key, (slider, value_lbl) in self.video_inspector_adjust_sliders.items():
                slider.valueChanged.connect(
                    lambda v, lbl=value_lbl, fk=field_key: self._on_video_inspector_adjust_changed(fk, v, lbl)
                )
                slider.sliderReleased.connect(
                    lambda fk=field_key: self._on_video_inspector_adjust_released(fk)
                )
        # Reset
        if hasattr(self, "video_inspector_reset_btn"):
            self.video_inspector_reset_btn.clicked.connect(self._on_video_inspector_reset)
        self._video_inspector_wired = True
        # Initial UI sync
        self._sync_video_inspector_ui()

    def _sync_video_inspector_ui(self):
        if hasattr(self, "video_inspector_preset_combo"):
            try:
                key = self._normalize_video_filter_preset_key(
                    getattr(self, "_video_filter_preset_key", "original")
                )
                for i in range(self.video_inspector_preset_combo.count()):
                    if self.video_inspector_preset_combo.itemData(i) == key:
                        self.video_inspector_preset_combo.blockSignals(True)
                        self.video_inspector_preset_combo.setCurrentIndex(i)
                        self.video_inspector_preset_combo.blockSignals(False)
                        break
            except Exception:
                pass
        if hasattr(self, "video_inspector_intensity_slider"):
            try:
                self.video_inspector_intensity_slider.blockSignals(True)
                self.video_inspector_intensity_slider.setValue(int(self._video_filter_intensity))
                self.video_inspector_intensity_slider.blockSignals(False)
            except Exception:
                pass
        if hasattr(self, "video_inspector_intensity_value_label"):
            try:
                self.video_inspector_intensity_value_label.setText(str(int(self._video_filter_intensity)))
            except Exception:
                pass
        if hasattr(self, "video_inspector_adjust_sliders"):
            overrides = getattr(self, "_video_filter_adjust_overrides", {}) or {}
            for field_key, (slider, value_lbl) in self.video_inspector_adjust_sliders.items():
                try:
                    val = int(overrides.get(field_key, 0))
                except Exception:
                    val = 0
                try:
                    slider.blockSignals(True)
                    slider.setValue(val)
                    slider.blockSignals(False)
                except Exception:
                    pass
                value_lbl.setText(str(val))

    def _refresh_video_inspector_status(self):
        try:
            if not hasattr(self, "video_inspector_status_label"):
                return
            try:
                active = bool(self.has_active_video_filters())
            except Exception:
                active = False
            realtime = self._is_realtime_color_filter_state()

            if active and realtime:
                self.video_inspector_status_label.setText("✓ Realtime preview")
                self.video_inspector_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            elif active:
                self.video_inspector_status_label.setText("✓ Filter applied")
                self.video_inspector_status_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            else:
                self.video_inspector_status_label.setText("No filter applied")
                self.video_inspector_status_label.setStyleSheet("color: #888; font-weight: normal;")
            if hasattr(self, "video_inspector_reset_btn"):
                self.video_inspector_reset_btn.setEnabled(self._video_filter_inspector_available())
        except Exception as e:
            if hasattr(self, "log"):
                self.log(f"[Filter] Status refresh error: {e}")

    def _on_video_inspector_preset_changed(self, index: int):
        if not hasattr(self, "video_inspector_preset_combo"):
            return
        try:
            key = self.video_inspector_preset_combo.itemData(index)
            if not key:
                return
            self.on_video_filter_preset_selected(str(key))
        except Exception:
            pass
        # When the preset changes, the base values for each adjust
        # field change too. Refresh the slider UI so the user can see
        # what the new preset looks like at the current intensity.
        self._sync_video_inspector_ui()
        self._refresh_video_inspector_status()
        if hasattr(self, "refresh_ui_state"):
            self.refresh_ui_state()

    def _on_video_inspector_intensity_changed(self, value: int):
        if hasattr(self, "video_inspector_intensity_value_label"):
            self.video_inspector_intensity_value_label.setText(str(int(value)))
        try:
            self.on_video_filter_intensity_changed(int(value))
        except Exception:
            pass
        self._refresh_video_inspector_status()

    def _on_video_inspector_intensity_released(self):
        if hasattr(self, "on_video_filter_slider_released"):
            try:
                self.on_video_filter_slider_released()
            except Exception:
                pass
        self._refresh_video_inspector_status()

    def _on_video_inspector_adjust_changed(self, field_key: str, value: int, value_lbl):
        value_lbl.setText(str(int(value)))
        self.on_video_filter_adjust_changed(field_key, int(value))
        self._refresh_video_inspector_status()

    def _video_filter_inspector_available(self) -> bool:
        """Return whether the initialized preview backend supports realtime filters."""
        backend = getattr(self, "media_player", None)
        if backend is None or str(getattr(backend, "backend_name", "")) != "libmpv":
            return False
        if not bool(getattr(backend, "_gpu_next_enabled", False)):
            return False
        try:
            vo = backend._player.vo
            return any(
                str(item.get("name", "")) == "gpu-next"
                for item in (vo or [])
                if isinstance(item, dict)
            )
        except Exception:
            return False

    def _on_video_inspector_adjust_released(self, field_key: str):
        if hasattr(self, "on_video_filter_slider_released"):
            try:
                self.on_video_filter_slider_released()
            except Exception:
                pass
        self._refresh_video_inspector_status()

    def _on_video_inspector_reset(self):
        self.reset_video_filters()
        self._refresh_video_inspector_status()
        if hasattr(self, "refresh_ui_state"):
            self.refresh_ui_state()

    def _current_blur_track_for_inspector(self):
        """Return the Blur Track currently displayed in the Blur inspector."""
        if not hasattr(self, "blur_inspector_track_name_label"):
            return None, None
        target = self.blur_inspector_track_name_label.text().strip()
        if not target or target == "-":
            return None, None
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return None, None
        for t in self.timeline._timeline.tracks:
            if t.name == target:
                return t, target
        return None, None

    def on_blur_inspector_show_toggled(self, checked: bool):
        """Toggle whether the blur is rendered on the video preview.

        The blur layers remain in the timeline; only the visual mpv vf
        filter is toggled on/off via the media player's blur region.
        """
        track, _track_name = self._current_blur_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_show_on_preview"] = bool(checked)
        if hasattr(self, "media_player") and self.media_player is not None:
            if checked:
                # Re-apply the blur region to the media player.
                if hasattr(self, "apply_preview_blur_region"):
                    try:
                        self.apply_preview_blur_region(force=True)
                    except Exception:
                        pass
            else:
                # Clear the blur vf filter but keep the layer data.
                try:
                    self.media_player.clear_blur_region()
                except Exception:
                    pass
        if hasattr(self, "blur_inspector_summary_label"):
            state = "shown" if checked else "hidden"
            self.blur_inspector_summary_label.setText(
                f"The visual blur is currently {state} on the video preview."
            )

    def _switch_inspector(self, kind: str):
        if not hasattr(self, "inspector_stack"):
            return
        idx_map = {
            "subtitle": 0,
            "audio": 1,
            "blur": 2,
            "video": 3,
            "default": 4,
            "logo": 5,
            "mask": 6,
            "text": 7,
        }
        target = idx_map.get(kind, 4)
        if self.inspector_stack.currentIndex() != target:
            self.inspector_stack.setCurrentIndex(target)
        # The handle/toggle button is always visible so the user can
        # The handle/toggle UI was removed - the track inspector is
        # always expanded. No need to show/hide a handle.
        # Clicking a track layer opens the inspector (auto-expand shell).
        if kind in ("subtitle", "audio", "blur", "video", "logo", "mask", "text"):
            self.set_inspector_collapsed(False)

    def _current_audio_track_for_inspector(self):
        """Return the Track object currently displayed in the audio inspector."""
        if not hasattr(self, "audio_inspector_card") or not hasattr(self, "timeline"):
            return None, None
        if not self.timeline._timeline:
            return None, None
        if not hasattr(self, "audio_inspector_track_name_label"):
            return None, None
        target = self.audio_inspector_track_name_label.text().strip()
        if not target or target == "-":
            return None, None
        for t in self.timeline._timeline.tracks:
            if t.name == target:
                return t, target
        return None, None

    def on_audio_inspector_gain_changed(self, value: float):
        track, track_name = self._current_audio_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_gain_db"] = float(value)
        self._apply_audio_track_settings(track_name)

    def on_audio_inspector_speed_changed(self, value: float):
        track, track_name = self._current_audio_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_speed"] = float(value)
        self._apply_audio_track_settings(track_name)

    def on_audio_inspector_fade_in_changed(self, value: float):
        track, track_name = self._current_audio_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_fade_in"] = float(value)
        self._apply_audio_track_settings(track_name)

    def on_audio_inspector_fade_out_changed(self, value: float):
        track, track_name = self._current_audio_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_fade_out"] = float(value)
        self._apply_audio_track_settings(track_name)

    def on_audio_inspector_mute_toggled(self, checked: bool):
        track, track_name = self._current_audio_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_muted"] = bool(checked)
        track.muted = bool(checked)
        if track_name in ("A1 Audio", "A1"):
            self._mute_original = bool(checked)
        elif track_name in ("A2 Dub", "A2", "TS1"):
            self._mute_dubbed = bool(checked)
        if hasattr(self, "audio_inspector_mute_btn"):
            self.audio_inspector_mute_btn.setText(
                "Unmute Track" if checked else "Mute Track"
            )
        if hasattr(self, "track_label_bar"):
            self.track_label_bar.set_muted(track_name, bool(checked))
        self._apply_audio_track_settings(track_name)
        self.schedule_timeline_project_persist()

    def on_audio_inspector_solo_toggled(self, checked: bool):
        track, track_name = self._current_audio_track_for_inspector()
        if track is None:
            return
        if not isinstance(track.metadata, dict):
            track.metadata = {}
        track.metadata["_solo"] = bool(checked)
        track.solo = bool(checked)
        self._apply_audio_track_settings(track_name)
        self.schedule_timeline_project_persist()

    def _refresh_audio_inspector_dub_voice_buttons(self):
        """Enable/disable Dub Voice buttons and populate shared/tabs."""
        idx = int(getattr(self, "_selected_segment_index", -1))
        segments = self.get_active_segments() or []
        valid = 0 <= idx < len(segments)
        seg = segments[idx] if valid and isinstance(segments[idx], dict) else {}
        translation_ready = self._translation_phase_complete()
        for attr in (
            "audio_inspector_use_voice_btn",
            "audio_inspector_regenerate_voice_btn",
        ):
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setEnabled(valid and translation_ready)
        # Shared section: Original text
        orig_lbl = getattr(self, "inspector_original_text_label", None)
        orig_widget = getattr(self, "inspector_shared_original_label", None)
        if orig_lbl is not None:
            orig_text = ""
            if valid:
                row = self._find_segment_editor_row(idx)
                if row is not None:
                    orig_text = str(row.get("original", "") or "")
                if not orig_text:
                    orig_text = str(
                        seg.get("source_text", "")
                        or seg.get("original_text", "")
                        or seg.get("text", "")
                        or ""
                    )
            orig_lbl.setText(orig_text if orig_text else "")
            if orig_widget is not None:
                orig_widget.setVisible(bool(orig_text))

    def on_audio_inspector_regenerate_voice_clicked(self):
        if not self._translation_phase_complete():
            QMessageBox.information(self, "Voice Unavailable", "Complete the Translation phase before generating subtitle voice audio.")
            return
        idx = int(getattr(self, "_selected_segment_index", -1))
        segments = self.get_active_segments() or []
        if not (0 <= idx < len(segments)):
            return
        self.preview_segment_audio(idx)

    AUDIO_MIX_PRESETS = {
        "original_only": (100, 0),
        "prefer_original": (80, 20),
        "balanced": (100, 100),
        "prefer_dub": (20, 80),
        "dub_only": (0, 100),
    }

    def on_audio_mix_preset_changed(self):
        if not hasattr(self, "audio_mix_preset_combo"):
            return
        preset_key = str(self.audio_mix_preset_combo.currentData() or "").strip().lower()
        if preset_key in self.AUDIO_MIX_PRESETS:
            a1_val, a2_val = self.AUDIO_MIX_PRESETS[preset_key]
            if hasattr(self, "audio_a1_volume_slider"):
                self.audio_a1_volume_slider.blockSignals(True)
                self.audio_a1_volume_slider.setValue(a1_val)
                self.audio_a1_volume_slider.blockSignals(False)
            if hasattr(self, "audio_a1_volume_label"):
                self.audio_a1_volume_label.setText(f"{int(a1_val)}%")
            if hasattr(self, "audio_a2_volume_slider"):
                self.audio_a2_volume_slider.blockSignals(True)
                self.audio_a2_volume_slider.setValue(a2_val)
                self.audio_a2_volume_slider.blockSignals(False)
            if hasattr(self, "audio_a2_volume_label"):
                self.audio_a2_volume_label.setText(f"{int(a2_val)}%")
            self._apply_audio_mix_to_tracks(a1_val, a2_val)

    def on_audio_a1_volume_changed(self, value: int):
        if hasattr(self, "audio_a1_volume_label"):
            self.audio_a1_volume_label.setText(f"{int(value)}%")
        self._sync_audio_track_volume("A1 Audio", int(value))
        self._set_audio_mix_preset_custom()
        self.schedule_timeline_project_persist()

    def on_audio_a2_volume_changed(self, value: int):
        if hasattr(self, "audio_a2_volume_label"):
            self.audio_a2_volume_label.setText(f"{int(value)}%")
        self._sync_audio_track_volume("A2 Dub", int(value))
        self._sync_audio_track_volume("TS1", int(value))
        self._set_audio_mix_preset_custom()
        self.schedule_timeline_project_persist()

    def _apply_audio_mix_to_tracks(self, a1_val: int, a2_val: int):
        self._sync_audio_track_volume("A1 Audio", a1_val)
        self._sync_audio_track_volume("A2 Dub", a2_val)
        self._sync_audio_track_volume("TS1", a2_val)
        self.schedule_timeline_project_persist()

    def _sync_audio_track_volume(self, track_name: str, volume: int):
        if not hasattr(self, "timeline") or self.timeline is None or not self.timeline._timeline:
            return
        for t in self.timeline._timeline.tracks:
            if t.name == track_name:
                if not isinstance(t.metadata, dict):
                    t.metadata = {}
                t.metadata["_volume"] = float(volume)
                self._apply_audio_track_settings(track_name)
                break

    def _set_audio_mix_preset_custom(self):
        if not hasattr(self, "audio_mix_preset_combo"):
            return
        idx = self.audio_mix_preset_combo.findData("custom")
        if idx >= 0 and self.audio_mix_preset_combo.currentIndex() != idx:
            self.audio_mix_preset_combo.setCurrentIndex(idx)

    def _apply_audio_track_settings(self, track_name: str):
        """Apply per-track volume/gain/mute to the underlying media player.

        Maps the timeline track name to the media player:
          "A1 Audio" -> QMediaPlayer #1 (original sidecar)
          "A2 Dub" / "TS1" -> QMediaPlayer #2 (dubbed sidecar)
        """
        if not hasattr(self, "media_player") or self.media_player is None:
            return
        try:
            if track_name == "A1 Audio":
                vol = self._compute_audio_track_volume(track_name, base=100.0)
                gain_db = self._get_audio_track_gain_db(track_name)
                effective = vol * (10 ** (gain_db / 20.0))
                effective = max(0.0, min(200.0, effective))
                muted = self._is_audio_track_muted(track_name)
                if hasattr(self.media_player, "set_mute_original"):
                    self.media_player.set_mute_original(muted or (effective <= 0.0))
                if hasattr(self.media_player, "set_original_volume"):
                    self.media_player.set_original_volume(effective)
            elif track_name in ("A2 Dub", "TS1"):
                vol = self._compute_audio_track_volume(track_name, base=100.0)
                gain_db = self._get_audio_track_gain_db(track_name)
                effective = vol * (10 ** (gain_db / 20.0))
                effective = max(0.0, min(200.0, effective))
                muted = self._is_audio_track_muted(track_name)
                if hasattr(self.media_player, "set_mute_dubbed"):
                    self.media_player.set_mute_dubbed(muted or (effective <= 0.0))
                if hasattr(self.media_player, "set_dubbed_volume"):
                    self.media_player.set_dubbed_volume(effective)
        except Exception:
            pass

    def _get_audio_track_meta(self, track_name: str) -> dict:
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return {}
        for t in self.timeline._timeline.tracks:
            if t.name == track_name:
                if not isinstance(t.metadata, dict):
                    t.metadata = {}
                return t.metadata
        return {}

    def _get_audio_track_volume(self, track_name: str) -> float:
        meta = self._get_audio_track_meta(track_name)
        default_vol = 50.0 if track_name.startswith("A1") else 100.0
        try:
            return float(meta.get("_volume", default_vol))
        except (TypeError, ValueError):
            return default_vol

    def _get_audio_track_gain_db(self, track_name: str) -> float:
        meta = self._get_audio_track_meta(track_name)
        try:
            return float(meta.get("_gain_db", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _is_audio_track_muted(self, track_name: str) -> bool:
        meta = self._get_audio_track_meta(track_name)
        if bool(meta.get("_muted", False)):
            return True
        # A soloed track is never muted by another track's solo. If
        # multiple tracks are soloed, all of them play; the rest are muted.
        if bool(meta.get("_solo", False)):
            return False
        # If any OTHER audio track is soloed, this one is muted.
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return False
        for t in self.timeline._timeline.tracks:
            if t.name == track_name:
                continue
            if str(getattr(t, "name", "")).startswith(("A1", "A2")):
                if isinstance(t.metadata, dict) and bool(t.metadata.get("_solo", False)):
                    return True
        return False

    def _compute_audio_track_volume(self, track_name: str, base: float = 100.0) -> float:
        meta = self._get_audio_track_meta(track_name)
        default_base = 50.0 if track_name.startswith("A1") else base
        try:
            v = float(meta.get("_volume", default_base))
        except (TypeError, ValueError):
            v = default_base
        return max(0.0, min(200.0, v))

    def on_track_mute_toggled(self, track_name: str, is_muted: bool):
        """Handle timeline audio track mute toggling.
        Maps timeline mute to per-track mute on the dual-track player.
        """
        # TS1 is a subtitle/edit track even though each DubSubtitleLayer may
        # carry a generated voice path. Subtitle selection/visibility must
        # never alter the dubbed-audio channel.
        if track_name not in ("A1 Audio", "A2 Dub"):
            return
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        for t in self.timeline._timeline.tracks:
            if t.name == track_name:
                t.muted = is_muted
                if not isinstance(t.metadata, dict):
                    t.metadata = {}
                t.metadata["_muted"] = bool(is_muted)

        muted = bool(is_muted)
        if track_name == "A1 Audio":
            self._mute_original = muted
            if hasattr(self, "media_player"):
                try:
                    self.media_player.set_mute_original(muted)
                except Exception:
                    pass
        elif track_name == "A2 Dub":
            self._mute_dubbed = muted
            if hasattr(self, "media_player"):
                try:
                    self.media_player.set_mute_dubbed(muted)
                except Exception:
                    pass

        if hasattr(self, "track_label_bar"):
            self.track_label_bar.set_muted(track_name, muted)

        if hasattr(self, "audio_inspector_mute_btn"):
            try:
                curr_track, curr_name = self._current_audio_track_for_inspector()
                if curr_name == track_name:
                    self.audio_inspector_mute_btn.blockSignals(True)
                    self.audio_inspector_mute_btn.setChecked(muted)
                    self.audio_inspector_mute_btn.setText("Unmute Track" if muted else "Mute Track")
                    self.audio_inspector_mute_btn.blockSignals(False)
            except Exception:
                pass

        self.schedule_timeline_project_persist()
        self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)

    def on_track_blur_toggled(self, track_name: str, is_on: bool):
        """Handle B1 track label click - toggle blur effect."""
        if hasattr(self, "timeline") and self.timeline._timeline:
            for track in self.timeline._timeline.tracks:
                if track.name == track_name or track.name == "B1":
                    track.visible = bool(is_on)
        if not hasattr(self, "blur_area_btn"):
            return
        self.blur_area_btn.blockSignals(True)
        self.blur_area_btn.setChecked(bool(is_on))
        self.blur_area_btn.blockSignals(False)
        try:
            self.toggle_blur_effect_enabled(bool(is_on))
        except Exception:
            pass
        self.schedule_timeline_project_persist(blur_state=True)

    def on_track_logo_toggled(self, track_name: str, is_shown: bool):
        """Handle L1 track label click - hide or show the logo overlay."""
        self._logo_track_preview_visible = bool(is_shown)
        if hasattr(self, "timeline") and self.timeline._timeline:
            for track in self.timeline._timeline.tracks:
                if track.name == track_name or track.name == "L1 Logo":
                    track.visible = bool(is_shown)
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_logo_track_visible"):
            self.video_view.set_logo_track_visible(self._logo_track_preview_visible)
        # Force the next timed refresh to respect the new track state even if
        # the playhead remains at the same timestamp.
        self._timed_layer_preview_signature = None
        self.schedule_timeline_project_persist()
        if not hasattr(self, "video_view"):
            return
        if is_shown:
            # Restore only logos active at the current playhead.  This keeps
            # Hide/Show consistent with timed logo segments.
            self.refresh_timed_layer_preview()
        else:
            # Hide the logo overlay
            if hasattr(self.video_view, "clear_logo"):
                self.video_view.clear_logo()

    def on_track_mask_toggled(self, track_name: str, is_shown: bool):
        """Handle M1 track label click - show or hide the mask filter."""
        self._mask_track_preview_visible = bool(is_shown)
        if hasattr(self, "timeline") and self.timeline._timeline:
            for track in self.timeline._timeline.tracks:
                if track.name == track_name or track.name == "M1":
                    track.visible = bool(is_shown)
        self.schedule_timeline_project_persist(mask_state=True)
        if not hasattr(self, "media_player"):
            return
        if is_shown:
            # Re-apply the M1 mask filter from the timeline.
            try:
                self._apply_mask_to_preview()
            except Exception:
                pass
            # Re-show the mask overlay. A label click should restore M1 even
            # when another layer is selected (or the selection was cleared).
            try:
                if hasattr(self, "timeline") and self.timeline._timeline:
                    sid = getattr(self.timeline, "_selected_layer_id", "")
                    for tr in self.timeline._timeline.tracks:
                        if tr.name != "M1" or not tr.layers:
                            continue
                        layer = next((item for item in tr.layers if item.id == sid), tr.layers[0])
                        self._show_mask_overlay(tr, layer)
                        return
            except Exception:
                pass
        else:
            try:
                self.media_player.clear_mask_region()
            except Exception:
                pass
            if hasattr(self, "video_view") and hasattr(self.video_view, "clear_mask_region"):
                try:
                    self.video_view.clear_mask_region()
                except Exception:
                    pass

    def on_track_text_toggled(self, track_name: str, is_shown: bool):
        """Show or hide every Text layer in the T1 track without changing export data."""
        self._text_track_preview_visible = bool(is_shown)
        timeline = getattr(self, "timeline", None)
        if timeline is not None and timeline._timeline:
            for track in timeline._timeline.tracks:
                if track.name == track_name or track.name == "T1 Text":
                    track.visible = bool(is_shown)
            timeline._redraw()
            self._refresh_text_layer_preview(getattr(timeline, "_selected_layer_id", ""))
            if hasattr(self, "track_label_bar"):
                self.track_label_bar.set_text_shown(track_name, bool(is_shown))
            self.log(f"[Timeline] {'Shown' if is_shown else 'Hidden'} text track: {track_name}")
            self.schedule_timeline_project_persist()
            return

    def on_track_subtitle_toggled(self, track_name: str, is_shown: bool):
        """Temporarily show or hide TS1 subtitle output without deleting data."""
        self._subtitle_track_preview_visible = bool(is_shown)
        if hasattr(self, "timeline") and self.timeline._timeline:
            for track in self.timeline._timeline.tracks:
                if track.name == track_name or track.name == "TS1":
                    track.visible = bool(is_shown)
        if hasattr(self, "video_view") and hasattr(self.video_view, "set_subtitle_track_visible"):
            self.video_view.set_subtitle_track_visible(self._subtitle_track_preview_visible)
        if not is_shown:
            try:
                self.media_player.clear_subtitle()
            except Exception:
                pass
            # clear_subtitle() removes MPV's external ASS track.  Its source
            # path may still be the same on Show, so invalidate the UI-level
            # cache as well; otherwise sync_live_subtitle_preview() believes
            # the removed track is already loaded and never restores it.
            self._loaded_live_ass_path = ""
            self._loaded_live_ass_signature = None
            if hasattr(self, "video_view"):
                try:
                    self.video_view.subtitle_item.hide()
                except Exception:
                    pass
        else:
            try:
                self.sync_live_subtitle_preview()
            except Exception:
                pass
        if hasattr(self, "track_label_bar"):
            self.track_label_bar.set_subtitle_shown(track_name, bool(is_shown))
        self.log(f"[Timeline] {'Shown' if is_shown else 'Hidden'} subtitle track: {track_name}")
        self.schedule_timeline_project_persist()

    def on_track_label_selected(self, track_name: str):
        """Select the first layer in a track; label clicks never toggle state."""
        timeline = getattr(self, "timeline", None)
        if timeline is None or not timeline._timeline:
            return
        for track in timeline._timeline.tracks:
            if track.name == track_name and track.layers:
                layer_id = track.layers[0].id
                timeline.select_layer(layer_id)
                # select_layer updates the canvas only; label clicks must
                # also route through the inspector/preview selection path.
                self.on_timeline_layer_selected(layer_id)
                return

    def _sync_timeline_mute_to_gui(self):
        """Pull the current timeline track mute state into the GUI and backend."""
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return
        a1_muted = False
        a2_muted = False
        for t in self.timeline._timeline.tracks:
            meta = t.metadata if isinstance(t.metadata, dict) else {}
            if t.name == "A1 Audio":
                a1_muted = bool(t.muted) or bool(meta.get("_muted", False))
                t.muted = a1_muted
            elif t.name == "A2 Dub":
                a2_muted = bool(t.muted) or bool(meta.get("_muted", False))
                t.muted = a2_muted
        self._mute_original = a1_muted
        self._mute_dubbed = a2_muted
        if hasattr(self, "media_player"):
            try:
                self.media_player.set_mute_original(a1_muted)
            except Exception:
                pass
            try:
                self.media_player.set_mute_dubbed(a2_muted)
            except Exception:
                pass
        if hasattr(self, "track_label_bar"):
            self.track_label_bar.set_muted("A1 Audio", a1_muted)
            self.track_label_bar.set_muted("A2 Dub", a2_muted)
        if hasattr(self, "audio_inspector_mute_btn"):
            try:
                curr_track, curr_name = self._current_audio_track_for_inspector()
                if curr_name == "A1 Audio":
                    self.audio_inspector_mute_btn.blockSignals(True)
                    self.audio_inspector_mute_btn.setChecked(a1_muted)
                    self.audio_inspector_mute_btn.setText("Unmute Track" if a1_muted else "Mute Track")
                    self.audio_inspector_mute_btn.blockSignals(False)
                elif curr_name == "A2 Dub":
                    self.audio_inspector_mute_btn.blockSignals(True)
                    self.audio_inspector_mute_btn.setChecked(a2_muted)
                    self.audio_inspector_mute_btn.setText("Unmute Track" if a2_muted else "Mute Track")
                    self.audio_inspector_mute_btn.blockSignals(False)
            except Exception:
                pass

    def _sync_timeline_audio_volumes_to_gui(self):
        """Restore persisted A1/A2 levels into both controls and playback.

        Timeline metadata is the persisted source of truth. Previously only
        mute state was restored when reopening a project, so the sliders went
        back to 50/100 while the timeline still contained the user's values.
        Preview and export could consequently use different gains.
        """
        if not hasattr(self, "timeline") or not self.timeline._timeline:
            return

        saved = {}
        for track in self.timeline._timeline.tracks:
            meta = track.metadata if isinstance(track.metadata, dict) else {}
            try:
                if "_volume" in meta:
                    saved[track.name] = max(0, min(200, int(round(float(meta["_volume"])))))
            except (TypeError, ValueError):
                continue

        a1_value = saved.get("A1 Audio")
        a2_track_name = "A2 Dub" if "A2 Dub" in saved else "TS1"
        a2_value = saved.get(a2_track_name)
        for value, slider_attr, label_attr in (
            (a1_value, "audio_a1_volume_slider", "audio_a1_volume_label"),
            (a2_value, "audio_a2_volume_slider", "audio_a2_volume_label"),
        ):
            if value is None:
                continue
            slider = getattr(self, slider_attr, None)
            if slider is not None:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)
            label = getattr(self, label_attr, None)
            if label is not None:
                label.setText(f"{value}%")

        if a1_value is not None:
            self._apply_audio_track_settings("A1 Audio")
        if a2_value is not None:
            self._apply_audio_track_settings(a2_track_name)

    def _is_active_timeline_audio_track_muted(self) -> bool:
        track_mutes = self._timeline_audio_track_mutes()
        if not track_mutes:
            return False
        a1_muted, a2_muted = track_mutes
        mode = str(getattr(self, "_preview_audio_track_mode", "original") or "original").strip().lower()
        if mode != "dubbed":
            return a1_muted
        dubbed_audio_kind, _dubbed_path = self._resolve_preview_dubbed_playback_source()
        if dubbed_audio_kind == "voice":
            return a2_muted
        if dubbed_audio_kind == "mixed":
            return a1_muted and a2_muted
        return a1_muted

    def on_add_timeline_layer(self, layer_type: str = "subtitle"):
        if not hasattr(self, "timeline"):
            return
        if self._preview_is_playing():
            return

        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        if layer_type != "subtitle" and (not video_path or not os.path.exists(video_path)):
            QMessageBox.information(
                self,
                "Select Video First",
                "Open a valid video before adding a visual layer.",
            )
            return

        tl = self.timeline._timeline
        if not tl:
            return

        from app.layers.base import LayerType
        from app.layers.sync_bridge import find_or_create_track

        if layer_type == "subtitle":
            # TS1 is driven from the segment lists, not the legacy Subtitle
            # track. Insert at the playhead so the normal timeline, preview,
            # editor, export and project persistence paths all stay aligned.
            try:
                start = max(0.0, self.timeline_position_seconds() if hasattr(self, "timeline_position_seconds") else float(self.media_player.position()) / 1000.0)
            except Exception:
                start = 0.0
            duration = max(0.0, float(getattr(tl, "duration", 0.0) or 0.0))
            end = start + 2.0
            if duration > 0.0:
                end = min(end, duration)
                if end - start < 0.20:
                    start = max(0.0, end - 2.0)
            if end - start < 0.05:
                end = start + 2.0

            translated_exists = bool(getattr(self, "current_translated_segments", None))
            if not hasattr(self, "current_segments") or self.current_segments is None:
                self.current_segments = []
            if not hasattr(self, "current_translated_segments") or self.current_translated_segments is None:
                self.current_translated_segments = []

            active_segments = self.current_translated_segments if translated_exists else self.current_segments
            index = next(
                (idx for idx, segment in enumerate(active_segments)
                 if float(segment.get("start", 0.0) or 0.0) > start),
                len(active_segments),
            )
            source_segment = {"start": start, "end": end, "text": "New subtitle", "words": []}
            translated_segment = {
                "start": start,
                "end": end,
                "text": "New subtitle",
                "source_text": "New subtitle",
                "tts_text": "New subtitle",
                "provider": "manual",
            }
            history_entry = {
                "type": "insert",
                "index": int(index),
                "selected_before": int(getattr(self, "_selected_segment_index", -1)),
                "selected_after": int(index),
                "current_before": [],
                "current_after": [copy.deepcopy(source_segment)],
                "translated_before": [],
                "translated_after": [copy.deepcopy(translated_segment)] if translated_exists else [],
            }
            self.current_segments.insert(min(index, len(self.current_segments)), source_segment)
            if translated_exists:
                self.current_translated_segments.insert(min(index, len(self.current_translated_segments)), translated_segment)
            # Segment insertion changes the source index mapping used by the
            # optional one-line display cache, so always rebuild it from the
            # current project data.
            self._single_line_split_cache = None
            self.current_segment_models = self._dict_segments_to_models(self.current_segments, translated=False)
            if translated_exists:
                self.current_translated_segment_models = self._dict_segments_to_models(self.current_translated_segments, translated=True)
                self._sync_hidden_translated_text_from_segments()
            self._sync_hidden_transcript_text_from_segments()
            self._timeline_timing_undo_stack.append(history_entry)
            self._timeline_timing_redo_stack = []
            if len(self._timeline_timing_undo_stack) > 100:
                self._timeline_timing_undo_stack = self._timeline_timing_undo_stack[-100:]
            self._refresh_timeline_history_buttons()
            self.set_selected_segment_index(index, sync_ui=True)
            self.timeline.set_active_segment_index(index)
            self._commit_subtitle_mutation(selected_index=index)
            self.show_subtitle_inspector_details()
            self.log(f"[Subtitle] Added manual TS1 segment at {start:.2f}s.")
            return

        elif layer_type == "text":
            from app.layers.text import TextLayer
            text_track = find_or_create_track(tl, "T1 Text", LayerType.TEXT, 80)
            idx = len(text_track.layers)
            layer = TextLayer(
                name=f"Text {idx + 1}",
                text="New text layer",
                start=0.0,
                end=tl.duration if tl.duration > 0 else 10.0,
            )
            layer.font_size = 60
            # Match the subtitle defaults so identical Text/Subtitles size
            # values use the same family and weight out of the box.
            layer.font_name = "Segoe UI"
            layer.font_bold = True
            layer.transform.x = 0.5
            layer.transform.y = 0.5
            layer.z_index = idx
            text_track.layers.append(layer)
            if hasattr(self.timeline, "_track_heights"):
                self.timeline._track_heights[text_track.id] = text_track.height or 80
            self.timeline._redraw()
            self.timeline._selected_layer_id = layer.id
            if hasattr(self, "_sync_track_labels"):
                self._sync_track_labels()
            # A newly-created Text layer must enter the exact same selection
            # path as a layer clicked in the timeline.  Updating only the
            # inspector left `_preview_edit_layer_id` empty, so the native MPV
            # text overlay was not activated consistently and the layer could
            # appear to have been added only on the timeline.
            self._timed_layer_preview_signature = None
            self.on_timeline_layer_selected(layer.id)
            self.schedule_timeline_project_persist()

        elif layer_type == "image":
            from app.layers.image import ImageLayer
            img_track = find_or_create_track(tl, "I1 Image", LayerType.IMAGE, 80)
            idx = len(img_track.layers)
            layer = ImageLayer(
                name=f"Image {idx + 1}",
                source="",
                start=0.0,
                end=min(tl.duration, 10.0) if tl.duration > 0 else 10.0,
            )
            layer.z_index = idx
            img_track.layers.append(layer)
            self.timeline._redraw()

        elif layer_type == "logo":
            from app.layers.image import ImageLayer
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Logo / Watermark Image", "",
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.svg);;All Files (*)"
            )
            if not path:
                return
            img_track = find_or_create_track(tl, "L1 Logo", LayerType.IMAGE, 80)
            # L1 supports multiple independent logo layers.  Keep existing
            # layers intact; selecting a timeline layer determines which
            # logo is currently editable in the preview overlay.
            idx = len(img_track.layers)
            dur = tl.duration if tl.duration > 0 else 10.0
            from app.layers.transform import Transform
            layer = ImageLayer(
                name=f"Logo {idx + 1}",
                source=path,
                start=0.0,
                end=dur,
                transform=Transform(x=0.08, y=0.08, scale_x=0.2, scale_y=0.2),
            )
            layer.z_index = idx
            # Mark as watermark so the preview positions it correctly
            layer.metadata["_is_watermark"] = True
            img_track.layers.append(layer)
            # Register the new track's height in the timeline so it gets
            # a real draw slot.
            if hasattr(self.timeline, "_track_heights"):
                self.timeline._track_heights[img_track.id] = (
                    img_track.height or 80
                )
            self.timeline._redraw()
            if hasattr(self, "_sync_track_labels"):
                self._sync_track_labels()
            # Show the logo overlay immediately (no need to click the
            # layer first) and persist the logo state.
            try:
                self._show_logo_overlay(img_track, layer)
            except Exception:
                pass
            self.schedule_timeline_project_persist()

        elif layer_type == "blur":
            from app.layers.blur import BlurLayer
            blur_track = find_or_create_track(tl, "B1", LayerType.BLUR, 60)
            # Register the new track's height in the timeline so it gets a
            # real draw slot (otherwise the track silently uses the default
            # height and may not be visible).
            if hasattr(self.timeline, "_track_heights"):
                self.timeline._track_heights[blur_track.id] = (
                    blur_track.height or 60
                )
            idx = len(blur_track.layers)
            # Stagger each new blur layer slightly so all layers are
            # visible in the timeline (otherwise overlapping layers at
            # the same position hide each other).
            stagger = idx % 4
            base_y = 0.78 - stagger * 0.04
            base_x = 0.15 + (stagger % 2) * 0.05
            # New Blur layers are global by default.  Their geometry can be
            # narrowed later in the inspector/timeline, but creating one must
            # not unexpectedly limit it to a five-second window at the
            # current playhead.
            blur_start = 0.0
            blur_end = float(tl.duration) if float(getattr(tl, "duration", 0.0) or 0.0) > 0.0 else 10.0
            layer = BlurLayer(
                name=f"Blur {idx + 1}",
                position_x=float(base_x),
                position_y=float(base_y),
                width=0.7,
                height=0.18,
                blur_strength=36.0,
                start=blur_start,
                end=blur_end,
            )
            layer.z_index = idx
            blur_track.layers.append(layer)
            # Force a redraw so the new track + layer are visible.
            self.timeline._redraw()
            # Auto-scroll the timeline vertically so the new B1
            # track is in view (it sits below V1 + A1 by default).
            try:
                if hasattr(self.timeline, "verticalScrollBar"):
                    y_offset = 0
                    if hasattr(self.timeline, "RULER_HEIGHT"):
                        y_offset = int(self.timeline.RULER_HEIGHT)
                    for tr in tl.tracks:
                        if tr.id == blur_track.id:
                            break
                        y_offset += int(
                            self.timeline._track_heights.get(
                                tr.id, self.timeline.TRACK_DEFAULT_H
                            )
                        )
                    bar = self.timeline.verticalScrollBar()
                    # Make sure the scroll bar range reflects the new scene
                    # size (it is normally auto-sized by the QGraphicsView,
                    # but the range can lag on first update).
                    viewport_h = int(self.timeline.viewport().height())
                    scene_h = int(self.timeline._scene.height())
                    bar.setRange(0, max(0, scene_h - viewport_h))
                    # Center the B1 track in the viewport
                    target = max(0, y_offset - max(0, (viewport_h - 80) // 2))
                    bar.setValue(target)
                    # Make sure the new layer is fully visible too.
                    self.timeline.ensureVisible(
                        0,
                        y_offset,
                        1,
                        int(self.timeline._track_heights.get(
                            blur_track.id, 60
                        )),
                    )
            except Exception:
                pass
            # Auto-enable the blur effect so the visual blur shows on the
            # video preview the moment the layer is added.
            if hasattr(self, "blur_area_btn"):
                self.blur_area_btn.blockSignals(True)
                self.blur_area_btn.setChecked(True)
                self.blur_area_btn.blockSignals(False)
            # Push the new region's normalized data into the video view
            # and force the mpv vf filter to be applied immediately.
            try:
                regions = []
                for ll in blur_track.layers:
                    if not getattr(ll, "visible", True):
                        continue
                    regions.append({
                        "x": float(getattr(ll, "position_x", 0.3)),
                        "y": float(getattr(ll, "position_y", 0.8)),
                        "width": float(getattr(ll, "width", 0.4)),
                        "height": float(getattr(ll, "height", 0.1)),
                        "blur_strength": float(getattr(ll, "blur_strength", 20.0)),
                    })
                if hasattr(self.video_view, "set_blur_regions_normalized"):
                    self.video_view.set_blur_regions_normalized(regions)
                # The Add Layer menu bypasses the legacy Blur button, so it
                # must explicitly enable the editable overlay.  Merely
                # checking blur_area_btn does not emit its toggled signal.
                if hasattr(self.video_view, "set_blur_edit_enabled"):
                    self.video_view.set_blur_edit_enabled(True)
                if hasattr(self.video_view, "set_blur_active_index"):
                    self.video_view.set_blur_active_index(idx)
                if hasattr(self, "apply_preview_blur_region"):
                    self.apply_preview_blur_region(force=True)
            except Exception:
                pass
            # Persist the new region(s) to the project state so they
            # survive a close/reopen. Without this, the blur_state is
            # only saved on the legacy blur add/edit handlers, and a
            # region added via the new "Blur" button would be lost.
            try:
                if hasattr(self, "persist_project_blur_state"):
                    self.persist_project_blur_state()
            except Exception:
                pass
            try:
                self.timeline._selected_layer_id = layer.id
                # Route newly-created layers through the same paused
                # selection path as existing B1 layers. This starts the
                # deferred edit session and removes only this layer's
                # rendered effect while its geometry is edited.
                self.on_timeline_layer_selected(layer.id)
            except Exception:
                pass

        elif layer_type == "mask":
            from app.layers.mask import MaskLayer
            mask_track = find_or_create_track(tl, "M1", LayerType.MASK, 60)
            if hasattr(self.timeline, "_track_heights"):
                self.timeline._track_heights[mask_track.id] = (
                    mask_track.height or 60
                )
            idx = len(mask_track.layers)
            # Offset new regions slightly so their draggable overlays do
            # not start perfectly on top of an existing mask.
            stagger = idx % 4
            layer = MaskLayer(
                name=f"Mask {idx + 1}",
                position_x=0.3 + (stagger % 2) * 0.08,
                position_y=0.4 + (stagger // 2) * 0.08,
                width=0.4,
                height=0.2,
                color="#000000",
                mode="solid",
                pixelate_size=12,
                blur_strength=20,
                start=0.0,
                # Span the full timeline so the mask track is visible
                # across the whole video (like the audio track layers),
                # not a short 5-second segment.
                end=tl.duration if tl.duration > 0 else 5.0,
            )
            layer.z_index = idx
            # Visibility is gated by the play state in
            # _apply_mask_to_preview: the mask filter is only pushed
            # to mpv while the video is playing, so a freshly added
            # mask does not draw on the paused preview.
            mask_track.layers.append(layer)
            self.timeline._redraw()
            # Push the new mask into the mpv filter chain and persist
            # it so the export matches the preview.
            try:
                self._apply_mask_to_preview()
            except Exception:
                pass
            try:
                if hasattr(self, "persist_project_mask_state"):
                    self.persist_project_mask_state()
            except Exception:
                pass
            # Select the new mask layer so the inspector opens with
            # the right settings loaded.
            try:
                self.timeline._selected_layer_id = layer.id
                self.timeline._redraw()
                # Use the normal paused-layer selection path so the new M1
                # layer gets the same deferred effect/edit-handle behavior
                # as a layer selected after reopening a project.
                self.on_timeline_layer_selected(layer.id)
            except Exception:
                pass

        # Save timeline data (includes mask and logo layers)
        try:
            self.persist_current_timeline_project_data()
        except Exception:
            pass
