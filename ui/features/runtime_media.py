"""Runtime logging, resources, and preview-media feature."""

import glob
import hashlib
import json
import os
import time

from PySide6.QtCore import QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services import ResourceDownloadService
from runtime_profile import is_remote_profile
from utils.display_utils import clear_log as clear_log_impl, log_message as log_message_impl, show_error as show_error_impl
from worker_adapters import TimelineThumbnailWorker, TimelineWaveformWorker
from utils.thread_lifecycle import release_thread_when_stopped


class RuntimeMediaMixin:
    def log(self, message: str):
        log_message_impl(self, message)

    def _append_runtime_log_entry(self, message: str):
        from datetime import datetime

        text = str(message or "").strip()
        if not text:
            return
        entry = f"{datetime.now().strftime('%H:%M:%S')}  {text}"
        self._pending_runtime_log_entries.append(entry)
        if not self._runtime_log_flush_timer.isActive():
            self._runtime_log_flush_timer.start()

    def _flush_runtime_log_entries(self):
        entries = self._pending_runtime_log_entries
        self._pending_runtime_log_entries = []
        if not entries:
            return
        self._runtime_logs.extend(entries)
        if len(self._runtime_logs) > 10000:
            del self._runtime_logs[:-10000]
        view = getattr(self, "runtime_log_view", None)
        # The Logs view belongs to the Advanced workflow page. Keep the
        # in-memory log complete, but defer text layout/repaint work until
        # the user actually opens that page.
        if view is not None and view.isVisible():
            already_rendered = int(getattr(self, "_runtime_log_view_entry_count", 0))
            if already_rendered != len(self._runtime_logs) - len(entries):
                view.setPlainText("\n".join(self._runtime_logs))
            else:
                view.appendPlainText("\n".join(entries))
            self._runtime_log_view_entry_count = len(self._runtime_logs)

    def sync_runtime_log_view(self, *_args):
        """Populate deferred runtime logs when the Advanced page is shown."""
        view = getattr(self, "runtime_log_view", None)
        if view is None or not view.isVisible():
            return
        logs = getattr(self, "_runtime_logs", [])
        if int(getattr(self, "_runtime_log_view_entry_count", 0)) == len(logs):
            return
        view.setPlainText("\n".join(logs))
        self._runtime_log_view_entry_count = len(logs)

    def clear_log(self):
        clear_log_impl(self)

    def export_runtime_logs(self):
        default_name = f"viustudio_logs_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        default_path = os.path.join(self.workspace_root, default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Runtime Logs",
            default_path,
            "Text Files (*.txt);;All Files (*)",
        )
        if not file_path:
            return
        try:
            self._flush_runtime_log_entries()
            with open(file_path, "w", encoding="utf-8") as handle:
                entries = getattr(self, "_runtime_logs", [])
                handle.write("\n".join(entries))
                handle.write("\n" if entries else "")
            self.log(f"[Logs] Exported runtime logs to {file_path}")
        except OSError as exc:
            QMessageBox.warning(self, "Export Logs", f"Could not export logs:\n{exc}")

    def _register_progress_dialog(self, dialog):
        if dialog is None:
            return
        self._tracked_progress_dialogs = [d for d in self._tracked_progress_dialogs if d is not None]
        if dialog not in self._tracked_progress_dialogs:
            self._tracked_progress_dialogs.append(dialog)
            try:
                dialog.destroyed.connect(lambda *_args, dlg=dialog: self._unregister_progress_dialog(dlg))
            except Exception:
                pass
        self._update_progress_reopen_button()

    def _unregister_progress_dialog(self, dialog):
        self._tracked_progress_dialogs = [d for d in self._tracked_progress_dialogs if d is not dialog]
        self._update_progress_reopen_button()

    def _active_progress_dialogs(self):
        active = []
        for dialog in list(getattr(self, "_tracked_progress_dialogs", []) or []):
            if dialog is None:
                continue
            try:
                if dialog.isVisible():
                    active.append(dialog)
                    continue
                if getattr(dialog, "isHidden", None) and not dialog.isHidden():
                    active.append(dialog)
            except Exception:
                continue
        return active

    def _update_progress_reopen_button(self):
        button = getattr(self, "show_progress_btn", None)
        if button is None:
            return
        tracked = [d for d in getattr(self, "_tracked_progress_dialogs", []) if d is not None]
        try:
            button.setVisible(bool(tracked))
            button.setEnabled(bool(tracked))
        except RuntimeError:
            # Qt can destroy the toolbar button before a tracked progress
            # dialog emits its destroyed signal during application shutdown.
            pass

    def show_active_progress_dialog(self):
        dialogs = [d for d in getattr(self, "_tracked_progress_dialogs", []) if d is not None]
        if not dialogs:
            self._update_progress_reopen_button()
            return
        dialog = dialogs[-1]
        try:
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
        except Exception:
            pass
        self._update_progress_reopen_button()

    def _resource_service(self) -> ResourceDownloadService:
        return ResourceDownloadService(self.workspace_root)

    def _open_vietdict_folder(self, resource_id: str):
        from runtime_paths import models_path
        dir_path = models_path("vietnormalizer")
        os.makedirs(dir_path, exist_ok=True)
        os.startfile(dir_path)

    def _create_vietdict_template(self, resource_id: str):
        import csv
        from runtime_paths import models_path
        dir_path = models_path("vietnormalizer")
        os.makedirs(dir_path, exist_ok=True)

        acronyms_path = os.path.join(dir_path, "acronyms.csv")
        if not os.path.exists(acronyms_path):
            with open(acronyms_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["acronym", "transliteration"])
                w.writerow(["vtv", "vô tuyến truyền hình"])
                w.writerow(["CLB", "câu lạc bộ"])
            print(f"[VietDict] Created template: {acronyms_path}")

        nonvn_path = os.path.join(dir_path, "non-vietnamese-words.csv")
        if not os.path.exists(nonvn_path):
            with open(nonvn_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["original", "transliteration"])
                w.writerow(["iPhone", "ai phôn"])
            print(f"[VietDict] Created template: {nonvn_path}")

        os.startfile(dir_path)

    def _vietdict_add_row(self, table):
        from PySide6.QtWidgets import QTableWidgetItem
        r = table.rowCount()
        table.insertRow(r)
        table.setItem(r, 0, QTableWidgetItem(""))
        table.setItem(r, 1, QTableWidgetItem(""))
        table.scrollToBottom()

    def _vietdict_remove_row(self, table):
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        for r in rows:
            table.removeRow(r)

    def open_normalizer_dict_dialog(self):
        import csv
        from pathlib import Path
        from runtime_paths import models_path
        custom_dir = Path(models_path("vietnormalizer"))
        custom_dir.mkdir(parents=True, exist_ok=True)

        DICT_DEFS = [
            {"label": "Acronyms", "file": "acronyms.csv", "col_a": "acronym", "col_b": "transliteration"},
            {"label": "Non-Vietnamese Words", "file": "non-vietnamese-words.csv", "col_a": "original", "col_b": "transliteration"},
        ]

        dialog = QDialog(self)
        dialog.setWindowTitle("Normalizer Dictionary")
        dialog.setModal(True)
        dialog.resize(700, 520)
        dialog.setStyleSheet("""
            QDialog { background-color: #0f1724; }
            QLabel { color: #d7e3f4; background-color: transparent; }
            QTableWidget { background-color: #132033; color: #d7e3f4; gridline-color: #2f4868;
                border: 1px solid #2f4868; border-radius: 8px; font-size: 13px; }
            QTableWidget::item:selected { background-color: #29405d; color: #f8fbff; }
            QHeaderView::section { background-color: #1a2c44; color: #8ad7ff; border: none;
                padding: 6px 8px; font-weight: 700; font-size: 12px; }
            QPushButton { background-color: #22344d; color: #f8fbff; border: 1px solid #34506f;
                border-radius: 8px; padding: 6px 16px; font-weight: 600; }
            QPushButton:hover { background-color: #29405d; }
            QPushButton#dangerBtn { background-color: #5a1a1a; border-color: #8b2a2a; }
            QPushButton#dangerBtn:hover { background-color: #7a2828; }
            QPushButton#primaryBtn { background-color: #1a4a5a; border-color: #2a6a8b; }
            QPushButton#primaryBtn:hover { background-color: #1e5a6e; }
            QTabWidget::pane { border: 1px solid #2f4868; background-color: #0f1724; border-radius: 8px; }
            QTabBar::tab { background-color: #1a2c44; color: #9fb3ca; padding: 8px 20px; border: 1px solid #2f4868;
                border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; }
            QTabBar::tab:selected { background-color: #132033; color: #8ad7ff; }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Manage Normalizer Dictionary", dialog)
        title.setStyleSheet("color: #f8fbff; font-size: 16px; font-weight: 700;")
        layout.addWidget(title)

        hint = QLabel(f"Dictionary location: {custom_dir}\nEntries here override built-in normalizer rules.", dialog)
        hint.setStyleSheet("color: #9fb3ca; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        from PySide6.QtWidgets import QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView
        tabs = QTabWidget(dialog)
        layout.addWidget(tabs, 1)

        tables = {}

        for defn in DICT_DEFS:
            tab = QWidget(dialog)
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(8, 8, 8, 8)
            tab_layout.setSpacing(8)

            table = QTableWidget(0, 2, dialog)
            table.setHorizontalHeaderLabels([defn["col_a"].title(), defn["col_b"].title()])
            table.horizontalHeader().setStretchLastSection(True)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.verticalHeader().setVisible(False)
            tab_layout.addWidget(table, 1)

            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            add_btn = QPushButton("+ Add Row", dialog)
            remove_btn = QPushButton("Remove Selected", dialog)
            remove_btn.setObjectName("dangerBtn")
            btn_row.addWidget(add_btn)
            btn_row.addWidget(remove_btn)
            btn_row.addStretch()
            tab_layout.addLayout(btn_row)

            add_btn.clicked.connect(lambda _checked=False, t=table: self._vietdict_add_row(t))
            remove_btn.clicked.connect(lambda _checked=False, t=table: self._vietdict_remove_row(t))

            tables[defn["file"]] = {"table": table, "defn": defn}
            tabs.addTab(tab, defn["label"])

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addStretch()

        save_btn = QPushButton("Save All", dialog)
        save_btn.setObjectName("primaryBtn")
        close_btn = QPushButton("Close", dialog)
        close_btn.clicked.connect(dialog.accept)
        bottom_row.addWidget(save_btn)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

        def _load_all():
            for fname, meta in tables.items():
                file_path = custom_dir / fname
                table = meta["table"]
                table.setRowCount(0)
                if file_path.exists():
                    try:
                        with open(file_path, encoding="utf-8", newline="") as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                a = (row.get(meta["defn"]["col_a"]) or "").strip()
                                b = (row.get(meta["defn"]["col_b"]) or "").strip()
                                if a or b:
                                    r = table.rowCount()
                                    table.insertRow(r)
                                    table.setItem(r, 0, QTableWidgetItem(a))
                                    table.setItem(r, 1, QTableWidgetItem(b))
                    except Exception:
                        pass

        def _save_all():
            for fname, meta in tables.items():
                file_path = custom_dir / fname
                table = meta["table"]
                rows = []
                for r in range(table.rowCount()):
                    a = (table.item(r, 0).text() if table.item(r, 0) else "").strip()
                    b = (table.item(r, 1).text() if table.item(r, 1) else "").strip()
                    if a or b:
                        rows.append({meta["defn"]["col_a"]: a, meta["defn"]["col_b"]: b})
                with open(file_path, "w", encoding="utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=[meta["defn"]["col_a"], meta["defn"]["col_b"]])
                    w.writeheader()
                    w.writerows(rows)
            print("[VietDict] Dictionary saved.")

        save_btn.clicked.connect(_save_all)

        _load_all()
        dialog.exec()

    def _missing_resource_entries(self, *, include_whisper: bool = False, include_voice: bool = False, include_ocr: bool = False, validate_pipeline_runtime: bool = False) -> list[tuple[str, str]]:
        service = self._resource_service()
        missing: list[tuple[str, str]] = []

        if include_whisper and not is_remote_profile():
            engine = self.get_transcription_engine()
            if engine == "sensevoice":
                missing.extend(service.validate_sensevoice_runtime())
            else:
                model_name = self.get_whisper_model_name()
                resource_id = f"whisper:{model_name}"
                if not service.is_resource_installed(resource_id):
                    missing.append((resource_id, f"Whisper {model_name.title()} model"))

        if include_voice and not is_remote_profile():
            voice_name = self.get_active_voice_name()
            if voice_name and not str(voice_name).startswith(("edge:", "f5:", "zerotts:", "kokoro:")):
                resource_id = f"voice:{voice_name}"
                if not service.is_resource_installed(resource_id):
                    voice_label = voice_name
                    voice_entry = self.voice_catalog_map.get(voice_name) if hasattr(self, "voice_catalog_map") else None
                    if isinstance(voice_entry, dict):
                        voice_label = str(voice_entry.get("name", voice_name)).strip() or voice_name
                    missing.append((resource_id, f"Local voice: {voice_label}"))

        if include_ocr:
            missing.extend(service.validate_ocr_runtime())

        if include_voice and not is_remote_profile():
            missing.extend(service.validate_tts_voice_runtime(self.get_active_voice_name()))

        if validate_pipeline_runtime and not is_remote_profile():
            missing.extend(service.validate_pipeline_runtime())

        deduped: list[tuple[str, str]] = []
        seen = set()
        for item in missing:
            if item[0] in seen:
                continue
            seen.add(item[0])
            deduped.append(item)
        return deduped

    def ensure_required_resources(self, action_label: str, *, include_whisper: bool = False, include_voice: bool = False, include_ocr: bool = False, validate_pipeline_runtime: bool = False) -> bool:
        missing = self._missing_resource_entries(
            include_whisper=include_whisper,
            include_voice=include_voice,
            include_ocr=include_ocr,
            validate_pipeline_runtime=validate_pipeline_runtime,
        )
        if not missing:
            return True

        missing_lines = "\n".join(f"- {label}" for _resource_id, label in missing)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("VIUStudio Cannot Start This Step")
        box.setText(f"{action_label} cannot start because a required local component is unavailable.")
        box.setInformativeText(
            "The exact cause is listed below. Use Manage Resources for downloadable "
            "models, or fix the shown folder/permission problem before trying again:\n\n"
            f"{missing_lines}"
        )
        open_btn = box.addButton("Manage Resources", QMessageBox.AcceptRole)
        box.addButton("Close", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self.open_resource_manager_dialog()
        return False

    def open_resource_manager_dialog(self, focus_resource_id: str | None = None, auto_start: bool = False):
        from views.resource_manager import open_resource_manager
        open_resource_manager(
            self.workspace_root,
            parent=self,
            on_finished=lambda: self._on_resource_download_complete(),
            focus_resource_id=focus_resource_id,
            auto_start=auto_start,
        )

    def _on_resource_download_complete(self):
        try:
            self.load_voice_preview_catalog()
        except Exception:
            pass
        self.refresh_ui_state()

    def show_error(self, title: str, short_msg: str, details: str = ""):
        show_error_impl(self, title, short_msg, details)

    def stabilize_button(self, button: QPushButton, min_width: int = 220, min_height: int = 42):
        button.setMinimumWidth(min_width)
        button.setMinimumHeight(min_height)
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def make_helper_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("helperLabel")
        return label

    def using_existing_audio_source(self) -> bool:
        mixed_path = self._normalize_local_file_path(
            self.mixed_audio_edit.text().strip() if hasattr(self, "mixed_audio_edit") else ""
        )
        use_existing = bool(hasattr(self, "use_existing_audio_radio") and self.use_existing_audio_radio.isChecked())
        return bool(use_existing and mixed_path and os.path.exists(mixed_path))

    def _normalize_local_file_path(self, path: str) -> str:
        value = str(path or "").replace("\r", "").replace("\n", "").replace("\t", " ").strip().strip('"').strip("'")
        if not value:
            return ""

        value = os.path.expandvars(os.path.expanduser(value))
        candidates = []
        if os.path.isabs(value):
            candidates.append(value)
        else:
            candidates.append(os.path.join(self.workspace_root, value))
            current_project = getattr(self, "current_project_state", None)
            if current_project and getattr(current_project, "project_root", ""):
                candidates.append(os.path.join(current_project.project_root, value))
            candidates.append(os.path.join(self.workspace_root, value))

        for candidate in candidates:
            normalized = os.path.normpath(os.path.abspath(candidate))
            if os.path.exists(normalized):
                return normalized

        fallback = candidates[0] if candidates else value
        return os.path.normpath(os.path.abspath(fallback))

    def resolve_selected_audio_path(self) -> str:
        if self.using_existing_audio_source():
            return self._normalize_local_file_path(self.mixed_audio_edit.text().strip())
        candidates = [
            self.processed_artifacts.get("mixed_vi"),
            self.last_mixed_vi_path,
            self.last_voice_vi_path,
        ]
        for candidate in candidates:
            normalized = self._normalize_local_file_path(candidate)
            if normalized and os.path.exists(normalized):
                return normalized
        return ""

    def _resolve_preview_voice_only_audio_path(self) -> str:
        if self.using_existing_audio_source():
            return ""
        candidates = [
            self.processed_artifacts.get("voice_vi"),
            self.last_voice_vi_path,
        ]
        for candidate in candidates:
            normalized = self._normalize_local_file_path(candidate)
            if normalized and os.path.exists(normalized):
                return normalized
        return ""

    def _resolve_preview_background_audio_path(self) -> str:
        audio_mode_key = str(self.get_audio_handling_mode() or "fast").strip().lower()
        if audio_mode_key == "clean":
            candidates = [self.last_music_path]
        else:
            candidates = [
                self.audio_source_edit.text().strip() if hasattr(self, "audio_source_edit") else "",
                self.processed_artifacts.get("audio_extracted"),
                self.last_extracted_audio,
                self.last_music_path,
            ]
        for candidate in candidates:
            normalized = self._normalize_local_file_path(candidate)
            if normalized and os.path.exists(normalized):
                return normalized
        return ""

    def _resolve_preview_mixed_audio_path(self) -> str:
        if self.using_existing_audio_source():
            audio_path = self._normalize_local_file_path(self.mixed_audio_edit.text().strip())
            return audio_path if audio_path and os.path.exists(audio_path) else ""
        voice_only = self._resolve_preview_voice_only_audio_path()
        background_audio = self._resolve_preview_background_audio_path()
        if not voice_only or not background_audio:
            return ""

        try:
            voice_stat = os.stat(voice_only)
            background_stat = os.stat(background_audio)
        except OSError:
            return ""

        segments = list(self.get_active_segments() or [])
        audio_mode_key = str(self.get_audio_handling_mode() or "fast").strip().lower()
        original_volume = int(self.audio_a1_volume_slider.value()) if hasattr(self, "audio_a1_volume_slider") else 50
        dub_volume = int(self.audio_a2_volume_slider.value()) if hasattr(self, "audio_a2_volume_slider") else 100

        a1_muted = False
        if hasattr(self, "_is_audio_track_muted"):
            a1_muted = bool(self._is_audio_track_muted("A1 Audio") or self._is_audio_track_muted("A1"))
        if not a1_muted and hasattr(self, "_mute_original"):
            a1_muted = bool(self._mute_original)
        if a1_muted:
            original_volume = 0

        a2_muted = False
        if hasattr(self, "_is_audio_track_muted"):
            a2_muted = bool(self._is_audio_track_muted("A2 Dub") or self._is_audio_track_muted("A2"))
        if not a2_muted and hasattr(self, "_mute_dubbed"):
            a2_muted = bool(self._mute_dubbed)
        if a2_muted:
            dub_volume = 0
        signature_payload = {
            "voice": os.path.abspath(voice_only),
            "voice_size": int(voice_stat.st_size),
            "voice_mtime_ns": int(getattr(voice_stat, "st_mtime_ns", int(voice_stat.st_mtime * 1_000_000_000))),
            "background": os.path.abspath(background_audio),
            "background_size": int(background_stat.st_size),
            "background_mtime_ns": int(getattr(background_stat, "st_mtime_ns", int(background_stat.st_mtime * 1_000_000_000))),
            "audio_mode": audio_mode_key,
            "original_volume": original_volume,
            "dub_volume": dub_volume,
            "segments": [
                {
                    "start": round(float(seg.get("start", 0.0)), 3),
                    "end": round(float(seg.get("end", 0.0)), 3),
                }
                for seg in segments
            ],
        }
        mix_hash = hashlib.sha1(json.dumps(signature_payload, ensure_ascii=True, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        output_path = os.path.join(self.get_workspace_temp_root(create=True), f"timeline_preview_mix_{mix_hash}.wav")
        if os.path.exists(output_path):
            return output_path

        try:
            from audio_mixer import mix_original_with_dub
            original_gain_db = self._percent_to_db(original_volume)
            dub_gain_db = self._percent_to_db(dub_volume)
            mix_original_with_dub(
                original_wav_path=background_audio,
                dub_wav_path=voice_only,
                output_wav_path=output_path,
                original_gain_db=original_gain_db,
                dub_gain_db=dub_gain_db,
            )
        except Exception as exc:
            self.log(f"[Preview] timeline mix fallback to voice-only: {exc}")
            return ""
        return output_path

    def resolve_timeline_audio_visualization_path(self) -> str:
        preview_mode = str(getattr(self, "_preview_audio_track_mode", "original") or "original").strip().lower()
        if preview_mode == "original":
            candidates = [
                self.audio_source_edit.text().strip() if hasattr(self, "audio_source_edit") else "",
                self.processed_artifacts.get("vocals"),
                self.processed_artifacts.get("audio_extracted"),
                self.last_vocals_path,
                self.last_extracted_audio,
            ]
            for candidate in candidates:
                normalized = self._normalize_local_file_path(candidate)
                if normalized and os.path.exists(normalized):
                    return normalized

        dubbed_audio_kind, dubbed_audio = self._resolve_preview_dubbed_playback_source()
        if dubbed_audio_kind in ("mixed", "voice") and dubbed_audio and os.path.exists(dubbed_audio):
            return dubbed_audio

        candidates = [
            self.audio_source_edit.text().strip() if hasattr(self, "audio_source_edit") else "",
            self.processed_artifacts.get("vocals"),
            self.processed_artifacts.get("audio_extracted"),
            self.last_vocals_path,
            self.last_extracted_audio,
        ]
        for candidate in candidates:
            normalized = self._normalize_local_file_path(candidate)
            if normalized and os.path.exists(normalized):
                return normalized
        return ""

    def _resolve_preview_original_video_path(self) -> str:
        timeline_source = str(getattr(self, "_timeline_preview_source", "") or "")
        timeline_sources = set()
        try:
            timeline_sources = {
                os.path.normcase(os.path.abspath(str(item.get("source", "") or "")))
                for item in self.get_timeline_video_clips(existing_only=True)
            }
        except Exception:
            pass
        if timeline_source and os.path.normcase(os.path.abspath(timeline_source)) in timeline_sources:
            normalized = self._normalize_local_file_path(timeline_source)
            if normalized and os.path.exists(normalized):
                return normalized
        canonical = getattr(self, "resolve_canonical_video_path", None)
        if callable(canonical):
            return canonical()
        video_path = self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else ""
        normalized = self._normalize_local_file_path(video_path)
        return normalized if normalized and os.path.exists(normalized) else ""

    def _resolve_preview_dubbed_audio_path(self) -> str:
        mixed_audio = self._resolve_preview_mixed_audio_path()
        if mixed_audio:
            return mixed_audio
        return self._resolve_preview_voice_only_audio_path()

    def _has_preview_dubbed_audio_source(self) -> bool:
        if self.using_existing_audio_source():
            audio_path = self._normalize_local_file_path(self.mixed_audio_edit.text().strip())
            return bool(audio_path and os.path.exists(audio_path))
        return bool(self._resolve_preview_voice_only_audio_path())

    def _timeline_audio_track_mutes(self) -> tuple[bool, bool] | None:
        if not hasattr(self, "timeline") or not getattr(self.timeline, "_timeline", None):
            return None
        a1_muted = None
        a2_muted = None
        for track in self.timeline._timeline.tracks:
            if track.name == "A1 Audio":
                a1_muted = bool(track.muted)
            elif track.name == "A2 Dub":
                a2_muted = bool(track.muted)
        if a1_muted is None and a2_muted is None:
            return None
        return bool(a1_muted), bool(a2_muted)

    def _resolve_preview_dubbed_playback_source(self) -> tuple[str, str]:
        """Resolve which audio file represents the dubbed track in preview.

        For preview we want PURE TTS (voice_vi) so the user hears only
        the new dub voice with natural gaps between segments. The mixed
        (TTS+background) version is only used for final export.

        Returns ("voice", path) | ("mixed", path) | ("original", "").
        """
        track_mutes = self._timeline_audio_track_mutes()
        voice_only = self._resolve_preview_voice_only_audio_path()
        mixed_audio = self._resolve_preview_mixed_audio_path()

        if not track_mutes:
            if voice_only:
                return "voice", voice_only
            if mixed_audio:
                return "mixed", mixed_audio
            return "original", ""

        a1_muted, a2_muted = track_mutes
        if a2_muted:
            return "original", ""
        # Prefer pure TTS for preview in all other cases.
        if voice_only:
            return "voice", voice_only
        if mixed_audio:
            return "mixed", mixed_audio
        return "original", ""

    def _preview_audio_track_choices(self) -> list[tuple[str, str]]:
        choices = [("Original Audio", "original")]
        if self._has_preview_dubbed_audio_source():
            choices.append(("Dub Voice", "dubbed"))
        return choices

    def _preferred_preview_audio_track_mode(self) -> str:
        track_mutes = self._timeline_audio_track_mutes()
        if track_mutes:
            _a1_muted, a2_muted = track_mutes
            if a2_muted:
                return "original"
        mode = str(self.get_output_mode_key() or "subtitle").strip().lower()
        if mode in ("voice", "both"):
            if self._has_preview_dubbed_audio_source():
                return "dubbed"
        return "original"

    def sync_preview_audio_track_to_output(self, *, apply_to_player: bool = True, force: bool = False):
        target_mode = self._preferred_preview_audio_track_mode()
        self._preview_audio_track_mode = target_mode

        if not apply_to_player or not getattr(self, "media_player", None):
            return

        source_video = self._resolve_preview_original_video_path()
        current_source = self._normalize_local_file_path(str(getattr(self.media_player, "_source_path", "") or ""))
        should_apply = bool(force) or not current_source
        if source_video and current_source:
            should_apply = bool(force) or os.path.abspath(current_source) == os.path.abspath(source_video)

        if should_apply:
            self._apply_preview_audio_track_selection()
            return

    def _apply_preview_audio_track_selection(self):
        if (
            getattr(self, "_preview_audio_track_switching", False)
            or not hasattr(self, "media_player")
            or not getattr(self, "media_player", None)
        ):
            return
        source_video = self._resolve_preview_original_video_path()
        if not source_video:
            return

        # Always load BOTH the original audio file (extracted audio) and
        # the dubbed audio file as separate sidecar streams. Per-track mute
        # is controlled by the timeline track labels (A1 Original / A2 Dub).
        dubbed_audio_kind, dubbed_audio = self._resolve_preview_dubbed_playback_source()
        if not dubbed_audio or dubbed_audio_kind == "original":
            dubbed_audio = ""
        original_audio = self._resolve_preview_original_audio_path()

        try:
            current_position = int(self.media_player.position())
        except Exception:
            current_position = 0
        try:
            was_playing = bool(self.media_player.is_playing())
        except Exception:
            was_playing = False

        current_source = str(getattr(self.media_player, "_source_path", "") or "")
        should_reset_source = not current_source or os.path.abspath(current_source) != os.path.abspath(source_video)

        self._preview_audio_track_switching = True
        try:
            if should_reset_source:
                try:
                    self.media_player.pause()
                except Exception:
                    pass
                self.media_player.setSource(QUrl.fromLocalFile(source_video))
                self.refresh_video_dimensions(source_video)
                self._preview_video_has_burned_subtitles = False
                self.sync_live_subtitle_preview()
            # Always load the original audio sidecar when available
            if hasattr(self.media_player, "set_original_audio_file"):
                if original_audio:
                    self.media_player.set_original_audio_file(original_audio)
                else:
                    try:
                        self.media_player._clear_original_audio()
                    except Exception:
                        pass
            if dubbed_audio:
                self.media_player.set_audio_file(dubbed_audio)
            else:
                self.media_player.clear_audio()
            if current_position > 0:
                try:
                    self.media_player.setPosition(current_position)
                except Exception:
                    pass
            if was_playing:
                try:
                    self.media_player.play()
                    if hasattr(self, "timeline"):
                        self.timeline.set_playing(True)
                except Exception:
                    pass
            else:
                if hasattr(self, "timeline"):
                    self.timeline.set_playing(False)
            # Only log the preview audio state when at least one audio sidecar
            # was actually applied. Logging "silent" on a freshly opened
            # video (no generate/voice done yet) is misleading noise —
            # Bug 3.
            if original_audio or dubbed_audio:
                active_label = "both" if (original_audio and dubbed_audio) else (
                    "dubbed" if dubbed_audio else "original"
                )
                self.log(f"[Preview] audio: {active_label}")
        finally:
            self._preview_audio_track_switching = False
        self.schedule_timeline_visual_refresh(waveform=True, thumbnails=True)

    def _resolve_preview_original_audio_path(self) -> str:
        """Resolve the original audio file path (separate from source video).

        Fast mode: full extracted audio (vocals + music)
        Clean mode: background stem only (no vocals, to avoid double voices)
        Fallback: extracted_audio artifact or active source video
        """
        current_preview_source = os.path.abspath(str(getattr(self, "_timeline_preview_source", "") or ""))
        canonical = getattr(self, "resolve_canonical_video_path", None)
        main_path = canonical() if callable(canonical) else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        main_video = os.path.abspath(str(self._normalize_local_file_path(main_path) or ""))
        
        # When previewing a secondary clip from multi-video timeline, play its own audio directly
        if current_preview_source and current_preview_source != main_video and os.path.exists(current_preview_source):
            return current_preview_source

        audio_mode = str(self.get_audio_handling_mode() or "fast").strip().lower()
        candidates: list[str] = []
        if audio_mode == "clean":
            candidates.extend([
                self.last_music_path,
                self.processed_artifacts.get("music"),
            ])
        candidates.extend([
            self.processed_artifacts.get("extracted_audio"),
            self.last_extracted_audio,
            self.audio_source_edit.text().strip() if hasattr(self, "audio_source_edit") else "",
        ])
        for candidate in candidates:
            if not candidate:
                continue
            normalized = self._normalize_local_file_path(candidate)
            if normalized and os.path.exists(normalized):
                return normalized
        source_video = current_preview_source if (current_preview_source and os.path.exists(current_preview_source)) else self._resolve_preview_original_video_path()
        if source_video:
            return source_video
        return ""

    def on_preview_audio_track_changed(self, index: int):
        if getattr(self, "_preview_audio_track_switching", False) or not hasattr(self, "preview_audio_track_combo"):
            return
        mode = str(self.preview_audio_track_combo.itemData(index) or "original").strip().lower()
        self._preview_audio_track_mode = mode if mode in ("original", "dubbed") else "original"
        self._apply_preview_audio_track_selection()

    def _waveform_temp_path(self) -> str:
        canonical = getattr(self, "resolve_canonical_video_path", None)
        video_path = canonical() if callable(canonical) else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        if not video_path:
            return ""
        clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []
        identity = repr(clips) if len(clips) > 1 else video_path
        video_hash = hashlib.md5(identity.encode("utf-8")).hexdigest()[:12]
        return os.path.join(self.get_workspace_temp_root(create=True), f"waveform_{video_hash}.wav")

    def _timeline_waveform_request_signature(self):
        # A1 represents the source video's original audio. It must remain
        # stable as Transcript/Translate/TTS change project artifacts.
        canonical = getattr(self, "resolve_canonical_video_path", None)
        video_path = self._normalize_local_file_path(canonical() if callable(canonical) else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else ""))
        if video_path and os.path.exists(video_path):
            try:
                stat = os.stat(video_path)
                return (
                    "v4-source-video-envelope",
                    os.path.abspath(video_path),
                    int(stat.st_size),
                    int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
                )
            except Exception:
                return ("v4-source-video-envelope", os.path.abspath(video_path), 0, 0)
        return None

    def _timeline_thumbnail_request_signature(self):
        clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []
        if len(clips) > 1:
            signature = []
            for clip in clips:
                path = os.path.abspath(str(clip.get("source", "") or ""))
                try:
                    stat = os.stat(path)
                    identity = (int(stat.st_size), int(getattr(stat, "st_mtime_ns", 0)))
                except OSError:
                    identity = (0, 0)
                signature.append((path, identity, round(float(clip.get("source_start", 0.0)), 3), round(float(clip.get("source_duration", 0.0)), 3)))
            return ("v6-timeline-sequence-thumbnails", tuple(signature))
        clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []
        if len(clips) > 1:
            return (
                "v5-source-sequence-envelope",
                tuple(
                    (
                        os.path.abspath(str(clip.get("source", "") or "")),
                        round(float(clip.get("source_start", 0.0) or 0.0), 3),
                        round(float(clip.get("source_duration", 0.0) or 0.0), 3),
                        round(float(clip.get("speed", 1.0) or 1.0), 3),
                    )
                    for clip in clips
                ),
            )
        canonical = getattr(self, "resolve_canonical_video_path", None)
        video_path = self._normalize_local_file_path(canonical() if callable(canonical) else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else ""))
        duration_s = max(0.0, float(getattr(self.timeline, "duration", 0) or 0) / 1000.0) if hasattr(self, "timeline") else 0.0
        if not video_path or not os.path.exists(video_path) or duration_s <= 0.0:
            return None
        try:
            stat = os.stat(video_path)
            return (
                "v5-timeline-thumbnails",
                os.path.abspath(video_path),
                int(stat.st_size),
                int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))),
                int(round(duration_s)),
            )
        except Exception:
            return ("v5-timeline-thumbnails", os.path.abspath(video_path), 0, 0, int(round(duration_s)))

    def _load_launcher_timeline_visual_cache(self):
        """Return static V1/A1 data prepared by the launcher, if valid."""
        canonical = getattr(self, "resolve_canonical_video_path", None)
        video_path = self._normalize_local_file_path(
            canonical() if callable(canonical) else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        )
        if not video_path or not os.path.exists(video_path):
            return None
        try:
            stat = os.stat(video_path)
            source_abs = os.path.abspath(video_path)
            cache_dir = os.path.join(self.get_workspace_temp_root(create=True), "timeline_visuals")
            digest = hashlib.md5(source_abs.encode("utf-8")).hexdigest()[:12]
            manifest_path = os.path.join(cache_dir, f"{digest}.json")
            candidates = [manifest_path]
            # A packaged build can be launched with a copied video (for
            # example, the same file moved from media/ to Downloads).  The
            # launcher cache is still reusable in that case, but its
            # path-based digest no longer matches.  Fall back to a manifest
            # with the same filename and byte size, while retaining the
            # normal exact path/mtime validation as the first choice.
            if os.path.isdir(cache_dir):
                candidates.extend(
                    path for path in glob.glob(os.path.join(cache_dir, "*.json"))
                    if path != manifest_path
                )
            for candidate in candidates:
                try:
                    with open(candidate, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                except (OSError, ValueError, TypeError):
                    continue
                exact = (
                    data.get("source") == source_abs
                    and int(data.get("size", -1)) == int(stat.st_size)
                    and int(data.get("mtime_ns", -1)) == int(getattr(stat, "st_mtime_ns", 0))
                )
                compatible_copy = (
                    os.path.basename(str(data.get("source", ""))).lower()
                    == os.path.basename(source_abs).lower()
                    and int(data.get("size", -1)) == int(stat.st_size)
                )
                if exact or compatible_copy:
                    return data
            return None
        except (OSError, ValueError, TypeError):
            return None

    def refresh_timeline_waveform(self):
        if not hasattr(self, "timeline"):
            return
        request_signature = self._timeline_waveform_request_signature()
        if not request_signature:
            self._desired_timeline_waveform_request = None
            self._timeline_waveform_cache_key = None
            self._timeline_waveform_samples = []
            self._timeline_waveform_duration_s = 0.0
            self.timeline.set_waveform_data([], 0.0)
            return
        launcher_cache = self._load_launcher_timeline_visual_cache()
        if launcher_cache and launcher_cache.get("waveform"):
            self._desired_timeline_waveform_request = request_signature
            self._timeline_waveform_cache_key = request_signature
            self._timeline_waveform_samples = list(launcher_cache.get("waveform") or [])
            self._timeline_waveform_duration_s = max(0.0, float(launcher_cache.get("duration_s") or 0.0))
            self.timeline.set_waveform_data(
                self._timeline_waveform_samples, self._timeline_waveform_duration_s
            )
            return
        self._desired_timeline_waveform_request = request_signature
        if self._timeline_waveform_cache_key == request_signature:
            self.timeline.set_waveform_data(
                self._timeline_waveform_samples, self._timeline_waveform_duration_s
            )
            return
        worker = self._timeline_waveform_worker
        if worker is not None and worker.isRunning():
            return
        canonical = getattr(self, "resolve_canonical_video_path", None)
        video_path = self._normalize_local_file_path(
            canonical() if callable(canonical) else (self.video_path_edit.text().strip() if hasattr(self, "video_path_edit") else "")
        )
        clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []
        worker = TimelineWaveformWorker(
            request_signature, video_path, "", self._waveform_temp_path(), clips
        )
        worker.setParent(self)
        worker.finished.connect(self._on_timeline_waveform_ready)
        self._timeline_waveform_worker = worker
        worker.start()

    def _on_timeline_waveform_ready(self, request_signature, waveform, duration_s, error):
        worker = self._timeline_waveform_worker
        release_thread_when_stopped(
            worker,
            lambda: setattr(self, "_timeline_waveform_worker", None)
            if getattr(self, "_timeline_waveform_worker", None) is worker
            else None,
        )
        if request_signature != self._desired_timeline_waveform_request:
            self.refresh_timeline_waveform()
            return
        if error:
            print(f"[Timeline] waveform generation failed: {error}")
            self._timeline_waveform_cache_key = request_signature
            self._timeline_waveform_samples = []
            self._timeline_waveform_duration_s = 0.0
        else:
            self._timeline_waveform_cache_key = request_signature
            self._timeline_waveform_samples = list(waveform or [])
            self._timeline_waveform_duration_s = max(0.0, float(duration_s or 0.0))
            print(
                f"[Timeline] waveform generated: samples={len(self._timeline_waveform_samples)} "
                f"duration={self._timeline_waveform_duration_s:.1f}s"
            )
        if hasattr(self, "timeline"):
            self.timeline.set_waveform_data(self._timeline_waveform_samples, self._timeline_waveform_duration_s)

    def schedule_timeline_visual_refresh(self, *, waveform: bool = True, thumbnails: bool = True, delay_ms: int = 40):
        # V1/A1 visuals are tied only to the source media, not to a pipeline
        # stage. They are static cached assets and may be prepared as soon as
        # a video is opened.
        if waveform:
            self._pending_timeline_waveform_refresh = True
        if thumbnails:
            self._pending_timeline_thumbnail_refresh = True
        timer = getattr(self, "_timeline_visual_refresh_timer", None)
        if timer is None:
            self._run_pending_timeline_visual_refresh()
            return
        timer.start(max(0, int(delay_ms)))

    def _run_pending_timeline_visual_refresh(self):
        refresh_waveform = bool(getattr(self, "_pending_timeline_waveform_refresh", False))
        refresh_thumbnails = bool(getattr(self, "_pending_timeline_thumbnail_refresh", False))
        self._pending_timeline_waveform_refresh = False
        self._pending_timeline_thumbnail_refresh = False
        if refresh_waveform:
            self.refresh_timeline_waveform()
        if refresh_thumbnails:
            self.refresh_timeline_video_thumbnails()

    def refresh_timeline_video_thumbnails(self):
        if not hasattr(self, "timeline"):
            return
        request_signature = self._timeline_thumbnail_request_signature()
        if not request_signature:
            self._timeline_video_thumb_cache_key = None
            self._timeline_video_thumbnails = []
            self._desired_timeline_thumbnail_request = None
            self.timeline.set_video_thumbnails([])
            return
        launcher_cache = self._load_launcher_timeline_visual_cache()
        if launcher_cache and launcher_cache.get("thumbnails"):
            pixmaps = []
            for timestamp_s, output_path in launcher_cache.get("thumbnails"):
                pixmap = QPixmap(str(output_path or ""))
                if not pixmap.isNull():
                    pixmaps.append((float(timestamp_s), pixmap))
            if pixmaps:
                self._desired_timeline_thumbnail_request = request_signature
                self._timeline_video_thumb_cache_key = request_signature
                self._timeline_video_thumbnails = pixmaps
                self.timeline.set_video_thumbnails(pixmaps)
                return
        self._desired_timeline_thumbnail_request = request_signature
        if self._timeline_video_thumb_cache_key == request_signature:
            self.timeline.set_video_thumbnails(self._timeline_video_thumbnails)
            return
        worker = self._timeline_thumbnail_worker
        if worker is not None and worker.isRunning():
            return
        canonical = getattr(self, "resolve_canonical_video_path", None)
        video_path = self._normalize_local_file_path(canonical() if callable(canonical) else self.video_path_edit.text().strip())
        duration_s = max(0.0, float(self.timeline.duration or 0) / 1000.0)
        thumb_dir = os.path.join(self.get_workspace_temp_root(create=True), "timeline_thumbnails")
        clips = self.get_timeline_video_clips(existing_only=True) if hasattr(self, "get_timeline_video_clips") else []
        worker = TimelineThumbnailWorker(request_signature, video_path, duration_s, thumb_dir, clips)
        worker.setParent(self)
        worker.finished.connect(self._on_timeline_video_thumbnails_ready)
        self._timeline_thumbnail_worker = worker
        worker.start()

    def _on_timeline_video_thumbnails_ready(self, request_signature, thumbnails, error):
        worker = self._timeline_thumbnail_worker
        release_thread_when_stopped(
            worker,
            lambda: setattr(self, "_timeline_thumbnail_worker", None)
            if getattr(self, "_timeline_thumbnail_worker", None) is worker
            else None,
        )
        if request_signature != self._desired_timeline_thumbnail_request:
            self.refresh_timeline_video_thumbnails()
            return
        if error:
            print(f"[Timeline] thumbnail generation failed: {error}")
            self._timeline_video_thumb_cache_key = request_signature
            self._timeline_video_thumbnails = []
        else:
            pixmaps = []
            for timestamp_s, output_path in list(thumbnails or []):
                pixmap = QPixmap(str(output_path or ""))
                if not pixmap.isNull():
                    pixmaps.append((float(timestamp_s), pixmap))
            self._timeline_video_thumb_cache_key = request_signature
            self._timeline_video_thumbnails = pixmaps
        if hasattr(self, "timeline"):
            self.timeline.set_video_thumbnails(self._timeline_video_thumbnails)
