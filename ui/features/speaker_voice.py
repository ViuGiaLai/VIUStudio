import threading
from typing import Any
from PySide6.QtWidgets import (
    QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QComboBox,
                             QFrame)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor




class SpeakerVoiceMixin:
    def _preload_active_voice_if_needed(self):
        voice_name = self.get_active_voice_name()
        if not voice_name:
            return
        if str(voice_name).startswith("f5:"):
            return
        entry_id = str(self.free_voice_combo.currentData(self.VOICE_ENTRY_ID_ROLE) or '').strip() if hasattr(self, 'free_voice_combo') else ''
        entry = self.voice_catalog_map.get(entry_id) if hasattr(self, 'voice_catalog_map') else None
        provider = str((entry or {}).get('provider', '')).strip().lower()
        if provider != 'piper':
            return
        current_token = voice_name.strip()
        if getattr(self, '_voice_preload_inflight', '') == current_token or getattr(self, '_voice_preloaded_name', '') == current_token:
            return

        self._voice_preload_inflight = current_token

        def _worker(expected_voice: str):
            try:
                self._preload_tts_voice_impl(expected_voice)
                def _mark_ready():
                    if getattr(self, '_voice_preload_inflight', '') == expected_voice:
                        self._voice_preload_inflight = ''
                        self._voice_preloaded_name = expected_voice
                        self.log(f"[Voice] Piper voice preloaded: {expected_voice}")
                QTimer.singleShot(0, _mark_ready)
            except Exception as exc:
                error_message = str(exc)

                def _mark_failed(message=error_message):
                    if getattr(self, '_voice_preload_inflight', '') == expected_voice:
                        self._voice_preload_inflight = ''
                        self.log(f"[Voice] Piper preload skipped: {message}")
                QTimer.singleShot(0, _mark_failed)

        threading.Thread(target=_worker, args=(current_token,), daemon=True).start()

    def get_selected_premium_voice_catalog_entry(self):
        if not hasattr(self, "premium_voice_combo"):
            return None
        if not hasattr(self, "voice_catalog_entries"):
            return None
        entry_id = self.premium_voice_combo.currentData(self.VOICE_ENTRY_ID_ROLE)
        if entry_id and entry_id in self.voice_catalog_map:
            return self.voice_catalog_map[entry_id]
        current_value = str(self.premium_voice_combo.currentData() or "")
        for entry in self.voice_catalog_entries:
            if self._voice_catalog_data_value(entry) == current_value:
                return entry
        return None

    def get_active_voice_name(self) -> str:
        return self._resolve_active_voice_name(persist_new_clone=False)

    @staticmethod
    def _speaker_sort_key(speaker: str) -> tuple[int, str]:
        value = str(speaker or "").strip()
        try:
            return (int(value.rsplit("_", 1)[-1]), value)
        except (TypeError, ValueError):
            return (9999, value)

    @staticmethod
    def _speaker_color_hex(speaker: str) -> str:
        value = str(speaker or "").strip()
        try:
            index = int(value.rsplit("_", 1)[-1])
        except (TypeError, ValueError):
            index = sum(ord(char) for char in value)
        return QColor.fromHsv((index * 137 + 20) % 360, 155, 205).name()

    def _uses_speaker_subtitle_colors(self) -> bool:
        checkbox = getattr(self, "subtitle_speaker_colors_cb", None)
        return bool(checkbox and checkbox.isChecked())

    def _subtitle_color_for_segment(self, segment: Any | None) -> QColor:
        if segment is None:
            speaker = ""
        elif isinstance(segment, dict):
            speaker = str(segment.get("speaker", "") or "").strip()
        else:
            speaker = str(getattr(segment, "metadata", {}).get("speaker", "") if isinstance(getattr(segment, "metadata", None), dict) else getattr(segment, "speaker", "") or "").strip()
        if self._uses_speaker_subtitle_colors() and speaker:
            return QColor(self._speaker_color_hex(speaker))
        return QColor(self.subtitle_color_hex)

    def _apply_live_subtitle_segment_color(self, segment: dict | None) -> None:
        item = getattr(getattr(self, "video_view", None), "subtitle_item", None)
        if item is None:
            return
        color = self._subtitle_color_for_segment(segment)
        if color != getattr(item, "font_color", None):
            item.font_color = color
            item.update()

    def _refresh_speaker_subtitle_colors_if_needed(self) -> None:
        """Rebuild the ASS preview only when speaker IDs affect its colors."""
        if self._uses_speaker_subtitle_colors():
            self.update_subtitle_preview_style()

    def _detected_speaker_ids(self) -> list[str]:
        segments = list(
            getattr(self, "current_translated_segments", None)
            or getattr(self, "current_segments", None)
            or []
        )
        return sorted(
            {
                str(segment.get("speaker", "") or "").strip()
                for segment in segments
                if str(segment.get("speaker", "") or "").strip()
            },
            key=self._speaker_sort_key,
        )

    @staticmethod
    def _speaker_display_name(speaker: str, position: int) -> str:
        """Use stable automatic labels; diarization IDs remain internal."""
        if 0 <= position < 26:
            return f"Speaker {chr(ord('A') + position)}"
        return f"Speaker {position + 1}"

    def _speaker_voice_assignments(self) -> dict:
        state = getattr(self, "current_project_state", None)
        raw = state.settings.get("speaker_voice_assignments", {}) if state is not None else {}
        return dict(raw) if isinstance(raw, dict) else {}

    def _save_speaker_voice_assignment(
        self,
        speaker: str,
        *,
        name: str | None = None,
        voice: str | None = None,
        voice_gender_filter: str | None = None,
    ) -> None:
        state = getattr(self, "current_project_state", None)
        speaker = str(speaker or "").strip()
        if state is None or not speaker:
            return
        assignments = self._speaker_voice_assignments()
        entry = dict(assignments.get(speaker, {}) or {})
        if name is not None:
            entry["name"] = str(name or "").strip()
        if voice is not None:
            entry["voice"] = str(voice or "").strip()
        if voice_gender_filter is not None:
            entry["voice_gender_filter"] = str(voice_gender_filter or "Any").strip() or "Any"
        assignments[speaker] = entry
        state.set_setting("speaker_voice_assignments", assignments)
        self.project_service.save_project(state)
        self._voiceover_force_refresh = True
        self._invalidate_dubbed_output_after_subtitle_edit()

    def _voice_display_entries(
        self,
        *,
        gender: str = "any",
        include_voice: str = "",
    ) -> list[tuple[str, str]]:
        """Return gender-filtered voices for a speaker row independently.

        ``free_voice_combo`` intentionally represents only Voice Setup.  A
        speaker's filter/search must never depend on that combo's contents.
        Keep an already assigned voice visible while filtering so changing a
        filter cannot silently replace the speaker's mapping.
        """
        wanted_gender = self._normalize_gender_value(gender)
        assigned = str(include_voice or "").strip()
        entries: list[tuple[str, str]] = []
        for entry in sorted(list(getattr(self, "voice_catalog_entries", []) or []), key=self._voice_entry_sort_key):
            value = self._voice_catalog_data_value(entry)
            if not value:
                continue
            entry_gender = self._normalize_gender_value(str(entry.get("gender", "")))
            label = str(entry.get("name", entry.get("id", "Voice")) or "Voice")
            gender_match = wanted_gender not in {"male", "female"} or entry_gender in {wanted_gender, "", "any"}
            if gender_match or value == assigned:
                entries.append((label, value))
        return entries

    def refresh_detected_speakers_section(self) -> None:
        card = getattr(self, "detected_speakers_card", None)
        layout = getattr(self, "detected_speakers_list_layout", None)
        if card is None or layout is None:
            return
        # Voice catalog initialization happens during UI construction, before
        # a project (and therefore the segment lists) necessarily exists.
        segments = list(
            getattr(self, "current_translated_segments", None)
            or getattr(self, "current_segments", None)
            or []
        )
        speakers = self._detected_speaker_ids()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        card.setVisible(bool(speakers))
        if not speakers:
            if hasattr(self, "timeline"):
                self.timeline.set_highlighted_speaker("")
            return
        assignments = self._speaker_voice_assignments()
        for position, speaker in enumerate(speakers):
            entry = dict(assignments.get(speaker, {}) or {})
            display_name = self._speaker_display_name(speaker, position)
            segment_count = sum(
                1 for segment in segments
                if str(segment.get("speaker", "") or "").strip() == speaker
            )
            row = QFrame()
            row.setObjectName("statusCard")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(9, 8, 9, 8)
            row_layout.setSpacing(6)
            header = QHBoxLayout()
            indicator = QLabel()
            indicator.setFixedSize(12, 12)
            indicator.setStyleSheet(
                f"background: {self._speaker_color_hex(speaker)}; border-radius: 6px; border: 1px solid #dcecff;"
            )
            header.addWidget(indicator)
            speaker_label = QLabel(f"{display_name}  ·  {segment_count} segment{'s' if segment_count != 1 else ''}")
            speaker_label.setToolTip(f"Timeline ID: {speaker}")
            header.addWidget(speaker_label, 1)
            row_layout.addLayout(header)
            row_layout.addWidget(QLabel("Voice type"))
            gender_combo = QComboBox()
            gender_combo.addItems(["Any", "Male", "Female"])
            saved_gender = str(entry.get("voice_gender_filter", "Any") or "Any").strip().title()
            gender_combo.setCurrentText(saved_gender if saved_gender in {"Any", "Male", "Female"} else "Any")
            row_layout.addWidget(gender_combo)
            row_layout.addWidget(QLabel("Voice"))
            voice_combo = QComboBox()
            assigned_voice = str(entry.get("voice", "") or "")
            row_layout.addWidget(voice_combo)

            def _refresh_speaker_voice_combo(
                *,
                combo=voice_combo,
                filter_combo=gender_combo,
                assigned=assigned_voice,
            ):
                # ``"Use default voice"`` intentionally has an empty value;
                # do not fall back to the original assignment in that case.
                current_assigned = (
                    str(combo.currentData() or "")
                    if combo.count()
                    else str(assigned or "")
                )
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("Use default voice", "")
                for label, value in self._voice_display_entries(
                    gender=filter_combo.currentText(),
                    include_voice=current_assigned,
                ):
                    combo.addItem(label, value)
                voice_index = combo.findData(current_assigned)
                combo.setCurrentIndex(voice_index if voice_index >= 0 else 0)
                combo.blockSignals(False)

            _refresh_speaker_voice_combo()
            voice_combo.currentIndexChanged.connect(
                lambda _index, sp=speaker, combo=voice_combo: self._save_speaker_voice_assignment(
                    sp, voice=str(combo.currentData() or "")
                )
            )
            gender_combo.currentTextChanged.connect(
                lambda value, sp=speaker, refresh=_refresh_speaker_voice_combo: (
                    self._save_speaker_voice_assignment(sp, voice_gender_filter=value),
                    refresh(),
                )
            )
            voice_combo.activated.connect(
                lambda _index, sp=speaker: self.highlight_timeline_speaker(sp)
            )
            reassign_row = QHBoxLayout()
            reassign_row.setContentsMargins(0, 0, 0, 0)
            reassign_row.setSpacing(6)
            reassign_row.addWidget(QLabel("Move all to"))
            reassign_combo = QComboBox()
            for target_position, target_speaker in enumerate(speakers):
                if target_speaker != speaker:
                    reassign_combo.addItem(
                        self._speaker_display_name(target_speaker, target_position),
                        target_speaker,
                    )
            reassign_button = QPushButton("Apply")
            reassign_button.setToolTip(
                f"Reassign every {display_name} subtitle segment to the selected speaker."
            )
            has_target = reassign_combo.count() > 0
            reassign_combo.setEnabled(has_target)
            reassign_button.setEnabled(has_target)
            reassign_button.clicked.connect(
                lambda _checked=False, source=speaker, combo=reassign_combo: self.reassign_all_speaker_segments(
                    source, str(combo.currentData() or "")
                )
            )
            reassign_row.addWidget(reassign_combo, 1)
            reassign_row.addWidget(reassign_button)
            row_layout.addLayout(reassign_row)
            row.mousePressEvent = lambda event, sp=speaker, original=row.mousePressEvent: (
                self.toggle_timeline_speaker_highlight(sp), original(event)
            )[-1]
            layout.addWidget(row)
        layout.addStretch()

    def highlight_timeline_speaker(self, speaker: str) -> None:
        if hasattr(self, "timeline"):
            self.timeline.set_highlighted_speaker(speaker)

    def toggle_timeline_speaker_highlight(self, speaker: str) -> None:
        """Toggle the presentation-only speaker highlight from its card."""
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            return
        selected = str(speaker or "").strip()
        current = str(getattr(timeline, "_highlighted_speaker", "") or "").strip()
        timeline.set_highlighted_speaker("" if selected and selected == current else selected)

    def _apply_speaker_voice_assignments(self, segments: list[dict]) -> list[dict]:
        assignments = self._speaker_voice_assignments()
        if not assignments:
            return [dict(segment) for segment in segments or []]
        # Speaker overrides are scoped to the currently selected engine and
        # output language.  A saved Piper assignment must not survive an
        # engine switch and silently override the user's new Edge/Zero/Kokoro
        # choice.  The current catalog is already filtered by both values.
        available_voices = {
            self._voice_catalog_data_value(entry)
            for entry in list(getattr(self, "voice_catalog_entries", []) or [])
            if isinstance(entry, dict) and self._voice_catalog_data_value(entry)
        }
        resolved = []
        for segment in segments or []:
            item = dict(segment)
            speaker = str(item.get("speaker", "") or "").strip()
            voice = str((assignments.get(speaker, {}) or {}).get("voice", "") or "").strip()
            if voice and voice in available_voices:
                item["voice_name"] = voice
            else:
                # Remove a stale materialized override as well; callers may
                # pass segments copied from an earlier engine run.
                item.pop("voice_name", None)
            resolved.append(item)
        return resolved

    def on_segment_speaker_changed(self, index: int, speaker: str) -> None:
        """Apply a manual diarization correction without rerunning analysis."""
        if getattr(self, "_syncing_segment_editor", False):
            return
        speaker = str(speaker or "").strip()
        updated = False
        for segments_list in (
            getattr(self, "current_segments", None),
            getattr(self, "current_translated_segments", None),
        ):
            if segments_list and 0 <= index < len(segments_list):
                if speaker:
                    segments_list[index]["speaker"] = speaker
                else:
                    segments_list[index].pop("speaker", None)
                updated = True
        if not updated:
            return
        self._sync_segment_models_from_current_segments()
        self._voiceover_force_refresh = True
        self._invalidate_dubbed_output_after_subtitle_edit()
        # Speaker identity changes the TS1 color and future voice selection,
        # not subtitle text, timing, or visual style.  Avoid the full
        # apply_segments_to_timeline() path here because it refreshes the
        # live subtitle preview assets and rewrites its SRT unnecessarily.
        if hasattr(self, "timeline"):
            self.timeline.set_segments(self.get_active_segments())
            self.timeline.set_active_segment_index(index)
        self._refresh_speaker_subtitle_colors_if_needed()
        self.refresh_detected_speakers_section()
        self.persist_current_timeline_project_data()

    def reassign_all_speaker_segments(self, source_speaker: str, target_speaker: str) -> None:
        """Move every cue from one diarized speaker to another."""
        source_speaker = str(source_speaker or "").strip()
        target_speaker = str(target_speaker or "").strip()
        if not source_speaker or not target_speaker or source_speaker == target_speaker:
            return
        changed_indexes: set[int] = set()
        for segments_list in (
            getattr(self, "current_segments", None),
            getattr(self, "current_translated_segments", None),
        ):
            if not segments_list:
                continue
            for index, segment in enumerate(segments_list):
                if str(segment.get("speaker", "") or "").strip() == source_speaker:
                    segment["speaker"] = target_speaker
                    changed_indexes.add(index)
        if not changed_indexes:
            return
        self._sync_segment_models_from_current_segments()
        self._voiceover_force_refresh = True
        self._invalidate_dubbed_output_after_subtitle_edit()
        if hasattr(self, "timeline"):
            self.timeline.set_segments(self.get_active_segments())
            self.timeline.set_highlighted_speaker(target_speaker)
        self._refresh_speaker_subtitle_colors_if_needed()
        self.refresh_detected_speakers_section()
        self.persist_current_timeline_project_data()
        self.log(
            f"[Diarization] Reassigned {len(changed_indexes)} segment(s) "
            f"from {source_speaker} to {target_speaker}."
        )

    def on_voice_tier_changed(self):
        mode = self.get_output_mode_key() if hasattr(self, "output_mode_combo") else "both"
        if hasattr(self, "free_voice_combo"):
            self.free_voice_combo.setEnabled(True)
        if hasattr(self, "preview_voice_btn"):
            self.preview_voice_btn.setVisible(mode in ("voice", "both"))
        self._update_voice_preview_meta()

    def _parse_voice_speed_value(self) -> float:
        raw = str(getattr(self, "voice_speed_spin", None).currentText() if getattr(self, "voice_speed_spin", None) else "1.0x").strip().lower()
        raw = raw.replace("x", "")
        try:
            return float(raw or "1.0")
        except ValueError:
            return 1.0

    def _percent_to_db(self, percent: int) -> float:
        """Convert volume percentage (0-200) to dB gain."""
        if percent <= 0:
            return -60.0
        import math
        return 20.0 * math.log10(percent / 100.0)

    # -----------------------------
    # Logging + error helpers
    # -----------------------------
