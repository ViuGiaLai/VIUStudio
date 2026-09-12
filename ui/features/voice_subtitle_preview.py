import os
import shutil
import re
import copy
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, QTextEdit, QFrame, QMessageBox,
                             QScrollArea,
                             QDialog)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QPixmap, QTextCursor

from video_processor import srt_to_ass
from audio_mixer import ffprobe_wav_duration
from utils.display_utils import (
    show_frame_preview_dialog as show_frame_preview_dialog_impl,
)
from worker_adapters import (
    SegmentAudioPreviewWorker,
    VoiceSamplePreviewWorker,
    VoiceExportWorker,
)
from utils.thread_lifecycle import release_thread_when_stopped

from workflows.voice_workflow import predict_speed_ratios



class VoiceSubtitlePreviewMixin:
    def _resolve_voice_preview_source(self, entry: dict) -> QUrl:
        preview_path = str(entry.get("preview_video_path", "")).strip()
        preview_url = str(entry.get("preview_video_url", "")).strip()
        preview_audio_path = str(entry.get("preview_audio_path", "")).strip()
        preview_audio_url = str(entry.get("preview_audio_url", "")).strip()

        if preview_path:
            if not os.path.isabs(preview_path):
                preview_path = os.path.join(self.workspace_root, preview_path)
            if not os.path.exists(preview_path):
                raise FileNotFoundError("The configured preview video file was not found.")
            return QUrl.fromLocalFile(preview_path)
        if preview_url:
            return QUrl(preview_url)
        if preview_audio_path:
            if not os.path.isabs(preview_audio_path):
                preview_audio_path = os.path.join(self.workspace_root, preview_audio_path)
            if not os.path.exists(preview_audio_path):
                raise FileNotFoundError("The configured preview audio file was not found.")
            return QUrl.fromLocalFile(preview_audio_path)
        if preview_audio_url:
            return QUrl(preview_audio_url)
        raise RuntimeError("This voice does not have preview media configured yet.")

    def _stop_voice_library_preview(self):
        try:
            self.voice_preview_library_player.stop()
            self.voice_preview_library_player.setSource(QUrl())
        except Exception:
            pass
        for button in self._voice_preview_row_buttons.values():
            button.setText("Preview")

    def _play_voice_preview_entry(self, entry: dict, button: QPushButton | None = None):
        try:
            source = self._resolve_voice_preview_source(entry)
            self._stop_voice_library_preview()
            self.voice_preview_library_player.setSource(source)
            self.voice_preview_library_player.play()
            if button is not None:
                button.setText("Playing...")
            self.log(f"[Voice Preview] playing clip for {entry.get('name', 'voice')}")
        except Exception as exc:
            self.show_error("Voice Preview Failed", "Could not play the selected voice preview clip.", str(exc))

    def _build_voice_preview_popup(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Voice Preview Library")
        dialog.setModal(False)
        dialog.resize(720, 560)
        dialog.setStyleSheet(
            """
            QDialog {
                background-color: #0f1724;
            }
            QWidget {
                background-color: #0f1724;
                color: #dbe5f3;
            }
            QScrollArea {
                border: none;
                background-color: #0f1724;
            }
            QLabel#statusHeadline {
                color: #f8fbff;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#sectionTitle {
                color: #8ad7ff;
                font-weight: 700;
            }
            QLabel#helperLabel {
                color: #9fb3ca;
            }
            QFrame#statusCard {
                background-color: #132033;
                border: 1px solid #2f4868;
                border-radius: 12px;
            }
            QPushButton {
                background-color: #22344d;
                color: #f8fbff;
                border: 1px solid #34506f;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #29405d;
            }
            QPushButton:disabled {
                background-color: #172435;
                color: #7f92a9;
                border-color: #24384f;
            }
            """
        )

        root_layout = QVBoxLayout(dialog)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        title = QLabel("Voice Preview Library", dialog)
        title.setObjectName("statusHeadline")
        root_layout.addWidget(title)

        hint = QLabel(
            "Preview each configured voice sample here. This popup uses a separate player and does not affect the main video timeline.",
            dialog,
        )
        hint.setObjectName("helperLabel")
        hint.setWordWrap(True)
        root_layout.addWidget(hint)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget(scroll)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        current_provider = None
        self._voice_preview_row_buttons = {}
        entries = sorted(
            list(self.voice_catalog_entries_all or []),
            key=lambda item: (
                str(item.get("tier", "")),
                self._voice_provider_label(str(item.get("provider", ""))),
                str(item.get("name", "")),
            ),
        )
        for entry in entries:
            provider = self._voice_provider_label(str(entry.get("provider", "")).strip())
            if provider != current_provider:
                current_provider = provider
                header = QLabel(provider, container)
                header.setObjectName("sectionTitle")
                layout.addWidget(header)

            row = QFrame(container)
            row.setObjectName("statusCard")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(10)

            label = QLabel(str(entry.get("name", entry.get("id", "Voice"))), row)
            label.setWordWrap(True)
            meta = QLabel(str(entry.get("tier", "voice")).strip().title(), row)
            meta.setObjectName("helperLabel")
            preview_btn = QPushButton("Preview", row)
            preview_btn.setEnabled(self._entry_has_preview_media(entry))
            preview_btn.clicked.connect(lambda _checked=False, item=entry, btn=preview_btn: self._play_voice_preview_entry(item, btn))

            row_layout.addWidget(label, 1)
            row_layout.addWidget(meta)
            row_layout.addWidget(preview_btn)
            layout.addWidget(row)
            self._voice_preview_row_buttons[str(entry.get("id", ""))] = preview_btn

        layout.addStretch()
        scroll.setWidget(container)
        root_layout.addWidget(scroll, 1)

        close_btn = QPushButton("Close", dialog)
        close_btn.clicked.connect(dialog.close)
        root_layout.addWidget(close_btn, 0, Qt.AlignRight)

        dialog.finished.connect(lambda _result: self._stop_voice_library_preview())
        self.voice_preview_dialog = dialog
        return dialog

    def preview_selected_voice_sample(self):
        if not (self.voice_catalog_entries or []):
            target_language = str(self.get_target_language_code() if hasattr(self, "get_target_language_code") else "vi").strip().lower()
            engine_key = self._current_voice_engine_key() if hasattr(self, "_current_voice_engine_key") else "piper"
            if engine_key == "zerotts":
                QMessageBox.information(
                    self,
                    "Preview voice",
                    "ZeroTTS voices could not be loaded. Use Install / Manage Voice Engines, then reopen the Voice section.",
                )
                return
            if engine_key == "kokoro":
                QMessageBox.information(
                    self,
                    "Preview voice",
                    "No Kokoro voices were found. Put .pt voice files in models/kokoro/voices, then reopen the Voice section.",
                )
                return
            folder = "models/piper-en" if target_language.startswith("en") else "models/piper"
            QMessageBox.information(
                self,
                "Preview voice",
                f"No local voices are available for the selected language. Install a Piper voice pack in {folder} from Manage Resources first.",
            )
            return

        if not self.ensure_required_resources("Voice preview", include_voice=True):
            return

        if self._voice_sample_preview_thread is not None:
            QMessageBox.information(self, "Preview voice", "A preview is already being generated. Please wait a moment.")
            return

        voice_name = self.get_active_voice_name()
        if not voice_name:
            QMessageBox.warning(self, "Preview voice", "Choose a voice first.")
            return
        voice_speed = self._parse_voice_speed_value()
        target_language = str(
            self.get_target_language_code() if hasattr(self, "get_target_language_code") else "vi"
        ).strip().lower()
        text = (
            "Hello, this is a preview of the selected voice."
            if target_language.startswith("en")
            else "Chào bạn, đây là bản xem trước giọng nói của mẫu được chọn."
        )

        if hasattr(self, "preview_voice_btn"):
            self.preview_voice_btn.setEnabled(False)
            self.preview_voice_btn.setText("...")

        worker = VoiceSamplePreviewWorker(
            self.workspace_root,
            text,
            voice_name,
            voice_speed,
            temp_dir=self.get_project_temp_dir("voice_sample_preview"),
        )
        worker.progress.connect(self.log)
        worker.finished.connect(self.on_voice_sample_preview_ready)
        worker.finished.connect(
            lambda *_args, worker=worker: release_thread_when_stopped(
                worker,
                lambda: setattr(self, "_voice_sample_preview_thread", None)
                if getattr(self, "_voice_sample_preview_thread", None) is worker
                else None,
            )
        )
        self._voice_sample_preview_thread = worker
        worker.start()

    def on_voice_sample_preview_ready(self, audio_path: str, error: str):
        if hasattr(self, "preview_voice_btn"):
            self.preview_voice_btn.setEnabled(True)
            self.preview_voice_btn.setText("Preview voice")

        if error:
            self.show_error("Voice Preview Failed", "Could not generate the preview audio.", error)
            return
        if not audio_path:
            self.show_error("Voice Preview Failed", "Preview audio path is missing.", "")
            return

        try:
            self.play_audio_preview_file(audio_path)
            self.log(f"[Voice Preview] playing generated sample: {audio_path}")
        except Exception as exc:
            self.show_error("Voice Preview Failed", "Could not play the generated preview audio.", str(exc))

    def preview_segment_audio(self, index: int):
        if index < 0 or index >= len(self.current_translated_segments or self.current_segments):
            QMessageBox.warning(self, "Missing Subtitle", "This subtitle line is not ready yet.")
            return

        if not self.ensure_required_resources("Subtitle audio preview", include_voice=True):
            return

        source_segments = self.current_translated_segments or self.current_segments
        text = str(source_segments[index].get("tts_text") or source_segments[index].get("text", "")).strip()
        if not text:
            QMessageBox.warning(self, "Missing Subtitle", "This subtitle line is empty.")
            return

        voice_name = self.get_active_voice_name()
        if not voice_name:
            QMessageBox.warning(self, "Missing Voice", "Choose a voice first before generating subtitle audio preview.")
            return
        voice_speed = self._parse_voice_speed_value()
        self._find_segment_editor_row(index)
        # The per-segment "Regenerate voice" button was moved to the
        # A2 Dub Track Inspector. Disable that one instead.
        if getattr(self, "audio_inspector_regenerate_voice_btn", None) is not None:
            self.audio_inspector_regenerate_voice_btn.setEnabled(False)
            self.audio_inspector_regenerate_voice_btn.setText("…")

        existing = self._segment_preview_threads.get(index)
        if existing and existing.isRunning():
            existing.quit()
            existing.wait(2000)
        worker = SegmentAudioPreviewWorker(
            self.workspace_root,
            index,
            text,
            voice_name,
            voice_speed,
            temp_dir=self.get_project_temp_dir("segment_audio_preview"),
            cache_temp_dir=self.get_project_temp_dir("tts"),
        )
        worker.finished.connect(self.on_segment_audio_preview_ready)
        worker.finished.connect(
            lambda *_args, worker=worker: release_thread_when_stopped(
                worker,
                lambda: self._segment_preview_threads.pop(index, None)
                if self._segment_preview_threads.get(index) is worker
                else None,
            )
        )
        self._segment_preview_threads[index] = worker
        worker.start()

    def on_segment_audio_preview_ready(self, index: int, audio_path: str, error: str):
        btn = getattr(self, "audio_inspector_regenerate_voice_btn", None)

        self._segment_preview_threads.pop(index, None)

        if error:
            if btn is not None:
                btn.setEnabled(True)
                btn.setText("Voice")
            self.show_error("Audio Preview Failed", "Could not generate preview audio for this subtitle.", error)
            return

        self._voiceover_force_refresh = True
        if btn is not None:
            btn.setEnabled(True)
            btn.setText("Voice")

        if getattr(self, "last_voice_vi_path", "") and os.path.exists(self.last_voice_vi_path):
            self.run_voiceover()
        else:
            self._apply_segment_audio_end_to_timeline(index=index, audio_path=audio_path)
            try:
                self.play_audio_preview_file(audio_path)
            except Exception as exc:
                self.show_error("Audio Preview Failed", "Could not play the generated preview audio.", str(exc))

    def _apply_segment_audio_end_to_timeline(self, *, index: int, audio_path: str) -> None:
        if not audio_path or not os.path.exists(audio_path):
            return
        actual_d = ffprobe_wav_duration(audio_path)
        if actual_d <= 0.0:
            return
        segs = self.current_translated_segments or self.current_segments
        if not segs or index < 0 or index >= len(segs):
            return
        seg = segs[index]
        try:
            start_s = float(seg.get("start", 0.0))
        except (TypeError, ValueError):
            return
        audio_end = start_s + actual_d
        try:
            cur_end = float(seg.get("end", audio_end))
        except (TypeError, ValueError):
            cur_end = audio_end
        if audio_end > cur_end + 0.01:
            seg["_audio_end"] = audio_end
        else:
            seg.pop("_audio_end", None)
        timeline = getattr(self, "timeline", None)
        if timeline is None:
            return
        timeline_model = getattr(timeline, "_timeline", None)
        if timeline_model is None:
            return
        from app.layers.sync_bridge import DUB_SUBTITLE_TRACK_NAME
        target_track = None
        for t in timeline_model.tracks:
            if t.name == DUB_SUBTITLE_TRACK_NAME:
                target_track = t
                break
        if target_track is None:
            return
        for layer in target_track.layers:
            meta = getattr(layer, "metadata", None) or {}
            if not isinstance(meta, dict):
                continue
            try:
                if int(meta.get("_seg_index", -1)) == index:
                    if audio_end > cur_end + 0.01:
                        meta["_audio_end"] = audio_end
                    else:
                        meta.pop("_audio_end", None)
            except (TypeError, ValueError):
                continue
        timeline._redraw()

    def download_subtitle(self):
        srt_text = self.translated_text.toPlainText().strip()
        if not srt_text:
            QMessageBox.warning(self, "Missing Subtitle", "No translated subtitle is ready yet.")
            return
        target_lang = str(self.get_target_language_code() or "translated").lower()
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        suggested_name = os.path.splitext(os.path.basename(source_path or "subtitle"))[0] + f"_{target_lang}.srt"
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Translated Subtitle", suggested_name, "Subtitle Files (*.srt)")
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(srt_text)
        QMessageBox.information(self, "Saved", f"Translated subtitle exported to:\n\n{file_path}")

    def export_voice_audio(self):
        voice_path = str(
            getattr(self, "last_voice_vi_path", "")
            or (self.processed_artifacts.get("voice_vi") if hasattr(self, "processed_artifacts") else "")
            or ""
        ).strip()
        if not voice_path or not os.path.exists(voice_path):
            state = getattr(self, "current_project_state", None)
            if state and getattr(state, "artifacts", None):
                candidate = str(state.artifacts.get("voice_vi", "")).strip()
                if candidate and os.path.exists(candidate):
                    voice_path = candidate

        if not voice_path or not os.path.exists(voice_path):
            has_subtitles = bool(
                (hasattr(self, "_get_voiceover_segments") and self._get_voiceover_segments())
                or (getattr(self, "translated_text", None) and self.translated_text.toPlainText().strip())
                or (getattr(self, "current_translated_segments", None))
            )
            if has_subtitles:
                reply = QMessageBox.question(
                    self,
                    "Voice Audio Not Ready",
                    "No voice audio has been generated yet for this project.\n\nWould you like to run Generate Voice / TTS now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    if hasattr(self, "run_voiceover_with_progress"):
                        self.run_voiceover_with_progress(target_stage="tts")
                    elif hasattr(self, "run_voiceover"):
                        self.run_voiceover()
            else:
                QMessageBox.warning(
                    self,
                    "Missing Voice Audio",
                    "No voice audio is ready to export.\n\nPlease import or create subtitles and run Voice (TTS) first.",
                )
            return

        if hasattr(self, "preview_controller") and not self.preview_controller._check_audio_freshness(voice_path):
            return

        source_path = (
            (self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else ""))
            or getattr(self, "last_translated_srt_path", "")
            or ""
        )
        base_name = os.path.splitext(os.path.basename(source_path))[0] if source_path else ""
        if not base_name or base_name.lower() in ("subtitle", "voice"):
            base_name = "voice"
        target_lang = str(self.get_target_language_code() if hasattr(self, "get_target_language_code") else "vi").lower()
        suggested_name = f"{base_name}_{target_lang}_voice.mp3"
        default_dir = (
            (self.voice_output_folder_edit.text().strip() if hasattr(self, "voice_output_folder_edit") else "")
            or (self.final_output_folder_edit.text().strip() if hasattr(self, "final_output_folder_edit") else "")
            or (self.srt_output_folder_edit.text().strip() if hasattr(self, "srt_output_folder_edit") else "")
            or self.workspace_root
        )
        default_path = os.path.join(default_dir, suggested_name)

        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Voice Audio",
            default_path,
            "MP3 Audio (*.mp3);;WAV Audio (*.wav)",
        )
        if not file_path:
            return

        if "wav" in selected_filter.lower():
            if not file_path.lower().endswith(".wav"):
                file_path = (file_path[:-4] if file_path.lower().endswith(".mp3") else file_path) + ".wav"
        else:
            if not file_path.lower().endswith((".mp3", ".wav")):
                file_path += ".mp3"

        self._perform_voice_audio_export(voice_path, file_path)

    def _perform_voice_audio_export(self, voice_path: str, output_path: str):
        self.log(f"[Voice Export] Exporting voice audio to {output_path}...")
        old_worker = getattr(self, "_voice_export_worker", None)
        if old_worker is not None:
            try:
                if old_worker.isRunning():
                    old_worker.quit()
                    old_worker.wait(1000)
            except Exception:
                pass
            self._voice_export_worker = None

        worker = VoiceExportWorker(voice_path, output_path, bitrate="256k")
        self._voice_export_worker = worker

        def on_finished(success: bool, dest: str, err: str):
            release_thread_when_stopped(worker)
            self._voice_export_worker = None
            if success and os.path.exists(dest):
                self.log(f"[Voice Export] Successfully exported voice audio to {dest}")
                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Voice audio exported successfully to:\n\n{dest}\n\nYou can now import this file into CapCut or any audio editor.",
                )
            else:
                self.log(f"[Voice Export] Export failed: {err}")
                QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Could not export voice audio:\n\n{err or 'Unknown error'}",
                )

        worker.finished.connect(on_finished)
        worker.start()

    def import_voice_audio(self):
        default_dir = (
            (self.voice_output_folder_edit.text().strip() if hasattr(self, "voice_output_folder_edit") else "")
            or (self.final_output_folder_edit.text().strip() if hasattr(self, "final_output_folder_edit") else "")
            or getattr(self, "workspace_root", "")
            or ""
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Voice Audio",
            default_dir,
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.wma);;All Files (*.*)",
        )
        if not file_path:
            return

        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            QMessageBox.warning(self, "Import Failed", "The selected audio file is invalid or empty.")
            return

        normalized_path = self._normalize_local_file_path(file_path) if hasattr(self, "_normalize_local_file_path") else os.path.normpath(file_path)

        state = self.ensure_current_project() if hasattr(self, "ensure_current_project") else getattr(self, "current_project_state", None)
        target_path = normalized_path
        if state and getattr(state, "project_root", "") and os.path.isdir(state.project_root):
            audio_dir = os.path.join(state.project_root, "audio")
            os.makedirs(audio_dir, exist_ok=True)
            ext = os.path.splitext(normalized_path)[1].lower() or ".mp3"
            dest = os.path.join(audio_dir, f"imported_voice{ext}")
            if os.path.abspath(normalized_path) != os.path.abspath(dest):
                try:
                    shutil.copy2(normalized_path, dest)
                    target_path = dest
                except Exception as exc:
                    self.log(f"[Import Voice] Notice: Could not copy audio to project directory ({exc}), using original path.")
                    target_path = normalized_path

        self.last_voice_vi_path = target_path
        if hasattr(self, "processed_artifacts"):
            self.processed_artifacts["voice_vi"] = target_path
        if hasattr(self, "update_project_artifact"):
            self.update_project_artifact("voice_vi", target_path)
        if hasattr(self, "update_project_step"):
            self.update_project_step("generate_tts", "done")

        self._voice_track_partial = False
        if hasattr(self, "use_generated_audio_radio"):
            self.use_generated_audio_radio.setChecked(True)

        if hasattr(self, "audio_tab_btn"):
            self.audio_tab_btn.setEnabled(True)

        if hasattr(self, "timeline"):
            self.timeline.sync_tts_track(
                target_path,
                segments=getattr(self, "current_translated_segments", None) or getattr(self, "current_segments", None),
            )
            if hasattr(self, "voice_timing_sync_combo"):
                self.timeline.set_voice_sync_mode(self.voice_timing_sync_combo.currentText())

        if hasattr(self, "_sync_timeline_mute_to_gui"):
            self._sync_timeline_mute_to_gui()

        if hasattr(self, "persist_current_timeline_project_data"):
            self.persist_current_timeline_project_data()

        if hasattr(self, "schedule_timeline_visual_refresh"):
            self.schedule_timeline_visual_refresh(waveform=True, thumbnails=False)

        if hasattr(self, "sync_preview_audio_track_to_output"):
            self.sync_preview_audio_track_to_output(apply_to_player=True, force=True)

        if state:
            state.set_setting("voice_track_partial", False)
            if hasattr(self, "project_service") and self.project_service:
                self.project_service.save_project(state)

        self.log(f"[Import] Voice audio loaded: {target_path}")
        self.refresh_ui_state()
        QMessageBox.information(
            self,
            "Import Success",
            f"Voice audio imported successfully:\n\n{os.path.basename(target_path)}\n\nYou can now preview or mix with background audio and export.",
        )

    def import_original_srt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Original Subtitle",
            self.srt_output_folder_edit.text().strip() or self.workspace_root,
            "Subtitle Files (*.srt)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as handle:
                srt_text = handle.read().strip()
        except Exception as exc:
            self.show_error("Import Failed", "Could not read the selected subtitle file.", str(exc))
            return

        if not srt_text:
            QMessageBox.warning(self, "Import Failed", "The selected subtitle file is empty.")
            return

        imported_segments = self.parse_srt_to_segments(srt_text)
        if not imported_segments:
            QMessageBox.warning(self, "Import Failed", "The selected file could not be parsed as a valid SRT subtitle.")
            return
        imported_segments = self.normalize_subtitle_timing(imported_segments)
        srt_text = self.format_to_srt(imported_segments)

        self.current_segments = imported_segments
        self._invalidate_translation_after_original_change()
        self.transcript_text.setText(srt_text)
        self.last_original_srt_path = file_path
        self.processed_artifacts["srt_original"] = file_path
        self._commit_subtitle_mutation()
        state = self.ensure_current_project()
        if state:
            state.set_setting("transcription_signature", "")
            self.project_service.save_project(state)
        self.log(f"[Import] Original subtitle loaded: {file_path} ({len(imported_segments)} segments)")
        QMessageBox.information(self, "Import Success", f"Loaded {len(imported_segments)} segments from original subtitle.")
        self.refresh_ui_state()

    def import_translated_srt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Translated Subtitle",
            self.srt_output_folder_edit.text().strip() or self.workspace_root,
            "Subtitle Files (*.srt)",
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8-sig") as handle:
                srt_text = handle.read().strip()
        except Exception as exc:
            self.show_error("Import Failed", "Could not read the selected subtitle file.", str(exc))
            return

        if not srt_text:
            QMessageBox.warning(self, "Import Failed", "The selected subtitle file is empty.")
            return

        imported_segments = self.parse_srt_to_segments(srt_text)
        if not imported_segments:
            QMessageBox.warning(self, "Import Failed", "The selected file could not be parsed as a valid SRT subtitle.")
            return
        imported_segments = self.normalize_subtitle_timing(imported_segments)

        # An SRT only stores text/timestamps. Keep diarization metadata from
        # the current translated transcript first (manual speaker corrections
        # are stored there), falling back to the original transcript. Matching
        # by overlap also works when an imported file has slightly different
        # cue boundaries or a different number of cues.
        base_segments = self.current_translated_segments or self.current_segments
        if base_segments:
            for imported in imported_segments:
                try:
                    start = float(imported.get("start", 0.0))
                    end = float(imported.get("end", start))
                except (TypeError, ValueError):
                    continue
                best = None
                best_score = -1.0
                midpoint = (start + end) / 2.0
                for base in base_segments:
                    speaker = str(base.get("speaker", "") or "").strip()
                    if not speaker:
                        continue
                    try:
                        base_start = float(base.get("start", 0.0))
                        base_end = float(base.get("end", base_start))
                    except (TypeError, ValueError):
                        continue
                    overlap = max(0.0, min(end, base_end) - max(start, base_start))
                    distance = abs(midpoint - ((base_start + base_end) / 2.0))
                    score = overlap * 1000.0 - distance
                    if score > best_score:
                        best_score = score
                        best = base
                if best is not None:
                    speaker = str(best.get("speaker", "") or "").strip()
                    if speaker:
                        imported["speaker"] = speaker
        # Import is authoritative: replace the previous cue boundaries with
        # the file's normalized timing.  "Keep timeline" still applies to
        # text-only editing, but must not resurrect old overlapping timings
        # during an explicit SRT import.
        srt_text = self.format_to_srt(imported_segments)

        self.translated_text.setText(srt_text)
        self.current_translated_segments = [dict(segment) for segment in imported_segments]
        self.current_translated_segment_models = self._dict_segments_to_models(
            self.current_translated_segments,
            translated=True,
        )
        self.apply_segments_to_timeline()
        self._invalidate_dubbed_output_after_subtitle_edit()
        # Re-apply metadata-bearing imported entries after the timeline
        # rebuild so speaker assignments survive the SRT replacement.
        if imported_segments and self.current_translated_segments:
            if len(imported_segments) == len(self.current_translated_segments):
                for idx, imported in enumerate(imported_segments):
                    speaker = str(imported.get("speaker", "") or "").strip()
                    if speaker:
                        self.current_translated_segments[idx]["speaker"] = speaker
            else:
                for target in self.current_translated_segments:
                    try:
                        start = float(target.get("start", 0.0))
                        end = float(target.get("end", start))
                    except (TypeError, ValueError):
                        continue
                    best = None
                    best_score = -1.0
                    midpoint = (start + end) / 2.0
                    for imported in imported_segments:
                        speaker = str(imported.get("speaker", "") or "").strip()
                        if not speaker:
                            continue
                        try:
                            imported_start = float(imported.get("start", 0.0))
                            imported_end = float(imported.get("end", imported_start))
                        except (TypeError, ValueError):
                            continue
                        overlap = max(0.0, min(end, imported_end) - max(start, imported_start))
                        distance = abs(midpoint - ((imported_start + imported_end) / 2.0))
                        score = overlap * 1000.0 - distance
                        if score > best_score:
                            best_score = score
                            best = imported
                    if best is not None:
                        target["speaker"] = str(best.get("speaker", "") or "").strip()
            self.current_translated_segment_models = self._dict_segments_to_models(
                self.current_translated_segments,
                translated=True,
            )
            self.apply_segments_to_timeline()
        self.last_translated_srt_path = file_path
        self.processed_artifacts["srt_translated"] = file_path
        self._commit_subtitle_mutation(
            selected_index=getattr(self, "_selected_segment_index", None),
        )
        # Rebuild speaker UI/colors after replacing the translated cues.  The
        # imported SRT itself cannot contain speaker metadata, so the merge
        # above is the source of truth for these project-only fields.
        self.refresh_detected_speakers_section()
        self._refresh_speaker_subtitle_colors_if_needed()
        self.refresh_ui_state()
        QMessageBox.information(
            self,
            "Imported",
            "Translated subtitle loaded. You can now run Generate Voice / TTS.\n\n" + file_path,
        )

    def download_original_script(self):
        script_text = self.transcript_text.toPlainText().strip()
        if not script_text:
            QMessageBox.warning(self, "Missing Script", "No original script is ready yet.")
            return
        source_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        base_name = os.path.splitext(os.path.basename(source_path or "original"))[0] + "_original"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Source Subtitle",
            base_name + ".srt",
            "Subtitle Files (*.srt)",
        )
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(script_text)
        QMessageBox.information(self, "Saved", f"Source subtitle exported to:\n\n{file_path}")

    def on_export_finished(self, output_path, error):
        self.preview_controller.on_export_finished(output_path, error)

    def on_auto_recap_export_finished(self, output_path, error):
        self.preview_controller._on_auto_recap_export_finished(output_path, error)

    def on_quick_preview_ready(self, output_path, error):
        self.preview_controller.on_quick_preview_ready(output_path, error)

    def on_exact_frame_ready(self, output_path, error):
        self.preview_controller.on_exact_frame_ready(output_path, error)

    def show_frame_preview_dialog(self, image_path: str):
        show_frame_preview_dialog_impl(self, image_path, QPixmap, Qt)

    # -----------------------------
    # Subtitle source handling
    # -----------------------------
    def get_active_segments(self):
        base = self.current_translated_segments or self.current_segments or []
        if base and bool(getattr(self, "subtitle_single_line_cb", None) and self.subtitle_single_line_cb.isChecked()):
            split = getattr(self, "_single_line_split_cache", None)
            if split is not None:
                return split
        return base

    def apply_segments_to_timeline(self):
        timing_changed = False
        if self.current_translated_segments:
            normalized = self.normalize_subtitle_timing(
                self.current_translated_segments
            )
            if normalized != self.current_translated_segments:
                timing_changed = True
                self.current_translated_segments = normalized
                self.current_translated_segment_models = self._dict_segments_to_models(
                    normalized,
                    translated=True,
                )
                self._single_line_split_cache = None
                self._sync_hidden_translated_text_from_segments()
        elif self.current_segments:
            normalized = self.normalize_subtitle_timing(self.current_segments)
            if normalized != self.current_segments:
                timing_changed = True
                self.current_segments = normalized
                self.current_segment_models = self._dict_segments_to_models(
                    normalized,
                    translated=False,
                )
                self._single_line_split_cache = None
                self._sync_hidden_transcript_text_from_segments()
        self._subtitle_timing_was_normalized = timing_changed
        segs = self.get_active_segments()
        if segs:
            predict_speed_ratios(segs)
        self.timeline.set_segments(segs if segs else [])
        self.schedule_timeline_visual_refresh(waveform=True, thumbnails=True)
        # Configure the Qt subtitle overlay before showing its drag target.
        # Otherwise it can briefly use the default size until the first drag.
        self.update_subtitle_preview_style()
        self._show_subtitle_drag_layer()
        self.sync_live_subtitle_preview()

    def _segments_from_editor_text(self, srt_text: str, base_segments):
        srt_text = (srt_text or "").strip()
        if not srt_text:
            return []

        if self.keep_timeline_cb.isChecked() and base_segments:
            edited_texts = self.extract_subtitle_text_entries(srt_text)
            if edited_texts and len(edited_texts) == len(base_segments):
                out = []
                for idx, base in enumerate(base_segments):
                    d = {
                        "start": float(base["start"]),
                        "end": float(base["end"]),
                        "text": edited_texts[idx],
                        "tts_text": str(base.get("tts_text", "") or ""),
                        "tts_group_id": base.get("tts_group_id", ""),
                        "tts_group_start": float(base.get("tts_group_start", base.get("start", 0.0)) or 0.0),
                        "tts_group_end": float(base.get("tts_group_end", base.get("end", 0.0)) or 0.0),
                        "words": list(base.get("words", [])),
                        "manual_highlights": list(base.get("manual_highlights", [])),
                    }
                    if base.get("speaker"):
                        d["speaker"] = str(base.get("speaker", "") or "")
                    if base.get("voice_speed") is not None:
                        try:
                            d["voice_speed"] = float(base.get("voice_speed", 1.0) or 1.0)
                        except (TypeError, ValueError):
                            pass
                    raw = base.get("_audio_end")
                    if raw is not None:
                        try:
                            d["_audio_end"] = float(raw)
                        except (TypeError, ValueError):
                            pass
                    out.append(d)
                return out

        parsed_segments = self.parse_srt_to_segments(srt_text)
        if base_segments and len(parsed_segments) == len(base_segments):
            for idx, segment in enumerate(parsed_segments):
                base = base_segments[idx]
                segment["words"] = list(base.get("words", []))
                segment["manual_highlights"] = list(base.get("manual_highlights", []))
                if base.get("speaker"):
                    segment["speaker"] = str(base.get("speaker", "") or "")
                if base.get("tts_text"):
                    segment["tts_text"] = str(base.get("tts_text", "") or "")
                    segment["tts_group_id"] = base.get("tts_group_id", "")
                    segment["tts_group_start"] = float(base.get("tts_group_start", base.get("start", 0.0)) or 0.0)
                    segment["tts_group_end"] = float(base.get("tts_group_end", base.get("end", 0.0)) or 0.0)
        return parsed_segments

    def _uses_exact_full_block_subtitle_background(self) -> bool:
        """Whether the live ASS path needs exact, measured vector geometry."""
        try:
            return bool(
                getattr(self, "subtitle_background_cb", None)
                and self.subtitle_background_cb.isChecked()
                and getattr(self, "subtitle_background_width_combo", None)
                and str(self.subtitle_background_width_combo.currentData() or self.subtitle_background_width_combo.currentText()).strip().lower()
                in {"full_area", "full subtitle area", "full block"}
            )
        except Exception:
            return False

    def _build_live_subtitle_ass_snapshot(self, segments):
        """Capture all Qt-owned state before an ASS worker is started."""
        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        source_width = max(1, int(getattr(self.video_view, "video_source_width", 0) or 1920))
        source_height = max(1, int(getattr(self.video_view, "video_source_height", 0) or 1080))
        canvas_width, canvas_height = self._subtitle_render_dimensions()
        subtitle_style = copy.deepcopy(self.get_subtitle_export_style(segments=segments))
        if subtitle_style.get("custom_position_enabled") and (canvas_width != source_width or canvas_height != source_height):
            try:
                scale_mode = self.get_output_scale_mode_key()
                focus_x, focus_y = self.get_output_fill_focus()
                scale = max(canvas_width / source_width, canvas_height / source_height) if scale_mode == "fill" else min(canvas_width / source_width, canvas_height / source_height)
                displayed_w, displayed_h = source_width * scale, source_height * scale
                offset_x = (canvas_width - displayed_w) * (focus_x if scale_mode == "fill" else 0.5)
                offset_y = (canvas_height - displayed_h) * (focus_y if scale_mode == "fill" else 0.5)
                x_canvas = float(subtitle_style.get("custom_position_x", 50.0)) * canvas_width / 100.0
                y_canvas = float(subtitle_style.get("custom_position_y", 86.0)) * canvas_height / 100.0
                subtitle_style["custom_position_x"] = max(0.0, min(100.0, (x_canvas - offset_x) * 100.0 / displayed_w))
                subtitle_style["custom_position_y"] = max(0.0, min(100.0, (y_canvas - offset_y) * 100.0 / displayed_h))
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        signature = (video_path, canvas_width, canvas_height, repr(segments), repr(subtitle_style))
        return {
            "segments": copy.deepcopy(list(segments or [])),
            "video_width": canvas_width,
            "video_height": canvas_height,
            "style": subtitle_style,
            "signature": signature,
            "preview_dir": self.get_project_temp_dir("preview"),
        }

    @staticmethod
    def _write_subtitle_ass_from_snapshot(snapshot: dict, srt_path: str) -> str:
        """Worker-safe ASS generation.  It intentionally touches no Qt state."""
        from subtitle_builder import generate_srt
        generate_srt(snapshot["segments"], srt_path)
        style = snapshot["style"]
        return srt_to_ass(
            srt_path,
            video_width=snapshot["video_width"], video_height=snapshot["video_height"],
            alignment=style.get("alignment", 2), margin_v=style.get("margin_v", 30),
            font_name=style.get("font_name", "Arial"), font_size=style.get("font_size", 18),
            font_color=style.get("font_color", "&H00FFFFFF"), background_box=style.get("background_box", False),
            animation_style=style.get("animation", "Static"), highlight_color=style.get("highlight_color", "&H00FFFFFF"),
            outline_color=style.get("outline_color", "&H00000000"), outline_width=style.get("outline_width", 2.0),
            shadow_color=style.get("shadow_color", "&H80000000"), shadow_depth=style.get("shadow_depth", 1.0),
            background_color=style.get("background_color", "&H80000000"), background_alpha=style.get("background_alpha", 0.5),
            background_width=style.get("background_width", "fit_text"), background_shape=style.get("background_shape", "rectangle"),
            background_padding=style.get("background_padding", 6), background_radius=style.get("background_radius", 0),
            bold=style.get("bold", False), preset_key=style.get("preset_key", ""),
            auto_keyword_highlight=style.get("auto_keyword_highlight", False), animation_duration=style.get("animation_duration", 0.22),
            manual_highlights=style.get("manual_highlights", []), word_timings=style.get("word_timings", []),
            speaker_colors=style.get("speaker_colors", []), custom_position_enabled=style.get("custom_position_enabled", False),
            custom_position_x=style.get("custom_position_x", 50), custom_position_y=style.get("custom_position_y", 86),
            custom_position_bottom_y=style.get("custom_position_bottom_y"), single_line=style.get("single_line", False),
            font_scale=style.get("font_scale", 1.0), log_generation=False,
        )

    def _schedule_deferred_subtitle_ass_build(self, segments) -> bool:
        """Queue exact libass measurement after editing settles; never block UI."""
        if not self._uses_exact_full_block_subtitle_background() or not segments:
            return False
        snapshot = self._build_live_subtitle_ass_snapshot(segments)
        if snapshot["signature"] == getattr(self, "_live_preview_signature", None):
            return True
        self._subtitle_ass_request_token = int(getattr(self, "_subtitle_ass_request_token", 0)) + 1
        snapshot["token"] = self._subtitle_ass_request_token
        self._subtitle_ass_pending_snapshot = snapshot
        timer = getattr(self, "subtitle_ass_debounce_timer", None)
        if timer:
            timer.start()
        else:
            self._start_deferred_subtitle_ass_build()
        return True

    def _start_deferred_subtitle_ass_build(self):
        snapshot = getattr(self, "_subtitle_ass_pending_snapshot", None)
        if not snapshot:
            return
        self._subtitle_ass_pending_snapshot = None
        token = int(snapshot["token"])
        preview_dir = snapshot["preview_dir"]
        os.makedirs(preview_dir, exist_ok=True)
        srt_path = os.path.join(preview_dir, f"live_preview_subtitle_{token}.srt")

        def _worker():
            try:
                ass_path = self._write_subtitle_ass_from_snapshot(snapshot, srt_path)
                self.subtitle_ass_ready.emit(token, srt_path, ass_path, snapshot["signature"])
            except Exception as exc:
                self.runtime_log_received.emit(f"[Subtitle Background] Exact libass layout failed: {exc}")
                self.subtitle_ass_ready.emit(token, "", "", snapshot["signature"])

        worker = threading.Thread(target=_worker, name=f"subtitle-ass-{token}", daemon=True)
        self._subtitle_ass_worker_threads = [thread for thread in getattr(self, "_subtitle_ass_worker_threads", []) if thread.is_alive()]
        self._subtitle_ass_worker_threads.append(worker)
        worker.start()

    def _on_async_subtitle_ass_ready(self, token: int, srt_path: str, ass_path: str, signature):
        """Apply only the newest completed exact layout on the Qt thread."""
        if int(token) != int(getattr(self, "_subtitle_ass_request_token", 0)):
            return
        if not ass_path or not os.path.exists(ass_path):
            return
        self.live_preview_subtitle_path = srt_path
        self.live_preview_ass_path = ass_path
        self._live_preview_signature = signature
        self.processed_artifacts["subtitle_preview_srt"] = srt_path
        self.processed_artifacts["subtitle_preview_ass"] = ass_path
        can_render_libass = bool(
            getattr(self, "_use_libass_live_preview", False)
            and hasattr(self.media_player, "set_subtitle_file")
            and hasattr(self.media_player, "_sub_track_id")
        )
        try:
            if can_render_libass:
                self.media_player.set_subtitle_file(ass_path)
            self._loaded_live_ass_path = ass_path
            self._loaded_live_ass_signature = signature
            if hasattr(self, "video_view"):
                self.video_view.subtitle_item.set_text_rendering(can_render_libass)
            self.update_playback_subtitle_highlight(int(self.media_player.position() or 0))
        except Exception as exc:
            self.runtime_log_received.emit(f"[Subtitle Background] Could not apply exact layout: {exc}")

    def _write_live_preview_assets(self, segments):
        if not segments:
            self.live_preview_subtitle_path = ""
            self.live_preview_ass_path = ""
            self._live_preview_signature = None
            self._loaded_live_ass_path = ""
            self._loaded_live_ass_signature = None
            return "", ""

        # Full-block geometry is measured from libass itself.  Scheduling it
        # here keeps all callers (style controls, playback callbacks, project
        # load) non-blocking.  The previous exact track stays visible while a
        # newer style is being measured after the debounce interval.
        if self._uses_exact_full_block_subtitle_background():
            self._schedule_deferred_subtitle_ass_build(segments)
            return self.live_preview_subtitle_path, self.live_preview_ass_path

        # A pending Full Block worker must never re-apply an older ASS file
        # after the user switches the background off (or back to Fit Text).
        self._subtitle_ass_request_token = int(getattr(self, "_subtitle_ass_request_token", 0)) + 1

        preview_dir = self.get_project_temp_dir("preview")
        preview_srt_path = os.path.join(preview_dir, "live_preview_subtitle.srt")

        from subtitle_builder import generate_srt

        video_path = self.resolve_canonical_video_path() if hasattr(self, "resolve_canonical_video_path") else self.video_path_edit.text().strip()
        if (
            video_path
            and os.path.exists(video_path)
            and (
                not getattr(self.video_view, "video_source_width", 0)
                or not getattr(self.video_view, "video_source_height", 0)
            )
        ):
            self.refresh_video_dimensions(video_path)
        source_width = max(1, int(getattr(self.video_view, "video_source_width", 0) or 1920))
        source_height = max(1, int(getattr(self.video_view, "video_source_height", 0) or 1080))
        canvas_width, canvas_height = self._subtitle_render_dimensions()
        subtitle_style = self.get_subtitle_export_style(segments=segments)
        # MPV/libass renders subtitles on the source frame before MPV applies
        # its Fit/Fill presentation transform. Convert custom canvas-relative
        # anchors back into source coordinates so the visible result follows
        # the same point after framing.
        if subtitle_style.get("custom_position_enabled") and (canvas_width != source_width or canvas_height != source_height):
            try:
                scale_mode = self.get_output_scale_mode_key()
                focus_x, focus_y = self.get_output_fill_focus()
                scale = max(canvas_width / source_width, canvas_height / source_height) if scale_mode == "fill" else min(canvas_width / source_width, canvas_height / source_height)
                displayed_w, displayed_h = source_width * scale, source_height * scale
                offset_x = (canvas_width - displayed_w) * (focus_x if scale_mode == "fill" else 0.5)
                offset_y = (canvas_height - displayed_h) * (focus_y if scale_mode == "fill" else 0.5)
                x_canvas = float(subtitle_style.get("custom_position_x", 50.0)) * canvas_width / 100.0
                y_canvas = float(subtitle_style.get("custom_position_y", 86.0)) * canvas_height / 100.0
                subtitle_style["custom_position_x"] = max(0.0, min(100.0, (x_canvas - offset_x) * 100.0 / displayed_w))
                subtitle_style["custom_position_y"] = max(0.0, min(100.0, (y_canvas - offset_y) * 100.0 / displayed_h))
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        video_width, video_height = source_width, source_height
        preview_signature = (
            video_path,
            video_width,
            video_height,
            repr(segments),
            repr(subtitle_style),
        )
        if (
            preview_signature == getattr(self, "_live_preview_signature", None)
            and self.live_preview_subtitle_path
            and os.path.exists(self.live_preview_subtitle_path)
            and self.live_preview_ass_path
            and os.path.exists(self.live_preview_ass_path)
        ):
            return self.live_preview_subtitle_path, self.live_preview_ass_path

        # Subtitle or content changed. We no longer revert the media source!
        # Because we'll disable burned-in subs in muxed previews, the rendered
        # background is already blank-subbed and can host our live overlay/mpv track comfortably.
        # This solves the user's complaint that 'it reverts to original'.

        generate_srt(segments, preview_srt_path)
        self.live_preview_subtitle_path = preview_srt_path
        self.live_preview_ass_path = srt_to_ass(
            preview_srt_path,
            video_width=video_width,
            video_height=video_height,
            alignment=subtitle_style.get("alignment", 2),
            margin_v=subtitle_style.get("margin_v", 30),
            font_name=subtitle_style.get("font_name", "Arial"),
            font_size=subtitle_style.get("font_size", 18),
            font_color=subtitle_style.get("font_color", "&H00FFFFFF"),
            background_box=subtitle_style.get("background_box", False),
            animation_style=subtitle_style.get("animation", "Static"),
            highlight_color=subtitle_style.get("highlight_color", "&H00FFFFFF"),
            outline_color=subtitle_style.get("outline_color", "&H00000000"),
            outline_width=subtitle_style.get("outline_width", 2.0),
            shadow_color=subtitle_style.get("shadow_color", "&H80000000"),
            shadow_depth=subtitle_style.get("shadow_depth", 1.0),
            background_color=subtitle_style.get("background_color", "&H80000000"),
            background_alpha=subtitle_style.get("background_alpha", 0.5),
            background_width=subtitle_style.get("background_width", "fit_text"),
            background_shape=subtitle_style.get("background_shape", "rectangle"),
            background_padding=subtitle_style.get("background_padding", 6),
            background_radius=subtitle_style.get("background_radius", 0),
            bold=subtitle_style.get("bold", False),
            preset_key=subtitle_style.get("preset_key", ""),
            auto_keyword_highlight=subtitle_style.get("auto_keyword_highlight", False),
            animation_duration=subtitle_style.get("animation_duration", 0.22),
            manual_highlights=subtitle_style.get("manual_highlights", []),
            word_timings=subtitle_style.get("word_timings", []),
            speaker_colors=subtitle_style.get("speaker_colors", []),
            custom_position_enabled=subtitle_style.get("custom_position_enabled", False),
            custom_position_x=subtitle_style.get("custom_position_x", 50),
            custom_position_y=subtitle_style.get("custom_position_y", 86),
            custom_position_bottom_y=subtitle_style.get("custom_position_bottom_y"),
            single_line=subtitle_style.get("single_line", False),
            font_scale=subtitle_style.get("font_scale", 1.0),
            log_generation=False,
        )
        self._live_preview_signature = preview_signature
        self.processed_artifacts["subtitle_preview_srt"] = self.live_preview_subtitle_path
        self.processed_artifacts["subtitle_preview_ass"] = self.live_preview_ass_path
        return self.live_preview_subtitle_path, self.live_preview_ass_path

    def _resolve_live_preview_segments(self):
        single_line = bool(getattr(self, "subtitle_single_line_cb", None) and self.subtitle_single_line_cb.isChecked())
        if single_line and self.current_translated_segments:
            return self.get_active_segments(), "translated"

        translated_text = self.translated_text.toPlainText().strip()
        if translated_text and not translated_text.lower().startswith("translating with "):
            base_segments = self.current_translated_segments or self.current_segments
            translated_segments = self._segments_from_editor_text(translated_text, base_segments)
            if translated_segments:
                return translated_segments, "translated"

        transcript_text = self.transcript_text.toPlainText().strip()
        if transcript_text and not transcript_text.lower().startswith("transcribing..."):
            transcript_segments = self._segments_from_editor_text(transcript_text, self.current_segments)
            if transcript_segments:
                return transcript_segments, "transcript"

        active = self.get_active_segments()
        if active:
            return list(active), ("translated" if self.current_translated_segments else "transcript")

        return [], ""

    def _resolve_live_preview_subtitle_path(self):
        segments, editor_name = self._resolve_live_preview_segments()
        self.live_preview_segments = segments
        self.live_preview_editor_name = editor_name
        return self._write_live_preview_assets(segments)

    def _find_active_segment_index(self, position_ms: int, segments):
        active = self._find_active_segment_indices(position_ms, segments)
        return active[0] if active else -1

    def _find_active_segment_indices(self, position_ms: int, segments) -> list[int]:
        """Return the indices of every segment whose [start, end] contains
        position_ms. Multiple entries are returned when segments overlap in
        time, so the live overlay can stack them on separate lines.
        """
        position_seconds = max(0.0, float(position_ms) / 1000.0)
        # ``segments`` is already the editor's indexed list. Avoid copying a
        # long TS1 list on each 200 ms playback tick; the cache below only
        # needs its identity and length to detect a replacement.
        source = segments or []
        cache = getattr(self, "_playback_subtitle_activity_cache", None)
        source_key = (id(segments), len(source))
        if cache and cache.get("source_key") == source_key:
            # The end is exclusive so a tick landing exactly on the next cue
            # boundary recalculates the active set immediately.
            if cache["stable_start"] <= position_seconds < cache["stable_end"]:
                return list(cache["active_indices"])

        # This full scan happens only when playback crosses a subtitle/gap
        # boundary. The cached stable interval handles the several position
        # updates that occur while a cue remains unchanged.
        result: list[int] = []
        previous_boundary = 0.0
        next_boundary = None
        for idx, seg in enumerate(source):
            if isinstance(seg, dict):
                try:
                    start_s = float(seg.get("start", 0.0))
                    end_s = float(seg.get("end", 0.0))
                except (TypeError, ValueError):
                    continue
            else:
                try:
                    start_s = float(getattr(seg, "start", 0.0))
                    end_s = float(getattr(seg, "end", 0.0))
                except (TypeError, ValueError):
                    continue
            for boundary in (start_s, end_s):
                if boundary <= position_seconds:
                    previous_boundary = max(previous_boundary, boundary)
                else:
                    next_boundary = boundary if next_boundary is None else min(next_boundary, boundary)
            # Subtitle end times are exclusive. Allow 5ms tolerance on start_s
            # so integer millisecond rounding when seeking to cue start does not
            # accidentally land before the segment.
            if (start_s - 0.005) <= position_seconds < end_s:
                result.append(idx)
        stable_start = previous_boundary
        stable_end = next_boundary if next_boundary is not None else float("inf")
        self._playback_subtitle_activity_cache = {
            "source_key": source_key,
            "stable_start": stable_start,
            "stable_end": stable_end,
            "active_indices": list(result),
        }
        return result

    def _set_editor_highlight(self, editor, active_index: int):
        if not editor:
            return

        document = editor.document()
        revision = int(document.revision())
        editor_key = id(editor)
        state = (revision, active_index)
        if self._editor_highlight_state.get(editor_key) == state:
            return
        self._editor_highlight_state[editor_key] = state

        selections = []
        cached = self._editor_highlight_chunks.get(editor_key)
        if cached and cached[0] == revision:
            chunks = cached[1]
        else:
            text = editor.toPlainText()
            block_pattern = re.compile(
                r"(^|\n\n)(\d+\n\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}\n.*?)(?=\n\n\d+\n|\Z)",
                re.DOTALL,
            )
            chunks = [(match.start(2), match.end(2)) for match in block_pattern.finditer(text)]
            self._editor_highlight_chunks[editor_key] = (revision, chunks)

        if 0 <= active_index < len(chunks):
            start, end = chunks[active_index]
            selection = QTextEdit.ExtraSelection()
            selection.cursor = editor.textCursor()
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.KeepAnchor)
            selection.format.setBackground(QColor("#183248"))
            selection.format.setForeground(QColor("#EAF6FF"))
            selections.append(selection)
            temp_cursor = editor.textCursor()
            temp_cursor.setPosition(start)
            editor.setTextCursor(temp_cursor)
            editor.ensureCursorVisible()

        editor.setExtraSelections(selections)

    def update_playback_subtitle_highlight(self, position_ms: int):
        try:
            if not bool(getattr(self, "_subtitle_track_preview_visible", True)):
                self.timeline.set_active_segment_index(-1)
                if hasattr(self, "video_view"):
                    self.video_view.subtitle_item.hide()
                return
            segments = self.live_preview_segments or self.get_active_segments()
            active_index = self._find_active_segment_index(position_ms, segments)
            self.timeline.set_active_segment_index(active_index)
            inspector_visible = self._is_subtitle_inspector_details_visible()
            # Playback may update its last position even while paused.  Do
            # not let that stale position overwrite a subtitle the user has
            # just selected on TS1 (which commonly reset the inspector to
            # segment 1 at position 0).  Follow playback only while it is
            # actually running.
            is_playing = self._preview_is_playing()
            if is_playing and hasattr(self.timeline, "_timeline") and self.timeline._timeline:
                # Review Mode follows the active subtitle track so the
                # Subtitle Inspector can refresh with the cue under the
                # playhead. This intentionally overrides a paused edit
                # selection only while playback is running.
                subtitle_layer_id = ""
                if active_index >= 0:
                    for layer_id, segment_index in getattr(self.timeline, "_segment_indices", {}).items():
                        if int(segment_index) == int(active_index):
                            subtitle_layer_id = str(layer_id)
                            break
                if not subtitle_layer_id:
                    for track in self.timeline._timeline.tracks:
                        track_type = str(getattr(getattr(track, "type", ""), "value", getattr(track, "type", ""))).lower()
                        if track_type not in {"subtitle", "dub_subtitle"} and str(getattr(track, "name", "")) != "TS1":
                            continue
                        if track.layers:
                            subtitle_layer_id = str(getattr(track.layers[0], "id", "") or "")
                            break
                if subtitle_layer_id and str(getattr(self.timeline, "_selected_layer_id", "") or "") != subtitle_layer_id:
                    self.timeline._selected_layer_id = subtitle_layer_id
                    self.on_timeline_layer_selected(subtitle_layer_id)
            # Keep the selected TS1 cue synchronized with the playhead during
            # review playback even when the inspector was previously focused
            # on another panel.  set_selected_segment_index() updates the
            # inspector when it is visible and remains harmless otherwise.
            if is_playing and active_index >= 0 and active_index != getattr(self, "_selected_segment_index", -1):
                self.set_selected_segment_index(active_index, sync_ui=True)

            if inspector_visible:
                target_editor = None
                if self.live_preview_editor_name == "translated":
                    target_editor = self.translated_text
                elif self.live_preview_editor_name == "transcript":
                    target_editor = self.transcript_text
                elif self.current_translated_segments:
                    target_editor = self.translated_text
                elif self.current_segments:
                    target_editor = self.transcript_text

                self._set_segment_editor_highlight(active_index)
                self._set_editor_highlight(self.translated_text, active_index if target_editor is self.translated_text else -1)
                self._set_editor_highlight(self.transcript_text, active_index if target_editor is self.transcript_text else -1)

            # Update live overlay text for faster feedback
            if hasattr(self, "video_view"):
                if getattr(self, "_preview_video_has_burned_subtitles", False):
                    self.video_view.subtitle_item.set_text("")
                    if self.video_view.subtitle_item.isVisible():
                        self.video_view.subtitle_item.hide()
                else:
                    active_indices = self._find_active_segment_indices(position_ms, segments)
                    if active_indices:
                        active_lines = []
                        for i in active_indices:
                            s = segments[i]
                            if isinstance(s, dict):
                                t = (
                                    s.get("final_text")
                                    or s.get("text")
                                    or s.get("subtitle_text")
                                    or s.get("raw_translation")
                                    or s.get("original_text")
                                    or ""
                                )
                            else:
                                t = (
                                    getattr(s, "subtitle_text", "")
                                    or getattr(s, "final_text", "")
                                    or getattr(s, "original_text", "")
                                    or getattr(s, "text", "")
                                )
                            active_lines.append(str(t or ""))
                        if len(active_lines) == 1:
                            self.video_view.subtitle_item.set_text(active_lines[0])
                        else:
                            self.video_view.subtitle_item.set_lines(active_lines)
                        self._apply_live_subtitle_segment_color(segments[active_indices[0]])
                        self._set_live_subtitle_effects(segments[active_indices[0]], position_ms)
                        if not self.video_view.subtitle_item.isVisible():
                            self.video_view.subtitle_item.show()
                    else:
                        # Keep a real subtitle visible while paused so it
                        # remains a draggable editing layer after subtitle
                        # generation, even if the playhead is between cues.
                        if not self.media_player.is_playing():
                            self._show_subtitle_drag_layer(segments)
                        else:
                             self.video_view.subtitle_item.set_text("")
                             if self.video_view.subtitle_item.isVisible():
                                 self.video_view.subtitle_item.hide()
                self.video_view.reposition_subtitle()
        except Exception as exc:
            self.log(f"[Preview] subtitle highlight skipped: {exc}")

    def _show_subtitle_drag_layer(self, segments=None):
        """Show the active paused subtitle as a drag target.

        A selected Inspector row is not proof that its cue is active at the
        playhead. Showing row 1 while the player is at 00:00 made a rebuilt
        timeline look as if an old subtitle survived after its TS1 item had
        disappeared. Keep preview time authoritative, including while paused.
        """
        if not hasattr(self, "video_view") or getattr(self, "_preview_video_has_burned_subtitles", False):
            return
        items = list(segments or self.live_preview_segments or self.get_active_segments() or [])
        if not items:
            self.video_view.subtitle_item.set_text("")
            self.video_view.subtitle_item.hide()
            return
        try:
            position_ms = int(self.media_player.position())
        except Exception:
            position_ms = 0
        active_indices = self._find_active_segment_indices(position_ms, items)
        if not active_indices:
            self.video_view.subtitle_item.set_text("")
            self.video_view.subtitle_item.hide()
            return
        selected_index = int(getattr(self, "_selected_segment_index", -1))
        index = selected_index if selected_index in active_indices else active_indices[0]
        target_item = items[index]
        if isinstance(target_item, dict):
            text = str(
                target_item.get("final_text", "")
                or target_item.get("text", "")
                or target_item.get("subtitle_text", "")
                or target_item.get("raw_translation", "")
                or target_item.get("original_text", "")
                or ""
            ).strip()
        else:
            text = str(
                getattr(target_item, "subtitle_text", "")
                or getattr(target_item, "final_text", "")
                or getattr(target_item, "original_text", "")
                or getattr(target_item, "text", "")
                or ""
            ).strip()
        if not text:
            return
        self.video_view.subtitle_item.set_text(text)
        self._apply_live_subtitle_segment_color(items[index])
        self._set_live_subtitle_effects(items[index])
        self.video_view.subtitle_item.show()
        self.video_view.reposition_subtitle()

    def on_preview_subtitle_clicked(self):
        """Handle clicking the subtitle on the preview canvas to focus and select it."""
        if self._preview_is_playing():
            return
        try:
            position_ms = int(getattr(self.media_player, "position", lambda: 0)() or 0)
        except Exception:
            position_ms = 0
        items = list(self.live_preview_segments or self.get_active_segments() or [])
        active_indices = self._find_active_segment_indices(position_ms, items)
        if active_indices:
            self.on_timeline_segment_selected(active_indices[0])
        elif items:
            selected_index = int(getattr(self, "_selected_segment_index", -1))
            if 0 <= selected_index < len(items):
                self.on_timeline_segment_selected(selected_index)
        if hasattr(self, "video_view") and hasattr(self.video_view, "subtitle_item"):
            self.video_view.subtitle_item.set_selected(True)
            self.video_view.subtitle_item.set_editable(True)

    def sync_live_subtitle_preview(self):
        """Synchronize the live subtitle renderer and draggable Qt target."""
        if not hasattr(self, "media_player"):
            return
        self._playback_subtitle_activity_cache = None
        if not bool(getattr(self, "_subtitle_track_preview_visible", True)):
            self.media_player.clear_subtitle()
            if hasattr(self, "video_view"):
                self.video_view.subtitle_item.set_text("")
                self.video_view.subtitle_item.hide()
            return
        if getattr(self, "_preview_video_has_burned_subtitles", False):
            self.media_player.clear_subtitle()
            if hasattr(self, "video_view"):
                self.video_view.subtitle_item.set_text("")
                self.video_view.subtitle_item.hide()
            return
        can_render_libass = bool(
            getattr(self, "_use_libass_live_preview", False)
            and hasattr(self.media_player, "set_subtitle_file")
            and hasattr(self.media_player, "_sub_track_id")
        )
        if can_render_libass:
            segments, editor_name = self._resolve_live_preview_segments()
            if segments:
                self.live_preview_segments = list(segments)
                self.live_preview_editor_name = editor_name
                _srt_path, ass_path = self._write_live_preview_assets(segments)
                if ass_path and os.path.exists(ass_path):
                    # Re-adding an unchanged MPV subtitle track can briefly
                    # stall playback.  Only reload it once the final ASS path
                    # actually changes.
                    live_track_id = getattr(self.media_player, "_sub_track_id", -1)
                    has_live_mpv_track = isinstance(live_track_id, int) and live_track_id >= 0
                    if (
                        ass_path != getattr(self, "_loaded_live_ass_path", "")
                        or getattr(self, "_loaded_live_ass_signature", None) != getattr(self, "_live_preview_signature", None)
                        or not has_live_mpv_track
                    ):
                        self.media_player.set_subtitle_file(ass_path)
                        self._loaded_live_ass_path = ass_path
                        self._loaded_live_ass_signature = getattr(self, "_live_preview_signature", None)
                    if hasattr(self, "video_view"):
                        # The Qt item remains present for dragging but MPV's
                        # libass renderer supplies the visible subtitle.
                        self.video_view.subtitle_item.set_text_rendering(False)
                    position = int(self.media_player.position() or 0)
                    self.update_playback_subtitle_highlight(position)
                    return
            self.media_player.clear_subtitle()
            if hasattr(self, "video_view"):
                self.video_view.subtitle_item.set_text("")
                self.video_view.subtitle_item.hide()
            return
        self.media_player.clear_subtitle()
        if hasattr(self, "video_view"):
            self.video_view.subtitle_item.set_text_rendering(True)
        segments, editor_name = self._resolve_live_preview_segments()
        if segments:
            self.live_preview_segments = list(segments)
            self.live_preview_editor_name = editor_name
        else:
            self.live_preview_segments = list(self.get_active_segments() or [])
        position = 0
        try:
            position = int(self.media_player.position())
        except Exception:
            pass
        self.update_playback_subtitle_highlight(position)
