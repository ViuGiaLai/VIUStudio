from __future__ import annotations

import os
import hashlib
import json
import re
import subprocess
import shutil
import threading
import time
import traceback
import wave
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QMainWindow, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSplitter, QVBoxLayout, QWidget, QMenu, QSlider, QDoubleSpinBox,
    QInputDialog,
)

from app.services.movie_review_service import (
    GeminiMovieReviewClient,
    MovieReviewProject,
    MovieReviewService,
)
from app.services.gemini_key_pool import GeminiKeyPool
from app.services.music_library_service import MusicLibraryService
from runtime_paths import subprocess_hidden_kwargs
from ui.helpers.srt_helpers import format_segments_to_srt, parse_srt_to_segments


DEFAULT_REVIEW_VOICE = "banmai"
LEGACY_REVIEW_VOICE = "edge:vi-VN-HoaiMyNeural"


class _TaskWorker(QObject):
    """Runs one long task off the UI thread.

    Tasks receive ``report(percent, message)`` so the editor can show real
    progress, and ``is_cancelled()`` so a cancel request stops between safe
    steps instead of freezing the window until the whole job finishes.
    """

    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)
    progress = Signal(int, str)

    def __init__(self, task: Callable[[Callable, Callable], object], cancel_event: threading.Event | None = None):
        super().__init__()
        self.task = task
        self.cancel_event = cancel_event or threading.Event()

    def _report(self, percent, message: str = ""):
        value = int(percent)
        if value >= 0:
            value = max(0, min(100, value))
        self.progress.emit(value, str(message))

    def _is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def run(self):
        try:
            result = self.task(self._report, self._is_cancelled)
        except InterruptedError as exc:
            self.cancelled.emit(str(exc))
            return
        except Exception as exc:  # pragma: no cover - exercised through UI
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
            return
        self.finished.emit(result)


class _UiTaskDispatcher(QObject):
    """Queues worker callbacks onto the GUI thread before touching widgets."""

    dispatch = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dispatch.connect(self._run, Qt.QueuedConnection)

    def _run(self, callback):
        callback()


class _ExportWarningDialog(QDialog):
    """Lists the Scenes that still have QA findings before an export starts.

    Every row carries its Scene id so the editor can jump straight to the scene
    instead of hunting for it in the list. ``allow_export`` is False while
    blocking errors exist (or when simply running a QA check).
    """

    def __init__(self, issues, parent=None, *, allow_export: bool = False):
        super().__init__(parent)
        self.jump_scene_id = ""
        errors = [item for item in issues if item.get("severity") == "error"]
        self.setWindowTitle("QA trước Export")
        self.resize(780, 470)

        layout = QVBoxLayout(self)
        summary = QLabel(
            f"{len(errors)} lỗi chặn Export · {len(issues) - len(errors)} cảnh báo"
            if allow_export else
            f"{len(errors)} lỗi chặn Export · {len(issues) - len(errors)} cảnh báo cần xem lại"
        )
        layout.addWidget(summary)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        for item in issues:
            marker = "⛔" if item.get("severity") == "error" else "⚠"
            row = QListWidgetItem(f"{marker} {item['scene_id']} — {item['message']}")
            row.setData(Qt.UserRole, item["scene_id"])
            self.list_widget.addItem(row)
        layout.addWidget(self.list_widget, 1)

        buttons = QHBoxLayout()
        self.jump_btn = QPushButton("Đi tới Scene")
        self.jump_btn.setEnabled(self.list_widget.count() > 0)
        self.jump_btn.clicked.connect(self._jump)
        buttons.addWidget(self.jump_btn)
        buttons.addStretch(1)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(close_btn)
        self.export_btn = None
        if allow_export:
            self.export_btn = QPushButton("Vẫn Export")
            self.export_btn.setProperty("accent", True)
            self.export_btn.clicked.connect(self.accept)
            buttons.addWidget(self.export_btn)
        layout.addLayout(buttons)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._jump())

    def _jump(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.jump_scene_id = str(item.data(Qt.UserRole) or "")
        self.done(QDialog.Accepted)


class _GeminiKeyPoolDialog(QDialog):
    """Local ordered key editor; list order is automatic failover order."""

    def __init__(self, pool: GeminiKeyPool, parent=None):
        super().__init__(parent)
        self.pool = pool
        self.setWindowTitle("Quản lý Gemini Keys")
        self.resize(720, 500)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Gemini thử key theo thứ tự từ trên xuống. Khi key bị quota/401/403/429, "
            "Movie Review tự chuyển sang key kế tiếp."
        ))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._select)
        layout.addWidget(self.list_widget, 1)

        form = QVBoxLayout()
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Tên dễ nhớ, ví dụ: Key 1")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Dán Gemini API key")
        self.show_key = QCheckBox("Hiện key")
        self.show_key.toggled.connect(
            lambda checked: self.key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        )
        self.enabled_check = QCheckBox("Đang bật")
        self.enabled_check.setChecked(True)
        form.addWidget(QLabel("Tên key"))
        form.addWidget(self.label_edit)
        form.addWidget(QLabel("API key"))
        form.addWidget(self.key_edit)
        form.addWidget(self.show_key)
        form.addWidget(self.enabled_check)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        new_btn = QPushButton("Key mới")
        new_btn.clicked.connect(self._new)
        save_btn = QPushButton("Thêm / Lưu sửa")
        save_btn.setProperty("accent", True)
        save_btn.clicked.connect(self._save_entry)
        delete_btn = QPushButton("Xóa key")
        delete_btn.clicked.connect(self._delete)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)
        for button in (new_btn, save_btn, delete_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        self._entry_ids: list[str] = []
        self._reload()

    def _reload(self):
        current_id = self._entry_ids[self.list_widget.currentRow()] if 0 <= self.list_widget.currentRow() < len(self._entry_ids) else ""
        self.list_widget.clear()
        entries = self.pool.load()
        self._entry_ids = [item.id for item in entries]
        for index, item in enumerate(entries, start=1):
            status = "Bật" if item.enabled else "Tắt"
            error = f" · lỗi gần nhất: {item.last_error[:90]}" if item.last_error else ""
            self.list_widget.addItem(
                f"{index}. {item.label} · {self.pool.mask(item.api_key)} · {status} · lỗi quota: {item.fail_count}{error}"
            )
        if current_id in self._entry_ids:
            self.list_widget.setCurrentRow(self._entry_ids.index(current_id))

    def _select(self, row: int):
        entries = self.pool.load()
        if not (0 <= row < len(entries)):
            return
        item = entries[row]
        self.label_edit.setText(item.label)
        self.key_edit.setText(item.api_key)
        self.enabled_check.setChecked(item.enabled)

    def _new(self):
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)
        self.label_edit.clear()
        self.key_edit.clear()
        self.enabled_check.setChecked(True)
        self.label_edit.setFocus()

    def _save_entry(self):
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Thiếu key", "Hãy nhập Gemini API key.")
            return
        row = self.list_widget.currentRow()
        entry_id = self._entry_ids[row] if 0 <= row < len(self._entry_ids) else ""
        saved = self.pool.upsert(
            self.label_edit.text(), key, entry_id=entry_id, enabled=self.enabled_check.isChecked()
        )
        self._reload()
        if saved.id in self._entry_ids:
            self.list_widget.setCurrentRow(self._entry_ids.index(saved.id))

    def _delete(self):
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self._entry_ids)):
            return
        if QMessageBox.question(self, "Xóa Gemini key?", "Xóa key đang chọn khỏi danh sách?") != QMessageBox.Yes:
            return
        self.pool.delete(self._entry_ids[row])
        self._new()
        self._reload()


class _ProjectLibraryDialog(QDialog):
    """Small project browser for the Movie Review workspace."""

    def __init__(self, roots: list[str], parent=None):
        super().__init__(parent)
        self.selected_path = ""
        self.setWindowTitle("Movie Review Projects")
        self.resize(720, 470)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("PROJECTS"))
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._open())
        layout.addWidget(self.list_widget, 1)
        buttons = QHBoxLayout()
        new_btn = QPushButton("+ Project mới")
        new_btn.clicked.connect(self._new_project)
        self.open_btn = QPushButton("Mở")
        self.open_btn.setEnabled(False)
        self.open_btn.clicked.connect(self._open)
        browse_btn = QPushButton("Mở file project…")
        browse_btn.clicked.connect(self._browse)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.reject)
        buttons.addWidget(new_btn)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(browse_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        self.list_widget.currentRowChanged.connect(lambda row: self.open_btn.setEnabled(row >= 0))
        self._populate(roots)

    def _populate(self, roots: list[str]) -> None:
        paths: list[str] = []
        for root in roots:
            if os.path.isdir(root):
                paths.extend(str(path) for path in Path(root).glob("**/movie_review.json"))
        for path in sorted(set(paths), key=lambda item: os.path.getmtime(item), reverse=True):
            try:
                payload = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            folder = os.path.basename(os.path.dirname(path))
            video = os.path.basename(str(payload.get("video_path", "") or "")) or "chưa có video"
            source_segments = payload.get("source_segments", []) or []
            scenes = payload.get("scenes", []) or []
            reviewed = sum(1 for scene in scenes if str(scene.get("review_text", "") or "").strip())
            modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
            item = QListWidgetItem(
                f"{folder}\n  Video: {video} · SRT: {len(source_segments)} dòng · "
                f"{len(scenes)} Scene · {reviewed} đã Review · Cập nhật: {modified}"
            )
            item.setData(Qt.UserRole, os.path.abspath(path))
            self.list_widget.addItem(item)

    def _open(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        self.selected_path = str(item.data(Qt.UserRole) or "")
        self.accept()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Mở Movie Review project", "", "Movie Review (*.json);;All files (*)"
        )
        if path:
            self.selected_path = os.path.abspath(path)
            self.accept()

    def _new_project(self) -> None:
        parent = self.parent()
        self.reject()
        if parent is not None and hasattr(parent, "_new_project"):
            parent._new_project()


class MovieReviewEditorWindow(QMainWindow):
    """Independent Movie Review workspace launched before the normal editor."""

    def __init__(self, workspace_root: str, parent=None):
        super().__init__(parent)
        self.workspace_root = os.path.abspath(workspace_root)
        self.settings = QSettings("VIUStudio", "MovieReviewEditor")
        self.key_pool_path = os.path.join(self.workspace_root, "MovieReviewProjects", "gemini_keys.json")
        os.environ["GEMINI_KEY_POOL_FILE"] = self.key_pool_path
        key_pool = GeminiKeyPool(self.key_pool_path)
        existing_key = str(os.getenv("GOOGLE_AI_STUDIO_API_KEY", "") or "").strip()
        if existing_key and not key_pool.load():
            key_pool.upsert("Key 1 (đã cấu hình)", existing_key)
        self._project_path = ""
        self.service = MovieReviewService()
        self.music_service = MusicLibraryService()
        self.ai = GeminiMovieReviewClient()
        self.project = MovieReviewProject()
        self._threads: list[QThread] = []
        # Qt only keeps a weak reference to a bound-method receiver, so this
        # list is what actually keeps each worker alive until its thread ends.
        # Without it the worker is garbage collected before it starts and the
        # task silently never runs (and the window stays disabled forever).
        self._workers: list[_TaskWorker] = []
        self._ui_task_dispatcher = _UiTaskDispatcher(self)
        self._selected_index = -1
        # Last QA result, keyed by Scene id, so the Scene list, the QA bar and
        # the editor panel all read one validation pass instead of three.
        self._issues_by_scene: dict[str, list[dict]] = {}
        self._busy = False
        self._cancel_event: threading.Event | None = None
        self._pending_seek_ms = 0
        self._video_warning_shown = False
        # Debounce rapid text edits so each keystroke doesn't re-plan entire project
        self._review_debounce = None
        self._length_guard_attempts: dict[str, int] = {}
        self.setObjectName("movieReviewEditor")
        self.setWindowTitle("Movie Review Editor")
        self.resize(1450, 880)
        self.setMinimumSize(1050, 680)
        self._build_ui()
        self._reload_voices()
        # Always start on a clean project: reopening the previous one without
        # asking was the reason a fresh launch looked like "the old project".
        self._start_new_project(announce=False)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("movieReviewCentral")
        self.setCentralWidget(central)
        self.setStyleSheet("""
            QMainWindow, QWidget#movieReviewCentral { background: #0b1118; color: #cdd9e5; }
            QLabel { color: #cdd9e5; }
            QFrame, QPlainTextEdit, QListWidget, QComboBox { background: #0f1724; border: 1px solid #24344a; border-radius: 7px; color: #dbe8f5; padding: 4px 6px; }
            QProgressBar { background: #0f1724; border: 1px solid #24344a; border-radius: 7px; color: #dbe8f5; text-align: center; }
            QProgressBar::chunk { background: #0ea574; border-radius: 6px; }
            QPushButton { background: #172235; border: 1px solid #314767; border-radius: 7px; padding: 7px 11px; color: #e5edf7; }
            QPushButton:hover { border-color: #6366f1; background: #202d43; }
            QPushButton[accent="true"] { background: #0ea574; border-color: #34d399; color: white; font-weight: 700; }
        """)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("MOVIE REVIEW EDITOR")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #eaf4ff;")
        title_row.addWidget(title)
        title_row.addWidget(QLabel("Mode"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Recap", "recap")
        self.mode_combo.addItem("Review", "review")
        self.mode_combo.addItem("Commentary", "commentary")
        self.mode_combo.setToolTip("Recap kể diễn biến; Review thêm đánh giá; Commentary thiên về phân tích.")
        title_row.addWidget(self.mode_combo)
        title_row.addStretch(1)
        self.new_project_btn = QPushButton("Project mới")
        self.new_project_btn.setToolTip("Bắt đầu project Movie Review trống.")
        self.open_project_btn = QPushButton("Mở project")
        self.project_folder_btn = QPushButton("Mở thư mục")
        self.project_folder_btn.setToolTip(
            "Mở thư mục project (chứa movie_review.json, source.srt, tts, export)."
        )
        title_row.addWidget(self.new_project_btn)
        title_row.addWidget(self.open_project_btn)
        title_row.addWidget(self.project_folder_btn)
        self.gemini_keys_btn = QPushButton("Gemini Keys")
        self.gemini_keys_btn.setToolTip("Thêm/sửa/xóa/xem key và cấu hình tự chuyển key khi hết quota.")
        title_row.addWidget(self.gemini_keys_btn)
        self.glossary_btn = QPushButton("Glossary")
        self.glossary_btn.setToolTip("Duyệt tên nhân vật, địa danh, vật phẩm và cách đọc Piper.")
        title_row.addWidget(self.glossary_btn)
        self.music_library_btn = QPushButton("Music Library")
        self.music_library_btn.setToolTip("Phân tích/cache thư viện nhạc và tự match mood cho từng Scene.")
        title_row.addWidget(self.music_library_btn)
        root.addLayout(title_row)

        writer_row = QHBoxLayout()
        self.video_btn = QPushButton("Upload Video")
        self.srt_btn = QPushButton("Upload SRT")
        self.review_srt_btn = QPushButton("Import Review SRT")
        self.external_export_btn = QPushButton("1. Xuất Brief cho AI ngoài")
        self.external_export_btn.setToolTip(
            "Tạo một file duy nhất chứa prompt, SRT, Scene Context, Glossary và mẫu JSON; gửi file đó cho ChatGPT/DeepSeek."
        )
        self.external_import_btn = QPushButton("2. Nhập JSON Review")
        self.external_import_btn.setToolTip(
            "Nhập file JSON AI bên ngoài trả về; hệ thống kiểm tra cue/timestamp rồi dùng Piper và bản dựng hiện tại."
        )
        self.build_btn = QPushButton("Viết bằng Gemini")
        self.build_btn.setToolTip("Dùng Gemini trong ứng dụng để tạo cấu trúc và lời review.")
        self.build_btn.setProperty("accent", True)
        writer_row.addWidget(self.video_btn)
        writer_row.addWidget(self.srt_btn)
        writer_row.addWidget(self.review_srt_btn)
        writer_row.addStretch(1)
        writer_row.addWidget(QLabel("Nguồn lời review:"))
        writer_row.addWidget(self.external_export_btn)
        writer_row.addWidget(self.external_import_btn)
        writer_row.addWidget(self.build_btn)
        root.addLayout(writer_row)

        # Project state gets its own row: with the extra project buttons the
        # single title row no longer has room for a full path summary.
        self.video_path_label = QLabel("Chưa chọn video")
        self.video_path_label.setStyleSheet("color: #7a8fa8;")
        root.addWidget(self.video_path_label)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        left = QFrame()
        left.setMinimumWidth(210)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Narrative Segments / Scenes"))
        self.scene_list = QListWidget()
        left_layout.addWidget(self.scene_list, 1)
        self.analyze_all_btn = QPushButton("Viết lại theo Story Arc")
        self.analyze_all_btn.setToolTip(
            "Gemini đọc nhiều Scene liên tiếp, viết mạch kể hoàn chỉnh rồi mới phân bổ lại timestamp. "
            "Thanh trạng thái hiện từng Arc; nếu thiếu Scene hoặc lời kể quá dài sẽ tự sửa ngay trong lúc chạy."
        )
        left_layout.addWidget(self.analyze_all_btn)
        self.approve_all_btn = QPushButton("Approve tất cả")
        self.approve_all_btn.setToolTip(
            "Đánh dấu đã duyệt cho mọi Scene đã có lời review; Scene chưa có review sẽ bị bỏ qua."
        )
        left_layout.addWidget(self.approve_all_btn)
        splitter.addWidget(left)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(300)
        self.video_widget.setStyleSheet("background: #05080d; border: 1px solid #253a54;")
        center_layout.addWidget(self.video_widget, 3)
        play_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Preview Original")
        self.preview_edited_btn = QPushButton("Preview Edited")
        self.preview_overlay_btn = QPushButton("Preview + Overlay/Subtitle")
        self.play_external_btn = QPushButton("Mở bằng trình phát ngoài")
        self.play_external_btn.setToolTip(
            "Mở video bằng ứng dụng mặc định của Windows tại đúng vị trí Scene."
        )
        self.time_label = QLabel("00:00.000 → 00:00.000")
        play_row.addWidget(self.play_btn)
        play_row.addWidget(self.preview_edited_btn)
        play_row.addWidget(self.preview_overlay_btn)
        play_row.addWidget(self.play_external_btn)
        play_row.addWidget(self.time_label, 1)
        center_layout.addLayout(play_row)
        self.video_hint_label = QLabel("")
        self.video_hint_label.setWordWrap(True)
        self.video_hint_label.setStyleSheet("color: #fbbf24;")
        center_layout.addWidget(self.video_hint_label)
        center_layout.addWidget(QLabel("Phim gốc · chọn một đoạn bên trái để xem"))
        self.keyframe_label = QLabel("Video preview · kiểm tra timestamp SRT")
        self.keyframe_label.setAlignment(Qt.AlignCenter)
        self.keyframe_label.setMinimumHeight(180)
        self.keyframe_label.setStyleSheet("background: #080d14; border: 1px solid #253a54; color: #7a8fa8;")
        center_layout.addWidget(self.keyframe_label, 2)
        frame_row = QHBoxLayout()
        self.keyframe_heading = QLabel("Khung hình tham khảo")
        frame_row.addWidget(self.keyframe_heading)
        frame_row.addStretch(1)
        self.keyframe_btn = QPushButton("Lấy keyframe")
        self.keyframe_btn.setToolTip(
            "Trích vài khung hình để người dựng kiểm tra visual; AI viết lời chỉ nhận SRT/Story Context/Glossary."
        )
        frame_row.addWidget(self.keyframe_btn)
        center_layout.addLayout(frame_row)
        self.keyframe_strip = QListWidget()
        self.keyframe_strip.setMaximumHeight(74)
        center_layout.addWidget(self.keyframe_strip)
        splitter.addWidget(center)

        right = QWidget()
        right.setMinimumWidth(340)
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("SRT GỐC (chỉ đọc)"))
        self.source_text = QPlainTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setMaximumHeight(190)
        right_layout.addWidget(self.source_text)
        self.story_beat_label = QLabel("STORY BEAT: —")
        self.story_beat_label.setWordWrap(True)
        self.story_beat_label.setStyleSheet("color: #8fb7d9;")
        right_layout.addWidget(self.story_beat_label)
        review_header = QHBoxLayout()
        review_header.addWidget(QLabel("Lời review · có thể sửa trực tiếp"))
        review_header.addStretch(1)
        self.copy_review_btn = QPushButton("Copy")
        self.copy_review_btn.setToolTip("Sao chép lời review của Scene đang chọn.")
        review_header.addWidget(self.copy_review_btn)
        right_layout.addLayout(review_header)
        self.review_text = QPlainTextEdit()
        self.review_text.setPlaceholderText(
            "Lời từ Gemini hoặc bản JSON nhập ngoài sẽ hiện ở đây; có thể sửa trực tiếp trước khi tạo Piper."
        )
        right_layout.addWidget(self.review_text, 1)
        stats = QHBoxLayout()
        self.tts_label = QLabel("TTS: 0.0s")
        self.confidence_label = QLabel("Context confidence: —")
        self.link_label = QLabel("SRT links: —")
        self.music_label = QLabel("Music: —")
        stats.addWidget(self.tts_label)
        stats.addWidget(self.confidence_label)
        stats.addWidget(self.link_label, 1)
        stats.addWidget(self.music_label, 1)
        right_layout.addLayout(stats)
        pacing_row = QHBoxLayout()
        pacing_row.addWidget(QLabel("Tone"))
        self.tone_combo = QComboBox()
        for value in ("NEUTRAL", "PLAYFUL", "TENSE", "SAD", "EPIC", "TWIST"):
            self.tone_combo.addItem(value, value)
        pacing_row.addWidget(self.tone_combo)
        pacing_row.addWidget(QLabel("Tốc độ"))
        self.narration_speed = QDoubleSpinBox()
        self.narration_speed.setRange(0.92, 1.08)
        self.narration_speed.setSingleStep(0.01)
        self.narration_speed.setDecimals(2)
        self.narration_speed.setSuffix("x")
        pacing_row.addWidget(self.narration_speed)
        right_layout.addLayout(pacing_row)
        voice_row = QHBoxLayout()
        voice_row.addWidget(QLabel("Giọng TTS"))
        self.voice_combo = QComboBox()
        self.voice_combo.setToolTip("Giọng dùng cho TTS Review; giọng Việt được xếp trước.")
        voice_row.addWidget(self.voice_combo, 1)
        self.voice_manage_btn = QPushButton("Quản lý giọng")
        self.voice_manage_btn.setToolTip("Mở Resource Manager để tải hoặc cài thêm giọng.")
        voice_row.addWidget(self.voice_manage_btn)
        right_layout.addLayout(voice_row)
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #fbbf24;")
        right_layout.addWidget(self.warning_label)
        action_row = QHBoxLayout()
        self.rewrite_btn = QPushButton("Rewrite")
        self.expand_btn = QPushButton("Expand Context")
        self.freeze_btn = QPushButton("Freeze")
        self.approve_btn = QPushButton("Approve")
        for button in (self.rewrite_btn, self.expand_btn, self.freeze_btn, self.approve_btn):
            action_row.addWidget(button)
        right_layout.addLayout(action_row)
        splitter.addWidget(right)
        splitter.setSizes([300, 680, 470])

        footer = QHBoxLayout()
        self.status_label = QLabel("Sẵn sàng")
        footer.addWidget(self.status_label, 1)
        self.qa_label = QLabel("QA: chưa có Scene")
        self.qa_label.setStyleSheet("color: #93a4b8;")
        footer.addWidget(self.qa_label)
        self.qa_btn = QPushButton("Scene còn cảnh báo")
        self.qa_btn.setToolTip("Mở danh sách Scene còn lỗi/cảnh báo và nhảy tới từng Scene.")
        self.qa_btn.setEnabled(False)
        footer.addWidget(self.qa_btn)
        self.validate_btn = QPushButton("Kiểm tra trước Export")
        self.sync_btn = QPushButton("Tạo / cập nhật Review Track")
        self.tts_btn = QPushButton("Tạo TTS Review")
        self.export_srt_btn = QPushButton("Xuất Review SRT")
        self.export_video_btn = QPushButton("Export Video")
        self.save_btn = QPushButton("Lưu")
        footer.addWidget(self.validate_btn)
        footer.addWidget(self.sync_btn)
        footer.addWidget(self.tts_btn)
        self.edit_plan_btn = QPushButton("Lập bản dựng sau TTS")
        self.edit_plan_btn.clicked.connect(self._build_measured_edit_plan)
        footer.addWidget(self.edit_plan_btn)
        footer.addWidget(self.export_srt_btn)
        footer.addWidget(self.export_video_btn)
        footer.addWidget(self.save_btn)
        root.addLayout(footer)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setMaximumWidth(320)
        self.progress_bar.hide()
        progress_row.addWidget(self.progress_bar)
        self.cancel_btn = QPushButton("Huỷ tác vụ")
        self.cancel_btn.clicked.connect(self._cancel_task)
        self.cancel_btn.hide()
        progress_row.addWidget(self.cancel_btn)
        progress_row.addStretch(1)
        root.addLayout(progress_row)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.audio_output.setVolume(0.8)
        self.player.positionChanged.connect(self._stop_at_scene_end)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_player_error)

        self.new_project_btn.clicked.connect(self._new_project)
        self.open_project_btn.clicked.connect(self._open_project)
        self.project_folder_btn.clicked.connect(self._open_project_folder)
        self.gemini_keys_btn.clicked.connect(self._manage_gemini_keys)
        self.glossary_btn.clicked.connect(self._edit_glossary)
        self.music_library_btn.clicked.connect(self._analyze_music_library)
        self.video_btn.clicked.connect(self._choose_video)
        self.srt_btn.clicked.connect(self._choose_srt)
        self.review_srt_btn.clicked.connect(self._choose_review_srt)
        self.external_export_btn.clicked.connect(self._export_external_review_brief)
        self.external_import_btn.clicked.connect(self._import_external_review)
        self.build_btn.clicked.connect(self._write_review_simple)
        self.scene_list.currentRowChanged.connect(self._select_scene)
        self.keyframe_strip.currentRowChanged.connect(self._select_keyframe)
        self.keyframe_btn.clicked.connect(self._extract_scene_keyframes)
        self.copy_review_btn.clicked.connect(self._copy_review_text)
        self.play_btn.clicked.connect(self._play_scene)
        self.preview_edited_btn.clicked.connect(self._preview_review)
        self.preview_overlay_btn.clicked.connect(self._preview_review)
        self.review_text.textChanged.connect(self._review_text_changed)
        self.rewrite_btn.clicked.connect(self._rewrite_scene)
        self.expand_btn.clicked.connect(self._expand_context)
        self.freeze_btn.clicked.connect(self._toggle_freeze)
        self.approve_btn.clicked.connect(self._approve_scene)
        self.analyze_all_btn.clicked.connect(self._analyze_all)
        self.validate_btn.clicked.connect(self._validate)
        self.sync_btn.clicked.connect(self._sync_timeline)
        self.tts_btn.clicked.connect(self._generate_tts)
        self.export_srt_btn.clicked.connect(self._export_review_srt)
        self.export_video_btn.clicked.connect(self._prepare_and_export)
        self.save_btn.clicked.connect(self._save)
        self.qa_btn.clicked.connect(self._show_issue_list)
        self.approve_all_btn.clicked.connect(self._approve_all)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        self.tone_combo.currentIndexChanged.connect(self._on_narration_settings_changed)
        self.narration_speed.valueChanged.connect(self._on_narration_settings_changed)
        self.voice_manage_btn.clicked.connect(self._open_voice_manager)
        self.play_external_btn.clicked.connect(self._open_video_externally)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        # Debounce timer for review text edits — waits 400ms after user stops typing
        self._review_debounce = QTimer(self)
        self._review_debounce.setSingleShot(True)
        self._review_debounce.timeout.connect(self._commit_review_text_edit)
        self._draft_playing = False
        self.voice_player = QMediaPlayer(self)
        self.voice_output = QAudioOutput(self)
        self.voice_player.setAudioOutput(self.voice_output)
        self.approve_all_btn.setText("Approve tất cả")
        self.approve_all_btn.show()
        controls = QHBoxLayout()
        self.quick_buttons = []
        for label, callback in (("Tạo giọng", self._generate_tts),
                                ("▶ Nghe giọng đoạn này", self._listen_voice),
                                ("■ Dừng", self._stop_review_preview),
                                ("Xem bản dựng", self._preview_review),
                                ("Âm lượng · Phụ đề · Logo · Chữ", self._edit_presentation)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
            self.quick_buttons.append(button)
        root.insertLayout(3, controls)
        self.review_seek = QSlider(Qt.Horizontal)
        self.review_seek.setToolTip("Kéo để xem vị trí khác trong phim hoặc bản dựng")
        self.player.durationChanged.connect(lambda duration: self.review_seek.setRange(0, int(duration)))
        self.player.positionChanged.connect(lambda position: self.review_seek.setValue(int(position))
                                            if not self.review_seek.isSliderDown() else None)
        self.review_seek.sliderMoved.connect(self.player.setPosition)
        root.insertWidget(4, self.review_seek)
        self.export_video_btn.setText("Xuất video")

    def _edit_presentation(self):
        if self._busy:
            return
        from ui.views.review_presentation import ReviewPresentationDialog
        dialog = ReviewPresentationDialog(self.project.presentation, self.project.export_config, self)
        if dialog.exec() == QDialog.Accepted:
            self.project.presentation, self.project.export_config = dialog.values()
            self._save(silent=True)
            self.status_label.setText("Đã lưu chỉnh sửa. Bấm Xem bản dựng để kiểm tra trước khi xuất.")

    def _listen_voice(self):
        if self._busy or not (0 <= self._selected_index < len(self.project.scenes)):
            return
        scene = self.project.scenes[self._selected_index]
        if not scene.tts_rendered or not os.path.isfile(scene.tts_audio_path):
            self._generate_tts(on_complete=self._listen_voice)
            return
        self.player.pause()
        self.voice_output.setVolume(min(1.0, float(self.project.presentation.get("voice_gain", 100)) / 100))
        self.voice_player.setSource(QUrl.fromLocalFile(scene.tts_audio_path))
        self.voice_player.play()
        self.status_label.setText(f"Đang nghe giọng {scene.scene_id}; chưa xuất video.")

    def _stop_review_preview(self):
        self.player.pause()
        self.voice_player.stop()

    def _preview_review(self):
        if self._busy or not self.project.scenes:
            return
        if any(not s.tts_rendered or not s.narration_timings for s in self.project.scenes):
            self._generate_tts(on_complete=self._preview_review)
        elif any(not s.has_ai_edit_plan for s in self.project.scenes):
            self._build_measured_edit_plan(on_complete=self._preview_review)
        else:
            self._export_video(preview=True)

    def _simplify_workspace(self, title_row, root):
        """Keep the main workflow visible; retain specialist actions in a menu."""
        self.video_btn.setText("1. Chọn phim")
        self.srt_btn.setText("Chọn phụ đề")
        self.build_btn.setText("2. Viết lời review")
        self.export_video_btn.setText("3. Tạo giọng & xuất video")
        self.export_video_btn.setProperty("accent", True)
        self.rewrite_btn.setText("Viết lại đoạn này")
        self.approve_btn.setText("Đã duyệt")
        self.play_btn.setText("▶ Xem đoạn phim")
        self.review_text.setPlaceholderText("Lời review sẽ xuất hiện ở đây. Bạn có thể sửa trực tiếp rồi bấm Tạo giọng & xuất video.")
        self.workflow_hint = QLabel("Chọn phim + phụ đề → Viết lời review → Đọc và sửa lời → Tạo giọng & xuất video")
        self.workflow_hint.setWordWrap(True)
        root.insertWidget(1, self.workflow_hint)
        more = QPushButton("Tùy chọn ▾")
        menu = QMenu(more)
        self.glossary_btn = QPushButton("Glossary")
        self.glossary_btn.clicked.connect(self._edit_glossary)
        for label, button in (
            ("Dự án mới", self.new_project_btn), ("Mở dự án", self.open_project_btn),
            ("Mở thư mục dự án", self.project_folder_btn), ("Quản lý API key", self.gemini_keys_btn),
            ("Glossary nhân vật & thuật ngữ", self.glossary_btn),
            ("Chọn nhạc nền", self.music_library_btn), ("Nhập lời review từ SRT", self.review_srt_btn),
            ("Viết lại toàn bộ theo Story Arc", self.analyze_all_btn),
            ("Duyệt tất cả lời review", self.approve_all_btn),
            ("Xem bằng trình phát ngoài", self.play_external_btn),
            ("Lấy khung hình", self.keyframe_btn), ("Mở rộng ngữ cảnh", self.expand_btn),
            ("Giữ hình lâu hơn", self.freeze_btn), ("Cài thêm giọng", self.voice_manage_btn),
            ("Kiểm tra bản dựng", self.validate_btn), ("Đồng bộ timeline", self.sync_btn),
            ("Chỉ tạo giọng", self.tts_btn), ("Chỉ lập bản dựng", self.edit_plan_btn),
            ("Xuất phụ đề review", self.export_srt_btn),
        ):
            button.hide()
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, target=button: target.click())
        more.setMenu(menu)
        title_row.addWidget(more)
        details = (self.keyframe_label, self.keyframe_strip, self.keyframe_heading, self.story_beat_label,
                   self.confidence_label, self.link_label, self.music_label)
        detail_action = menu.addAction("Hiện thông tin chi tiết")
        detail_action.setCheckable(True)
        detail_action.toggled.connect(lambda visible: [widget.setVisible(visible) for widget in details])
        for widget in (self.keyframe_label, self.keyframe_strip, self.keyframe_heading, self.story_beat_label,
                       self.confidence_label, self.link_label, self.music_label):
            widget.hide()
        self.source_text.setMaximumHeight(100)
        self.status_label.setWordWrap(True)

    def _prepare_and_export(self):
        from app.services.review_narration import narration_signature
        if self._busy:
            return
        if not self.project.scenes or any(not s.review_text.strip() for s in self.project.scenes):
            QMessageBox.information(self, "Chưa có lời review", "Chọn phim và phụ đề, sau đó bấm Viết lời review.")
            return
        if any(not s.tts_rendered or not s.narration_timings or not os.path.isfile(s.tts_audio_path)
               or s.narration_signature != narration_signature(
                   self.service.normalize_narration_plan(s, s.narration_plan), s.voice_speed)
               for s in self.project.scenes):
            self._generate_tts(on_complete=self._prepare_and_export)
        elif any(not s.has_ai_edit_plan for s in self.project.scenes):
            self._build_measured_edit_plan(on_complete=self._prepare_and_export)
        else:
            self._export_video()

    def _write_review_simple(self):
        """One context request per story arc; no video encoding in the fast path."""
        import copy
        if self._busy:
            return
        if not self.project.video_path or not self.project.source_segments:
            QMessageBox.information(self, "Chọn dữ liệu", "Hãy chọn phim và file phụ đề SRT trước.")
            return
        if self.project.writer_source == "external" and self.project.scenes:
            answer = QMessageBox.question(
                self, "Thay bản review ngoài?",
                "Project đang dùng bản review nhập từ AI bên ngoài. Viết bằng Gemini sẽ thay toàn bộ lời hiện tại. Tiếp tục?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        if not self.project.story_contexts:
            self._build_scenes(continue_to_review=True)
            return
        if self.project.glossary and any(item.get("status") != "approved" for item in self.project.glossary):
            from ui.views.review_glossary import ReviewGlossaryDialog
            dialog = ReviewGlossaryDialog(self.project.glossary, self)
            if dialog.exec() != QDialog.Accepted:
                self.status_label.setText("Cần duyệt Glossary trước khi Gemini viết lời Review.")
                return
            self.project.glossary = dialog.values()
            self._save(silent=True)
            if any(item.get("status") != "approved" for item in self.project.glossary):
                self.status_label.setText("Glossary vẫn còn tên chưa duyệt.")
                return
        snapshot = copy.deepcopy(self.project)
        windows = self.service.story_arc_windows(snapshot) if snapshot.structure_ready else []

        def task(report, cancelled):
            if not snapshot.structure_ready:
                report(2, "Gemini đang tạo Story Beat, semantic relation và Glossary…")
                structure = self.ai.draft_story_structure(
                    snapshot, cancellation_check=cancelled,
                    progress_callback=lambda message: report(-1, message),
                )
                self.service.merge_glossary_proposals(snapshot, structure.get("glossary_proposals", []))
                self.service.merge_story_structure(snapshot, structure)
                return snapshot, bool(snapshot.glossary), True
            for number, (start, end) in enumerate(windows, 1):
                if cancelled():
                    raise InterruptedError("Đã hủy viết review.")
                report(int(100 * (number - 1) / max(1, len(windows))),
                       f"Đang viết phần {number}/{len(windows)} từ phụ đề…")
                payload = self.ai.review_story_arc(
                    snapshot, start, end, context_clip_path="", keyframe_paths=[],
                    instruction="Nguồn lần này chỉ có SRT/context. Không tự nhận đã xem hình hay nghe phim. Nếu thiếu bằng chứng, ghi rõ needs_more_context và hạ confidence.",
                    cancellation_check=cancelled,
                    progress_callback=lambda message: report(-1, message),
                )
                if payload.get("needs_more_context") and not cancelled():
                    report(-1, f"Phần {number}: Gemini yêu cầu thêm context, đang mở rộng SRT trước/sau…")
                    payload = self.ai.review_story_arc(
                        snapshot, start, end, context_clip_path="", keyframe_paths=[],
                        instruction="EXPAND_CONTEXT: dùng thêm context trước/sau nhưng không kể lấn sang phần khác.",
                        cancellation_check=cancelled,
                        progress_callback=lambda message: report(-1, message),
                    )
                self.service.merge_glossary_proposals(snapshot, payload.get("glossary_proposals", []))
                rows = {str(row.get("scene_id", "")): row for row in payload.get("scene_reviews", [])
                        if isinstance(row, dict)}
                missing = [s.scene_id for s in snapshot.scenes[start:end]
                           if not str(rows.get(s.scene_id, {}).get("review_text", "")).strip()]
                if missing:
                    raise ValueError("AI chưa viết đủ phần: " + ", ".join(missing) + ". Hãy thử lại hoặc kiểm tra API key.")
                for scene in snapshot.scenes[start:end]:
                    self._apply_review_payload(scene, rows[scene.scene_id])
                    scene.edit_plan = []
                    scene.has_ai_edit_plan = False
                report(int(100 * number / max(1, len(windows))), f"Đã viết {number}/{len(windows)} phần.")
            return snapshot, False, False

        def done(result):
            project, glossary_needs_review, structure_only = result
            self.project = project
            self.project.writer_source = "gemini"
            self.project.writer_metadata = {
                "provider": "gemini",
                "model": getattr(getattr(self.ai, "provider", None), "model_name", ""),
            }
            if glossary_needs_review:
                from ui.views.review_glossary import ReviewGlossaryDialog
                dialog = ReviewGlossaryDialog(self.project.glossary, self)
                if dialog.exec() != QDialog.Accepted:
                    self._save(silent=True)
                    self.status_label.setText("Đã tạo Glossary nháp; cần duyệt tên trước khi viết Review.")
                    return
                self.project.glossary = dialog.values()
                if any(item.get("status") != "approved" for item in self.project.glossary):
                    self._save(silent=True)
                    self.status_label.setText("Glossary còn tên chưa duyệt; mở Glossary để hoàn tất.")
                    return
                self._save(silent=True)
                QTimer.singleShot(0, self._write_review_simple)
                return
            if structure_only:
                self._save(silent=True)
                QTimer.singleShot(0, self._write_review_simple)
                return
            if self.project.music_library_path and os.path.isfile(self.project.music_library_path):
                self.music_service.plan_project(
                    self.project, self.music_service.load(self.project.music_library_path),
                )
            self._save(silent=True)
            self._refresh_scene_list()
            if project.scenes:
                self.scene_list.setCurrentRow(0)
            self.status_label.setText("Đã viết Review; đang chuyển sang Piper và lập Edit Plan theo audio thật…")
            QTimer.singleShot(0, lambda: self._generate_tts(on_complete=self._build_measured_edit_plan))

        self._run_task(task, done, "Đang viết lời review từ phụ đề…", lock_scene_list=True)

    # ── Project management ────────────────────────────────────────────────
    # A Movie Review project owns its video, its imported SRT and its Scenes.
    # Every upload writes into the *current* project, so picking a video after
    # an SRT (or the other way round) can never wipe the other half again.

    def _project_root(self) -> str:
        return os.path.join(self.workspace_root, "MovieReviewProjects")

    def _manage_gemini_keys(self):
        dialog = _GeminiKeyPoolDialog(GeminiKeyPool(self.key_pool_path), self)
        dialog.exec()
        count = len(GeminiKeyPool(self.key_pool_path).enabled_keys())
        self.status_label.setText(f"Gemini Key Pool: {count} key đang bật.")

    def _edit_glossary(self):
        from ui.views.review_glossary import ReviewGlossaryDialog
        dialog = ReviewGlossaryDialog(self.project.glossary, self)
        if dialog.exec() == QDialog.Accepted:
            self.project.glossary = dialog.values()
            for scene in self.project.scenes:
                scene.review_text = self.service.enforce_glossary_text(
                    scene.review_text, self.project.glossary,
                )
                scene.narration_plan = self.service.normalize_narration_plan(
                    scene, scene.narration_plan,
                )
                scene.tts_rendered = False
                scene.tts_audio_path = ""
                scene.narration_timings = []
            self._save(silent=True)
            self._refresh_qa_state()
            self.status_label.setText("Đã lưu Glossary; mọi lần viết lại sau sẽ dùng tên chuẩn này.")

    def _analyze_music_library(self):
        default_folder = os.path.join(self.workspace_root, "mymusic")
        folder = QFileDialog.getExistingDirectory(
            self,
            "Chọn thư mục Music Library",
            default_folder if os.path.isdir(default_folder) else self.workspace_root,
        )
        if not folder:
            return
        output_path = os.path.join(self._project_root(), "music_library.json")

        def task(report, is_cancelled):
            def progress(number, total, name):
                if is_cancelled():
                    raise InterruptedError("Đã huỷ phân tích Music Library.")
                report(int(number * 100 / max(1, total)), f"Phân tích nhạc {number}/{total}: {name}")
            return self.music_service.analyze_library(folder, output_path, progress)

        def done(library):
            self.project.music_library_path = output_path
            plans = self.music_service.plan_project(self.project, library)
            self._save(silent=True)
            self._refresh_scene_list()
            selected = sum(1 for item in plans if item.get("track") not in {"", "NONE", None})
            self.status_label.setText(
                f"Music Library: {len(library.get('tracks', []))} bài đã cache · "
                f"{selected}/{len(plans)} Scene dùng nhạc · còn lại MUSIC=NONE."
            )

        self._run_task(task, done, "Đang phân tích và cache Music Library…")

    def _project_roots(self) -> list[str]:
        """Include the new library root and the legacy root for compatibility."""
        return [self._project_root(), os.path.join(self.workspace_root, "projects")]

    def _project_file(self) -> str:
        if self._project_path:
            return self._project_path
        return self._default_project_path(self.project.video_path)

    def _default_project_path(self, video_path: str = "") -> str:
        """Per-video folder when a video is known, timestamped folder otherwise."""
        if video_path:
            return self._path_for_video(video_path)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(self._project_root(), f"MovieReview_{stamp}", "movie_review.json")

    def _path_for_video(self, video_path: str) -> str:
        stem = re.sub(r"[^a-zA-Z0-9]+", "_", Path(video_path).stem).strip("_").lower() or "movie"
        digest = hashlib.sha1(os.path.abspath(video_path).encode("utf-8")).hexdigest()[:8]
        return os.path.join(self._project_root(), f"movie_review_{stem}_{digest}", "movie_review.json")

    def _project_name(self) -> str:
        if not self._project_path:
            return "(chưa tạo)"
        return os.path.basename(os.path.dirname(self._project_path)) or Path(self._project_path).stem

    def _update_project_label(self):
        video = os.path.basename(self.project.video_path) if self.project.video_path else "chưa có video"
        if self.project.srt_path:
            srt = f"{os.path.basename(self.project.srt_path)} ({len(self.project.source_segments)} dòng)"
        else:
            srt = "chưa có SRT"
        self.video_path_label.setText(
            f"Project: {self._project_name()}  ·  Video: {video}  ·  SRT: {srt}  ·  "
            f"{len(self.project.story_contexts)} Scene Context  ·  "
            f"{len(self.project.scenes)} Scene ({len(self.project.scenes)} Narrative Segment)  ·  Writer: {self.project.writer_source}"
        )
        remembered = str(self.settings.value("last_project_path", "") or "")
        self.open_project_btn.setToolTip(
            "Mở project .json đã lưu" + (f" (gần nhất: {remembered})" if remembered else "")
        )
        mode_index = self.mode_combo.findData(self.project.review_mode)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(max(0, mode_index))
        self.mode_combo.blockSignals(False)

    def _on_mode_changed(self):
        self.project.review_mode = str(self.mode_combo.currentData() or "recap")
        for scene in self.project.scenes:
            scene.approved = False
        self._save(silent=True)
        self.status_label.setText("Đã đổi chế độ; hãy Review lại các Scene để áp dụng phong cách mới.")

    @staticmethod
    def _srt_saved_label(project) -> str:
        return os.path.basename(project.srt_path) if project.srt_path else "chưa có"

    def _start_new_project(self, announce: bool = True):
        self.project = MovieReviewProject()
        self._project_path = ""
        self._selected_index = -1
        self._issues_by_scene = {}
        self._length_guard_attempts = {}
        self.source_text.clear()
        self.review_text.blockSignals(True)
        self.review_text.clear()
        self.review_text.blockSignals(False)
        self.scene_list.clear()
        self.keyframe_strip.clear()
        self.keyframe_label.setPixmap(QPixmap())
        self.keyframe_label.setText("Video preview · kiểm tra timestamp SRT")
        self.player.setSource(QUrl())
        self.video_hint_label.clear()
        self.time_label.setText("00:00.000 → 00:00.000")
        self.tts_label.setText("TTS: 0.0s")
        self.confidence_label.setText("Context confidence: —")
        self.link_label.setText("SRT links: —")
        self.music_label.setText("Music: —")
        self.warning_label.clear()
        self._update_project_label()
        self._update_qa_bar([])
        if announce:
            self.status_label.setText("Đã tạo project mới. Hãy upload Video và SRT.")

    def _new_project(self):
        if self._busy:
            return
        if self.project.scenes or self.project.srt_path:
            answer = QMessageBox.question(
                self,
                "Tạo project mới?",
                f"Project hiện tại ({self._project_name()}) đã được lưu.\n"
                "Tạo project mới và bắt đầu lại từ đầu?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self._save(silent=True)
        self._start_new_project()
        self._project_path = self._default_project_path()
        os.makedirs(os.path.dirname(self._project_path), exist_ok=True)
        self._save(silent=True)
        self.status_label.setText(f"Đã tạo project mới: {self._project_name()}. Hãy upload Video và SRT.")

    def _open_project_folder(self):
        start_dir = os.path.dirname(os.path.abspath(self._project_file()))
        os.makedirs(start_dir, exist_ok=True)
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục Movie Review", start_dir)
        if not folder:
            return
        projects = sorted(Path(folder).glob("**/movie_review.json"))
        if len(projects) == 1 and self._load_project_file(str(projects[0])):
            self.status_label.setText(
                f"Đã mở project {self._project_name()} từ thư mục: {os.path.abspath(folder)}"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(folder)))
        self.status_label.setText(f"Đã mở thư mục: {os.path.abspath(folder)}")

    def _open_project(self) -> bool:
        if self._busy:
            return False
        os.makedirs(self._project_root(), exist_ok=True)
        dialog = _ProjectLibraryDialog(self._project_roots(), self)
        if dialog.exec() != QDialog.Accepted or not dialog.selected_path:
            return False
        return self._load_project_file(dialog.selected_path)

    def _load_project_file(self, path: str) -> bool:
        try:
            project = self.service.load(path)
        except Exception as exc:
            QMessageBox.warning(self, "Không mở được project", f"{path}\n\n{exc}")
            return False
        self.project = project
        self._project_path = path
        self._selected_index = -1
        self._load_video()
        self._refresh_scene_list()
        self.settings.setValue("last_project_dir", os.path.dirname(path))
        self.settings.setValue("last_project_path", path)
        self.status_label.setText(
            f"Đã mở {self._project_name()} · {len(self.project.scenes)} Scene · "
            f"SRT: {self._srt_saved_label(self.project)}"
        )
        return True

    def _store_source_srt(self, source_path: str, text: str) -> str:
        """Keep a project-owned copy so a project never depends on the original file."""
        project_dir = os.path.dirname(self._project_file())
        target = os.path.join(project_dir, "source.srt")
        spec_source_original = os.path.join(project_dir, "source", "original.srt")
        try:
            os.makedirs(project_dir, exist_ok=True)
            with open(target, "w", encoding="utf-8-sig", newline="\n") as handle:
                handle.write(text if text.endswith("\n") else text + "\n")
            os.makedirs(os.path.dirname(spec_source_original), exist_ok=True)
            with open(spec_source_original, "w", encoding="utf-8-sig", newline="\n") as handle:
                handle.write(text if text.endswith("\n") else text + "\n")
        except OSError:
            return os.path.abspath(source_path)
        return target

    def _load_video(self):
        self._draft_playing = False
        path = self.project.video_path
        self.video_path_label.setText(os.path.basename(path) if path else "Chưa chọn video")
        self.video_hint_label.clear()
        self._video_warning_shown = False
        self._pending_seek_ms = 0
        if path and os.path.isfile(path):
            self.status_label.setText(f"Đang tải video: {os.path.basename(path)}…")
            self.player.setSource(QUrl.fromLocalFile(path))
        else:
            self.player.setSource(QUrl())

    def _on_media_status(self, status):
        if getattr(self, "_draft_playing", False):
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            self.status_label.setText(f"Video sẵn sàng: {os.path.basename(self.project.video_path or '')}")
            self.video_hint_label.clear()
            # QMediaPlayer keeps a freshly opened video black until it gets a
            # seek (the same workaround the main editor's Qt backend uses), so
            # prime the frame the editor is currently looking at.
            self._seek_player(self._pending_seek_ms or 1)
            # Some Qt video backends need one decoded playback frame before a
            # paused source is visible. Prime only the source monitor.
            self.player.play()
            QTimer.singleShot(120, self.player.pause)
        elif status == QMediaPlayer.InvalidMedia:
            self._warn_video_unplayable(
                "Qt không mở được video này (có thể do codec/container). "
                "Bạn vẫn xem được video preview, hoặc dùng 'Mở bằng trình phát ngoài'."
            )

    def _on_player_error(self, _error, error_string: str):
        self._warn_video_unplayable(
            f"Không phát được video trong cửa sổ này: {error_string}. "
            "Hãy dùng 'Mở bằng trình phát ngoài' để kiểm tra timestamp nguồn."
        )

    def _warn_video_unplayable(self, message: str):
        if not self.project.video_path:
            # Nothing is attached yet, so Qt's "no media" state is expected.
            self.video_hint_label.clear()
            return
        self.video_hint_label.setText(message)
        self.status_label.setText("Video không phát được trong cửa sổ này")
        if self._video_warning_shown:
            return
        self._video_warning_shown = True
        QMessageBox.warning(self, "Không phát được video", message)

    def _seek_player(self, position_ms: int):
        self._pending_seek_ms = max(0, int(position_ms))
        if self.player.mediaStatus() in (QMediaPlayer.NoMedia, QMediaPlayer.LoadingMedia):
            return
        self.player.setPosition(self._pending_seek_ms)

    def _open_video_externally(self):
        path = self.project.video_path
        if not path or not os.path.isfile(path):
            QMessageBox.warning(self, "Thiếu video", "Hãy upload video trước.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))
        self.status_label.setText("Đã mở video bằng ứng dụng mặc định của hệ thống.")

    @staticmethod
    def _read_text(path: str) -> str:
        raw = Path(path).read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1258"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def _choose_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn phim", "", "Video (*.mp4 *.mkv *.mov *.avi *.webm);;All files (*)")
        if not path:
            return
        self._attach_video(os.path.abspath(path))

    def _attach_video(self, absolute: str):
        if not self._project_path:
            candidate = self._path_for_video(absolute)
            if os.path.isfile(candidate):
                resume = QMessageBox.question(
                    self,
                    "Đã có project cho video này",
                    f"Đã có Movie Review project cho video này:\n{candidate}\n\nMở lại project đó?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if resume == QMessageBox.Yes and self._load_project_file(candidate):
                    if self.project.video_path and os.path.isfile(self.project.video_path):
                        self._load_video()
                        self.status_label.setText(f"Đã mở lại {self._project_name()}.")
                        return
            self._project_path = candidate

        previous_video = self.project.video_path
        if previous_video and previous_video != absolute and self.project.scenes:
            answer = QMessageBox.question(
                self,
                "Đổi video",
                "Project này đang có Scene của video khác. Đổi video sẽ xoá Scene hiện tại "
                "(SRT đã nạp vẫn được giữ). Tiếp tục?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            self.project.scenes = []
            self.project.story_contexts = []
            self.project.structure_ready = False

        self.project.source_video_origin = absolute
        self.project.video_path = absolute

        try:
            source_dir = os.path.join(os.path.dirname(self._project_file()), "source")
            os.makedirs(source_dir, exist_ok=True)
            target = os.path.join(source_dir, "video" + (Path(absolute).suffix.lower() or ".mp4"))
            if os.path.abspath(absolute) != os.path.abspath(target) and not os.path.exists(target):
                try:
                    os.link(absolute, target)
                except OSError:
                    pass
        except Exception:
            pass

        duration = 0.0
        try:
            from app.video_processor import get_video_duration
            duration = float(get_video_duration(absolute) or 0.0)
        except Exception:
            duration = 0.0

        if self.project.source_segments:
            self.project.source_validation = self.service.validate_source_subtitles(
                self.project.source_segments, duration,
            )
        self._load_video()
        self._refresh_scene_list()
        self._save(silent=True)
        self.status_label.setText(
            f"Đã gắn video {os.path.basename(absolute)} vào project {self._project_name()} "
            f"(SRT: {self._srt_saved_label(self.project)})."
        )

    def _choose_srt(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn SRT gốc", "", "SubRip (*.srt);;All files (*)")
        if not path:
            return
        self._attach_srt(os.path.abspath(path))

    def _choose_review_srt(self):
        if not self.project.source_segments:
            QMessageBox.warning(self, "Thiếu SRT gốc", "Hãy import SRT gốc trước khi import Review SRT.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Review SRT", "", "SubRip (*.srt);;All files (*)"
        )
        if not path:
            return
        text = self._read_text(path)
        review_segments = parse_srt_to_segments(text)
        if not review_segments:
            QMessageBox.warning(self, "Review SRT không hợp lệ", "Không đọc được các cue Review SRT.")
            return
        metadata = None
        for candidate in (f"{path}.json", str(Path(path).with_suffix(".json"))):
            try:
                metadata = json.loads(Path(candidate).read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                continue
        mapped = self.service.import_review_srt(self.project, review_segments, metadata)
        project_dir = os.path.dirname(self._project_file())
        os.makedirs(project_dir, exist_ok=True)
        stored = os.path.join(project_dir, "review.srt")
        Path(stored).write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8-sig")
        self.project.review_srt_path = stored
        self._save(silent=True)
        self._refresh_scene_list()
        self.status_label.setText(
            f"Đã import {len(mapped)} cue Review và map về SRT gốc "
            f"({sum(1 for item in mapped if item.source_cue_ids)} cue có source links)."
        )

    def _attach_srt(self, source_path: str):
        text = self._read_text(source_path)
        segments = parse_srt_to_segments(text)
        if not segments:
            QMessageBox.warning(self, "SRT không hợp lệ", "Không đọc được SRT. Hãy kiểm tra index và timestamp chuẩn SubRip.")
            return
        if not self._project_path:
            self._project_path = self._default_project_path(self.project.video_path)
        stored = self._store_source_srt(source_path, text)
        self.project.srt_path = stored
        self.project.source_srt_origin = os.path.abspath(source_path)
        self.project.source_segments = segments
        video_duration = 0.0
        if self.project.video_path and os.path.isfile(self.project.video_path):
            try:
                from app.video_processor import get_video_duration
                video_duration = float(get_video_duration(self.project.video_path) or 0.0)
            except Exception:
                video_duration = 0.0
        self.project.source_validation = self.service.validate_source_subtitles(segments, video_duration)
        self.project.scenes = []
        self.project.story_contexts = []
        self.project.structure_ready = False
        self._save(silent=True)
        self._refresh_scene_list()
        issue_count = len(self.project.source_validation.get("issues", []))
        self.status_label.setText(
            f"Đã nạp {len(segments)} subtitle từ {os.path.basename(source_path)} · "
            f"bản sao trong project: {os.path.relpath(stored, os.path.dirname(self._project_file()))} "
            f"(SRT gốc không bị thay đổi; {issue_count} cảnh báo timestamp)."
        )

    def _export_external_review_brief(self):
        if not self.project.source_segments:
            QMessageBox.information(self, "Thiếu SRT", "Hãy chọn video và SRT trước.")
            return
        if not self.project.story_contexts:
            self._build_scenes(on_complete=self._export_external_review_brief)
            return
        default_style = self.project.external_writer_instructions or (
            "Kể tự nhiên và liền mạch như một video recap chuyên nghiệp; câu sau nối ý câu trước, "
            "nhịp nhanh ở hành động, chậm và có điểm nghỉ ở twist/cảm xúc; không đọc lại phụ đề."
        )
        instructions, accepted = QInputDialog.getMultiLineText(
            self, "Yêu cầu cho người viết bên ngoài",
            "Bạn có thể sửa phong cách muốn ChatGPT/DeepSeek viết. Phần này sẽ được đóng gói cùng SRT:",
            default_style,
        )
        if not accepted:
            return
        self.project.external_writer_instructions = instructions.strip()
        self._save(silent=True)
        from app.services.external_review_exchange import ExternalReviewExchange
        folder = os.path.join(os.path.dirname(self._project_file()), "external_review")
        prompt_path = ExternalReviewExchange.export(self.project, folder)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        self.status_label.setText(
            f"Đã tạo một Brief tự chứa: {prompt_path}. Gửi đúng file này cho ChatGPT/DeepSeek rồi nhập JSON trả về."
        )

    def _import_external_review(self):
        if not self.project.source_segments or not self.project.story_contexts:
            QMessageBox.information(self, "Thiếu Context", "Hãy chọn video + SRT và tạo Scene Context trước.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Nhập JSON từ ChatGPT / DeepSeek", "", "JSON (*.json);;Text (*.txt *.md)"
        )
        if not path:
            return
        try:
            from app.services.external_review_exchange import ExternalReviewExchange
            payload = ExternalReviewExchange.load(path)
            scenes = self.service.import_external_review(self.project, payload)
        except Exception as exc:
            QMessageBox.warning(self, "Bản review ngoài không hợp lệ", str(exc))
            return
        imported_dir = os.path.join(os.path.dirname(self._project_file()), "external_review")
        os.makedirs(imported_dir, exist_ok=True)
        imported_copy = os.path.join(imported_dir, "imported_review_response.json")
        if os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(imported_copy)):
            shutil.copy2(path, imported_copy)
        self.project.writer_metadata.update({
            "original_file": os.path.abspath(path),
            "project_copy": os.path.abspath(imported_copy),
        })
        self._save(silent=True)
        self._refresh_scene_list()
        if scenes:
            self.scene_list.setCurrentRow(0)
        pending = [row for row in self.project.glossary if str(row.get("status", "pending")) != "approved"]
        if pending:
            from ui.views.review_glossary import ReviewGlossaryDialog
            dialog = ReviewGlossaryDialog(self.project.glossary, self)
            if dialog.exec() == QDialog.Accepted:
                self.project.glossary = dialog.values()
                for scene in self.project.scenes:
                    scene.review_text = self.service.enforce_glossary_text(
                        scene.review_text, self.project.glossary,
                    )
                    scene.narration_plan = self.service.normalize_narration_plan(
                        scene, scene.narration_plan,
                    )
                self._save(silent=True)
                pending = [row for row in self.project.glossary if str(row.get("status", "pending")) != "approved"]
        suffix = (f" Còn {len(pending)} tên/thuật ngữ phải duyệt trước Piper."
                  if pending else " Có thể tạo Piper và xem bản dựng ngay.")
        self.status_label.setText(f"Đã nhập và kiểm tra {len(scenes)} Narrative Segment từ AI ngoài.{suffix}")

    def _busy_buttons(self) -> tuple:
        return (
            self.new_project_btn, self.open_project_btn, self.project_folder_btn,
            self.gemini_keys_btn, self.glossary_btn, self.music_library_btn,
            self.video_btn, self.srt_btn, self.build_btn, self.analyze_all_btn,
            self.review_srt_btn, self.external_export_btn, self.external_import_btn,
            self.approve_all_btn, self.rewrite_btn, self.expand_btn, self.freeze_btn,
            self.approve_btn, self.tts_btn, self.edit_plan_btn, self.validate_btn, self.sync_btn,
            self.export_srt_btn, self.export_video_btn, self.save_btn,
            self.preview_edited_btn, self.preview_overlay_btn,
        ) + tuple(self.quick_buttons)

    def _set_busy(self, busy: bool, label: str = ""):
        """Lock only the actions that would clash with the running task.

        Browsing the Scene list, scrubbing the video and reading the review
        stay available, so starting a long TTS or Export run never makes the
        window feel dead.
        """
        self._busy = bool(busy)
        if busy and self._review_debounce and self._review_debounce.isActive():
            self._review_debounce.stop()
        self.review_text.setReadOnly(busy)
        self.voice_combo.setEnabled(not busy)
        self.tone_combo.setEnabled(not busy)
        self.narration_speed.setEnabled(not busy)
        self.mode_combo.setEnabled(not busy)
        for button in self._busy_buttons():
            button.setEnabled(not busy)
        if busy:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.show()
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.show()
            self.status_label.setText(label or "Đang xử lý…")
        else:
            self.cancel_btn.hide()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.hide()
            self._cancel_event = None

    def _task_cancelled(self) -> bool:
        return bool(self._cancel_event is not None and self._cancel_event.is_set())

    def _cancel_task(self):
        if self._cancel_event is None:
            return
        self._cancel_event.set()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Đang huỷ… (chờ bước hiện tại kết thúc)")

    def _on_task_progress(self, percent: int, message: str):
        # Progress crosses threads, so a queued update can still arrive after the
        # task already finished or was cancelled. Dropping it keeps the final
        # "Đã huỷ tác vụ."/"Đã xong" status from being overwritten by a stale step.
        if not self._busy:
            return
        if int(percent) < 0:
            if self.progress_bar.maximum() != 0:
                self.progress_bar.setRange(0, 0)
            self.progress_bar.setFormat("đang chờ Gemini…")
        else:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            self.progress_bar.setFormat("%p%")
            self.progress_bar.setValue(max(0, min(100, int(percent))))
        if message:
            self.status_label.setText(message)

    def _run_task(self, task: Callable[[Callable, Callable], object], on_done: Callable[[object], None], label: str, *, lock_scene_list: bool = False):
        if self._busy:
            return
        self._set_busy(True, label)
        if lock_scene_list:
            self.scene_list.setEnabled(False)
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        thread = QThread(self)
        worker = _TaskWorker(task, cancel_event)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(
            lambda percent, message: self._ui_task_dispatcher.dispatch.emit(
                lambda: self._on_task_progress(percent, message)
            )
        )

        def finish(value):
            was_cancelled = self._task_cancelled()
            self._set_busy(False)
            if lock_scene_list:
                self.scene_list.setEnabled(True)
            if was_cancelled:
                self.status_label.setText("Đã huỷ tác vụ.")
            else:
                on_done(value)
            thread.quit()

        def fail(message):
            self._set_busy(False)
            if lock_scene_list:
                self.scene_list.setEnabled(True)
            self.status_label.setText("Có lỗi")
            short_message = message.split("\n\n", 1)[0]
            if "GEMINI_KEYS_EXHAUSTED" in message or "GEMINI_REQUEST_FAILED" in message:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle("Gemini không xử lý được request")
                box.setText(short_message.replace("GEMINI_KEYS_EXHAUSTED:", "").replace("GEMINI_REQUEST_FAILED:", "").strip())
                manage = box.addButton("Nhập / đổi Gemini Key", QMessageBox.ActionRole)
                box.addButton(QMessageBox.Close)
                box.exec()
                if box.clickedButton() is manage:
                    self._manage_gemini_keys()
            else:
                QMessageBox.critical(self, "Movie Review Editor", short_message)
            thread.quit()

        def cancelled(_message):
            self._set_busy(False)
            if lock_scene_list:
                self.scene_list.setEnabled(True)
            self.status_label.setText("Đã huỷ tác vụ.")
            thread.quit()

        worker.finished.connect(
            lambda value: self._ui_task_dispatcher.dispatch.emit(lambda: finish(value))
        )
        worker.failed.connect(
            lambda message: self._ui_task_dispatcher.dispatch.emit(lambda: fail(message))
        )
        worker.cancelled.connect(
            lambda message: self._ui_task_dispatcher.dispatch.emit(lambda: cancelled(message))
        )
        thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
        thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._workers.append(worker)
        self._threads.append(thread)
        thread.start()

    def _analyze_and_create_review(self):
        if not self.project.video_path or not os.path.isfile(self.project.video_path):
            QMessageBox.warning(self, "Thiếu video", "Hãy upload video để dựng hình và preview.")
            return
        if not self.project.source_segments:
            QMessageBox.warning(self, "Thiếu SRT", "Hãy upload SRT trước.")
            return
        if self.project.scenes:
            self._analyze_all()
        else:
            self._build_scenes(continue_to_review=True)

    def _build_scenes(self, continue_to_review: bool = False, on_complete=None):
        if not self.project.source_segments:
            QMessageBox.warning(self, "Thiếu SRT", "Hãy upload SRT trước.")
            return
        segments = list(self.project.source_segments)
        video_path = self.project.video_path

        def task(report, is_cancelled):
            report(3, f"Đang đối chiếu scene cut và tạo Context từ {len(segments)} subtitle…")
            contexts = (self.service.detect_contexts(video_path, segments) if video_path
                        else self.service.group_subtitles_into_contexts(segments))
            report(100, f"Đã gom {len(segments)} subtitle thành {len(contexts)} Scene Context.")
            return contexts

        def done(contexts):
            self.project.story_contexts = contexts
            self.project.structure_ready = False
            self.project.scenes = []
            self._save(silent=True)
            self._refresh_scene_list()
            self.status_label.setText(
                f"Đã gom {len(self.project.source_segments)} subtitle thành {len(contexts)} Scene Context; "
                "bước tiếp theo tạo Story Beat → Cue Merge → Narrative Segment."
            )
            if continue_to_review and contexts and not self._task_cancelled():
                self._analyze_all()
            elif callable(on_complete) and contexts and not self._task_cancelled():
                QTimer.singleShot(0, on_complete)
        self._run_task(task, done, "Đang gom Scene từ SRT…")

    def _refresh_scene_list(self):
        current = self._selected_index
        self.service.plan_project_hybrid(self.project)
        self._refresh_qa_state()
        self._update_project_label()
        by_scene = self._issues_by_scene

        self.scene_list.clear()
        for scene in self.project.scenes:
            scene_issues = by_scene.get(scene.scene_id, [])
            if any(item.get("severity") == "error" for item in scene_issues):
                mark = "⛔"
            elif scene_issues:
                mark = "⚠"
            elif scene.approved:
                mark = "✓"
            elif scene.review_text:
                mark = "AI"
            else:
                mark = "…"
            detail = f"{len(scene.source_cue_ids)} subtitles · {scene.confidence:.0%}"
            detail += f" · TTS ✓ {scene.tts_duration:.1f}s" if scene.tts_rendered else " · TTS —"
            if scene_issues:
                detail += f" · {len(scene_issues)} vấn đề"
            item = QListWidgetItem(
                f"{mark}  {scene.scene_id}   {self._fmt(scene.start)}–{self._fmt(scene.end)}\n     {detail}"
            )
            if scene_issues:
                item.setToolTip("\n".join(f"• {entry['message']}" for entry in scene_issues))
            self.scene_list.addItem(item)
        if self.project.scenes:
            self.scene_list.setCurrentRow(min(max(0, current), len(self.project.scenes) - 1))
        else:
            self._selected_index = -1
            self._clear_editor()

    def _refresh_qa_state(self, issues=None):
        """Re-run QA once and publish it to the QA bar, the list and the editor."""
        if issues is None:
            issues = self.service.validate_project(self.project)
        pending = [issue for issue in issues if issue.get("code") in {"missing_tts", "missing_measured_plan"}]
        issues = [issue for issue in issues if issue.get("code") not in {"missing_tts", "missing_measured_plan"}]
        by_scene: dict[str, list[dict]] = {}
        for issue in issues:
            by_scene.setdefault(str(issue.get("scene_id", "")), []).append(issue)
        self._issues_by_scene = by_scene
        self._update_qa_bar(issues)
        if pending and not self.service.blocking_issues(issues):
            self.qa_label.setText("Chưa hoàn tất tạo giọng/căn hình · ứng dụng sẽ xử lý khi xem bản dựng")
            self.qa_label.setStyleSheet("color: #93a4b8;")

    def _update_scene_warning_label(self, scene):
        """Show the selected Scene's timing notes plus its QA findings."""
        lines = list(scene.warnings)
        for issue in self._issues_by_scene.get(scene.scene_id, []):
            mark = "⛔" if issue.get("severity") == "error" else "⚠"
            lines.append(f"{mark} {issue['message']}")
        self.warning_label.setText("\n".join(lines))

    def _update_qa_bar(self, issues=None):
        if issues is None:
            issues = self.service.validate_project(self.project)
        self.qa_btn.setEnabled(bool(self.project.scenes))
        if not self.project.scenes:
            self.qa_label.setText("QA: chưa có Scene")
            self.qa_label.setStyleSheet("color: #93a4b8;")
            return
        errors = self.service.blocking_issues(issues)
        warnings = self.service.advisory_issues(issues)
        continuity = self.project.continuity_report or {}
        continuity_text = f" · Continuity {float(continuity.get('avg_cues_per_segment', 0) or 0):.1f} cue/đoạn"
        if errors:
            self.qa_label.setText(f"QA: {len(errors)} lỗi chặn Export · {len(warnings)} cảnh báo{continuity_text}")
            self.qa_label.setStyleSheet("color: #fca5a5;")
        elif warnings:
            self.qa_label.setText(f"QA: {len(warnings)} cảnh báo · không chặn Export{continuity_text}")
            self.qa_label.setStyleSheet("color: #fbbf24;")
        else:
            self.qa_label.setText("QA: đạt" + continuity_text)
            self.qa_label.setStyleSheet("color: #6ee7b7;")

    @staticmethod
    def _fmt(seconds: float) -> str:
        minutes, sec = divmod(max(0.0, float(seconds)), 60)
        hours, minutes = divmod(int(minutes), 60)
        return f"{hours:02d}:{minutes:02d}:{sec:06.3f}"

    def _clear_editor(self):
        self.source_text.clear()
        self.review_text.clear()
        self.story_beat_label.setText("STORY BEAT: —")
        self.warning_label.clear()
        self.keyframe_label.setText("Chưa có Scene")
        self.keyframe_strip.clear()

    def _select_scene(self, index: int):
        if not (0 <= index < len(self.project.scenes)):
            return
        self._selected_index = index
        scene = self.project.scenes[index]
        self.source_text.setPlainText("\n".join(f"#{cue_id}  {text}" for cue_id, text in zip(scene.source_cue_ids, scene.source_subtitles)))
        self.review_text.blockSignals(True)
        self.review_text.setPlainText(scene.review_text)
        self.review_text.blockSignals(False)
        beat = scene.story_beat or {}
        beat_parts = [
            f"{label}: {str(beat.get(key, '') or '').strip()}"
            for key, label in (("summary", "BEAT"), ("event_type", "EVENT"),
                               ("emotion_tag", "TONE"), ("importance", "IMPORTANCE"))
            if str(beat.get(key, "") or "").strip()
        ]
        trace = " → ".join(
            f"#{row.get('from_cue')}→#{row.get('to_cue')} {row.get('reason')} ({row.get('gap_ms')}ms)"
            for row in scene.merge_trace
        )
        self.story_beat_label.setText(
            "STORY BEAT: " + (" · ".join(beat_parts) if beat_parts else "—")
            + (f"\nMERGE TRACE: {trace}" if trace else f"\nĐÓNG ĐOẠN: {scene.closed_reason or '—'}")
        )
        self.time_label.setText(f"{self._fmt(scene.start)} → {self._fmt(scene.end)}")
        self.tts_label.setText(f"TTS: {scene.tts_duration:.1f}s · {scene.voice_speed:.2f}x · hold {scene.freeze_duration:.1f}s")
        self.tone_combo.blockSignals(True)
        self.narration_speed.blockSignals(True)
        self.tone_combo.setCurrentIndex(max(0, self.tone_combo.findData(scene.tone)))
        self.narration_speed.setValue(max(0.92, min(1.08, scene.voice_speed)))
        self.tone_combo.blockSignals(False)
        self.narration_speed.blockSignals(False)
        self.confidence_label.setText(
            f"Context confidence: {scene.confidence:.0%} · Bám sát SRT {scene.source_alignment:.0%}"
        )
        self.link_label.setText(
            f"SRT links: {scene.source_cue_ids[0]}–{scene.source_cue_ids[-1]}"
            if scene.source_cue_ids else "SRT links: —"
        )
        music = scene.music or {}
        track_name = str(music.get("track_name", music.get("track", "")) or "")
        self.music_label.setText(
            "Music: NONE" if track_name in {"", "NONE"}
            else f"Music: {os.path.basename(track_name)} · {float(music.get('score', 0.0) or 0.0):.0%}"
        )
        self._update_scene_warning_label(scene)
        self.approve_btn.setText("Approved ✓" if scene.approved else "Approve")
        self.freeze_btn.setText("Freeze ✓" if scene.freeze_manual else "Freeze")
        self.keyframe_strip.clear()
        for path in scene.keyframe_paths:
            self.keyframe_strip.addItem(os.path.basename(path))
        if scene.keyframe_paths:
            self.keyframe_strip.setCurrentRow(0)
        self._seek_player(int(scene.start * 1000))

    def _copy_review_text(self):
        if not (0 <= self._selected_index < len(self.project.scenes)):
            self.status_label.setText("Chưa chọn Scene để copy review.")
            return
        scene = self.project.scenes[self._selected_index]
        if not scene.review_text.strip():
            self.status_label.setText(f"{scene.scene_id} chưa có lời review để copy.")
            return
        QApplication.clipboard().setText(scene.review_text.strip())
        self.status_label.setText(f"Đã copy review của {scene.scene_id}.")

    def _extract_scene_keyframes(self):
        """Extract local preview frames; Gemini v2.1 never receives them."""
        if not (0 <= self._selected_index < len(self.project.scenes)):
            QMessageBox.warning(self, "Chưa chọn Scene", "Hãy chọn một Scene trước khi lấy keyframe.")
            return
        if not self.project.video_path or not os.path.isfile(self.project.video_path):
            QMessageBox.warning(self, "Chưa có video", "Keyframe cần video của project.")
            return
        index = self._selected_index
        scene = self.project.scenes[index]
        video_path = self.project.video_path
        output_dir = os.path.join(
            os.path.dirname(self._project_file()), "keyframes", scene.scene_id.lower()
        )

        def task(report, is_cancelled):
            report(20, f"{scene.scene_id}: đang trích keyframe để kiểm tra hình…")
            if is_cancelled():
                raise InterruptedError("Đã huỷ trích keyframe.")
            paths = self.service.extract_keyframes(video_path, scene, output_dir)
            report(100, f"{scene.scene_id}: {len(paths)} keyframe." if paths else f"{scene.scene_id}: không có keyframe.")
            return paths

        def done(paths):
            self._save(silent=True)
            if index == self._selected_index:
                self._select_scene(index)
            if paths:
                self.status_label.setText(
                    f"{scene.scene_id}: đã trích {len(paths)} keyframe để người dùng kiểm tra hình nguồn."
                )
            else:
                self.status_label.setText(
                    f"{scene.scene_id}: không trích được keyframe từ video này."
                )

        self._run_task(task, done, f"Đang trích keyframe cho {scene.scene_id}…")

    def _select_keyframe(self, index: int):
        if not (0 <= self._selected_index < len(self.project.scenes)):
            return
        paths = self.project.scenes[self._selected_index].keyframe_paths
        if not (0 <= index < len(paths)):
            return
        pixmap = QPixmap(paths[index])
        if not pixmap.isNull():
            self.keyframe_label.setPixmap(pixmap.scaled(self.keyframe_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _play_scene(self):
        self.voice_player.stop()
        if getattr(self, "_draft_playing", False):
            self._draft_playing = False
            self._load_video()
        if not (0 <= self._selected_index < len(self.project.scenes)):
            return
        scene = self.project.scenes[self._selected_index]
        if self.player.mediaStatus() in (QMediaPlayer.NoMedia, QMediaPlayer.InvalidMedia):
            self._warn_video_unplayable(
                "Chưa có video phát được trong cửa sổ này. Hãy Upload Video, "
                "hoặc dùng 'Mở bằng trình phát ngoài'."
            )
            return
        self._seek_player(int(scene.start * 1000))
        self.player.play()
        self.status_label.setText(f"Đang xem {scene.scene_id} ({self._fmt(scene.start)} → {self._fmt(scene.end)}).")

    def _stop_at_scene_end(self, position_ms: int):
        if getattr(self, "_draft_playing", False):
            return
        if not (0 <= self._selected_index < len(self.project.scenes)):
            return
        if position_ms >= int(self.project.scenes[self._selected_index].end * 1000):
            self.player.pause()

    def _review_text_changed(self):
        """Store edits immediately; debounce only the expensive QA refresh."""
        if self._selected_index < 0 or self._busy:
            return
        scene = self.project.scenes[self._selected_index]
        text = self.review_text.toPlainText().strip()
        if scene.review_text == text:
            return
        scene.review_text = text
        scene.narration_plan = []
        scene.narration_timings = []
        scene.narration_signature = ""
        self._length_guard_attempts.pop(scene.scene_id, None)
        scene.edit_plan = []
        scene.has_ai_edit_plan = False
        scene.approved = False
        scene.tts_audio_path = ""
        scene.tts_rendered = False
        scene.narration_timings = []
        scene.narration_signature = ""
        if self._review_debounce:
            self._review_debounce.start(400)

    def _commit_review_text_edit(self):
        """Actually apply the review text change and re-plan (called after debounce timeout)."""
        if self._selected_index < 0:
            return
        scene = self.project.scenes[self._selected_index]
        self.service.plan_project_hybrid(self.project)
        self._refresh_qa_state()
        self.tts_label.setText(f"TTS: {scene.tts_duration:.1f}s · {scene.voice_speed:.2f}x · hold {scene.freeze_duration:.1f}s")
        self._update_scene_warning_label(scene)

    def _analyze_scene(self, index: int, instruction: str = "", continue_all: bool = False):
        if not (0 <= index < len(self.project.scenes)):
            return
        scene = self.project.scenes[index]
        def text_task(report, cancelled):
            report(10, f"{scene.scene_id}: Gemini đang đọc SRT + context + Glossary…")
            payload = self.ai.review_scene(
                self.project, index, instruction=instruction,
                cancellation_check=cancelled,
                progress_callback=lambda message: report(-1, message),
            )
            if payload.get("needs_more_context"):
                scene.context_radius = min(4, scene.context_radius + 1)
                report(55, f"{scene.scene_id}: tự mở rộng context SRT…")
                payload = self.ai.review_scene(
                    self.project, index,
                    instruction="Context SRT đã mở rộng; nối mạch, không bịa. " + instruction,
                    cancellation_check=cancelled,
                    progress_callback=lambda message: report(-1, message),
                )
            return payload

        def text_done(payload):
            self.service.merge_glossary_proposals(self.project, payload.get("glossary_proposals", []))
            self._apply_review_payload(scene, payload)
            self._save(silent=True)
            self._refresh_scene_list()
            self.scene_list.setCurrentRow(index)
            self.status_label.setText(f"Đã viết lại {scene.scene_id}; cần tạo lại Piper/Edit Plan.")
            if continue_all and index + 1 < len(self.project.scenes):
                QTimer.singleShot(0, lambda: self._analyze_scene(index + 1, continue_all=True))

        self._run_task(text_task, text_done, f"Đang viết {scene.scene_id} từ context SRT…")
        return
        total_scenes = max(1, len(self.project.scenes))
        step = max(1, int(round(100 / total_scenes)))
        base = min(95, int(round(100 * index / total_scenes)))

        def task(report, is_cancelled):
            report(base, f"{scene.scene_id}: chuẩn bị video + audio + SRT ({index + 1}/{total_scenes})…")
            if is_cancelled():
                raise InterruptedError("Đã huỷ trước khi gọi Gemini.")
            project_dir = os.path.dirname(self._project_file())
            keyframe_dir = os.path.join(project_dir, "keyframes", scene.scene_id.lower())
            context_dir = os.path.join(project_dir, "context_clips")
            self.service.extract_keyframes(self.project.video_path, scene, keyframe_dir)
            self.service.extract_context_clip(self.project.video_path, scene, context_dir)
            if not scene.context_clip_path or not os.path.isfile(scene.context_clip_path):
                raise RuntimeError("Không tạo được clip Scene có hình chuyển động và âm thanh để Gemini phân tích.")
            def gemini_progress(message):
                report(-1, message)

            report(min(99, base + step // 4), f"{scene.scene_id}: Gemini đang xem video, nghe audio và đối chiếu SRT…")
            payload = self.ai.review_scene(
                self.project, index, instruction=instruction,
                cancellation_check=is_cancelled, progress_callback=gemini_progress,
            )
            if is_cancelled():
                raise InterruptedError("Đã huỷ sau khi Gemini trả kết quả.")
            # Adaptive second look expands all evidence, not just text.
            alignment = float(payload.get("source_alignment", payload.get("confidence", 0.0)) or 0.0)
            if bool(payload.get("needs_more_context")) or min(float(payload.get("confidence", 0.0) or 0.0), alignment) < 0.6:
                scene.context_radius = min(4, scene.context_radius + 1)
                self.service.extract_keyframes(self.project.video_path, scene, keyframe_dir, expanded=True)
                self.service.extract_context_clip(self.project.video_path, scene, context_dir, expanded=True)
                payload = self.ai.review_scene(
                    self.project,
                    index,
                    instruction="Context video/audio/SRT đã được mở rộng. Chỉ kết luận điều có bằng chứng. " + instruction,
                    cancellation_check=is_cancelled,
                    progress_callback=gemini_progress,
                )
            estimated = self.service.estimate_tts_duration(str(payload.get("review_text", "") or ""))
            next_start = self.project.scenes[index + 1].start if index + 1 < len(self.project.scenes) else scene.end
            available = scene.duration + max(0.0, min(2.5, next_start - scene.end))
            if estimated > available:
                report(min(99, base + 2 * step // 3), f"{scene.scene_id}: đang rút gọn cho vừa thời lượng…")
                payload = self.ai.review_scene(
                    self.project,
                    index,
                    instruction=(
                        "Rút gọn mạnh lời review để đọc vừa timestamp nguồn; không dùng speed/freeze để bù thời lượng. "
                        f"Mục tiêu không quá khoảng {max(0.5, available):.1f} giây TTS. " + instruction
                    ),
                    cancellation_check=is_cancelled,
                    progress_callback=gemini_progress,
                )
            payload["review_text"] = self.service.fit_review_to_duration(
                str(payload.get("review_text", "") or ""), available,
            )
            report(min(99, base + 3 * step // 4), f"{scene.scene_id}: lập Edit Plan sau Review Script…")
            plan_payload = self.ai.plan_edit_scene(
                self.project,
                index,
                review_payload=payload,
                cancellation_check=is_cancelled,
                progress_callback=gemini_progress,
            )
            return {"review": payload, "plan": plan_payload}
        def done(result):
            payload = result["review"]
            scene.edit_plan = self.service.normalize_edit_plan(
                scene,
                result["plan"].get("edit_plan", []),
            )
            scene.has_ai_edit_plan = bool(scene.tts_rendered and scene.narration_timings)
            scene.review_text = str(payload.get("review_text", "") or "").strip()
            scene.narration_plan = self.service.normalize_narration_plan(
                scene, payload.get("narration_plan", []),
            )
            scene.summary = str(payload.get("summary", "") or "").strip()
            raw_beat = payload.get("story_beat", {})
            scene.story_beat = {
                key: str(raw_beat.get(key, "") or "").strip()
                for key in ("what", "who", "why", "consequence")
            } if isinstance(raw_beat, dict) else {}
            raw_confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0) or 0.0)))
            scene.source_alignment = max(0.0, min(1.0, float(payload.get("source_alignment", raw_confidence) or 0.0)))
            scene.confidence = min(raw_confidence, scene.source_alignment)
            scene.approved = False
            scene.tts_audio_path = ""
            scene.tts_rendered = False
            self.service.plan_project_hybrid(self.project)
            self._save(silent=True)
            self._refresh_scene_list()
            self.scene_list.setCurrentRow(index)
            self.status_label.setText(
                f"{scene.scene_id}: hiểu video → Review Script → Edit Plan hoàn tất ({scene.confidence:.0%})."
            )
            if continue_all and index + 1 < len(self.project.scenes) and not self._task_cancelled():
                self._analyze_scene(index + 1, continue_all=True)
        self._run_task(task, done, f"Gemini đang hiểu {scene.scene_id} từ video + audio + SRT…")

    def _rewrite_scene(self):
        if self._selected_index >= 0:
            self._analyze_scene(self._selected_index, "Viết lại hấp dẫn hơn nhưng tuyệt đối giữ đúng sự kiện và vừa thời lượng TTS.")

    def _expand_context(self):
        if self._selected_index < 0:
            return
        scene = self.project.scenes[self._selected_index]
        scene.context_radius = min(4, scene.context_radius + 1)
        self._analyze_scene(self._selected_index, "Hãy mở rộng thêm subtitle trước/sau để sửa các điểm chưa chắc chắn.")

    def _toggle_freeze(self):
        if self._selected_index < 0:
            return
        scene = self.project.scenes[self._selected_index]
        if scene.freeze_manual and scene.freeze_duration > 0:
            # Return to the automatic hybrid plan.
            scene.freeze_manual = False
            scene.freeze_duration = 0.0
        else:
            scene.freeze_manual = True
            scene.freeze_duration = min(
                self.service.MAX_FREEZE_DURATION,
                max(0.5, scene.tts_duration - scene.duration),
            )
        # The hold shifts every later scene on the output clock, so re-plan and
        # persist instead of leaving the review track on a stale timeline.
        self.service.plan_project_hybrid(self.project)
        self._save(silent=True)
        self._refresh_scene_list()
        self._select_scene(self._selected_index)
        self.status_label.setText(
            f"{scene.scene_id}: freeze {scene.freeze_duration:.2f}s "
            f"({'thủ công' if scene.freeze_manual else 'tự động'})."
        )

    def _approve_scene(self):
        if self._selected_index < 0:
            return
        scene = self.project.scenes[self._selected_index]
        if not scene.review_text.strip():
            QMessageBox.warning(self, "Chưa thể duyệt", "Scene chưa có lời review.")
            return
        scene.approved = not scene.approved
        self._save(silent=True)
        self._refresh_scene_list()

    def _approve_all(self):
        scenes = self.project.scenes
        if not scenes:
            QMessageBox.warning(self, "Chưa có Scene", "Hãy upload SRT và bấm Gom Scene từ SRT trước.")
            return
        approved = 0
        missing = []
        for scene in scenes:
            if not scene.review_text.strip():
                missing.append(scene.scene_id)
                continue
            if not scene.approved:
                scene.approved = True
                approved += 1
        self._save(silent=True)
        self._refresh_scene_list()
        if 0 <= self._selected_index < len(scenes):
            self._select_scene(self._selected_index)
        if approved:
            message = f"Đã Approve {approved}/{len(scenes)} Scene."
        else:
            message = "Không có Scene mới nào được Approve."
        if missing:
            preview = ", ".join(missing[:8]) + ("…" if len(missing) > 8 else "")
            message += f" Bỏ qua {len(missing)} Scene chưa có lời review: {preview}"
        self.status_label.setText(message)

    def _show_issue_list(self):
        """Read-only view of every Scene that still has QA findings."""
        if not self.project.scenes:
            QMessageBox.warning(self, "Chưa có Scene", "Hãy upload SRT và bấm Gom Scene từ SRT trước.")
            return
        self.service.plan_project_hybrid(self.project)
        issues = self.service.validate_project(self.project)
        self._refresh_qa_state(issues)
        self._save(silent=True)
        if not issues:
            QMessageBox.information(self, "QA đạt", "Không còn Scene nào có lỗi hay cảnh báo.")
            return
        dialog = _ExportWarningDialog(issues, self, allow_export=False)
        dialog.exec()
        self._focus_scene(dialog.jump_scene_id)
        errors = self.service.blocking_issues(issues)
        self.status_label.setText(
            f"QA: {len(errors)} lỗi chặn Export, {len(issues) - len(errors)} cảnh báo."
        )

    def _focus_scene(self, scene_id: str) -> bool:
        if not scene_id:
            return False
        for index, scene in enumerate(self.project.scenes):
            if scene.scene_id == scene_id:
                self.scene_list.setCurrentRow(index)
                self._select_scene(index)
                self.scene_list.scrollToItem(self.scene_list.item(index))
                return True
        return False

    def _available_narration_window(self, index: int) -> float:
        scene = self.project.scenes[index]
        next_start = self.project.scenes[index + 1].start if index + 1 < len(self.project.scenes) else scene.end
        return scene.duration + max(0.0, min(2.5, next_start - scene.end))

    def _ensure_scene_media(self, scene, expanded: bool = False) -> None:
        project_dir = os.path.dirname(self._project_file())
        self.service.extract_keyframes(
            self.project.video_path,
            scene,
            os.path.join(project_dir, "keyframes", scene.scene_id.lower()),
            expanded=expanded,
        )
        self.service.extract_context_clip(
            self.project.video_path,
            scene,
            os.path.join(project_dir, "context_clips"),
            expanded=expanded,
        )

    def _apply_review_payload(self, scene, row: dict, plan_payload: dict | None = None) -> None:
        scene.review_text = self.service.enforce_glossary_text(
            str(row.get("review_text", "") or ""), self.project.glossary,
        )
        scene.narration_plan = self.service.normalize_narration_plan(scene, row.get("narration_plan", []))
        scene.summary = str(row.get("summary", "") or "").strip()
        raw_beat = row.get("story_beat", {})
        scene.story_beat = dict(raw_beat) if isinstance(raw_beat, dict) else {}
        scene.tone = str(row.get("tone") or scene.story_beat.get("emotion_tag") or "NEUTRAL").upper()
        raw_confidence = max(0.0, min(1.0, float(row.get("confidence", 0.0) or 0.0)))
        scene.source_alignment = max(
            0.0,
            min(1.0, float(row.get("source_alignment", raw_confidence) or 0.0)),
        )
        scene.confidence = min(raw_confidence, scene.source_alignment)
        scene.approved = False
        scene.tts_audio_path = ""
        scene.tts_rendered = False
        if plan_payload is not None:
            scene.edit_plan = self.service.normalize_edit_plan(scene, plan_payload.get("edit_plan", []))
            scene.has_ai_edit_plan = not bool(plan_payload.get("pending_audio", False))

    @staticmethod
    def _default_keep_plan(scene) -> dict:
        return {"edit_plan": [{
            "start": scene.start,
            "end": scene.end,
            "action": "KEEP",
            "speed": 1.0,
            "freeze_duration": 0.0,
            "source_cue_ids": list(scene.source_cue_ids),
            "reason": "KEEP mặc định sau khi Edit Plan lỗi.",
        }]}

    def _commit_story_arc_to_ui(self, message: str = "") -> None:
        self.service.plan_project_hybrid(self.project)
        self._save(silent=True)
        self._refresh_scene_list()
        if message:
            self.status_label.setText(message)

    def _analyze_all(self):
        if not self.project.scenes:
            return
        if not self.project.video_path or not os.path.isfile(self.project.video_path):
            QMessageBox.warning(self, "Thiếu video", "Review theo Story Arc cần video của project.")
            return
        windows = self.service.story_arc_windows(self.project)
        project_dir = os.path.dirname(self._project_file())
        total_arcs = max(1, len(windows))

        def task(report, is_cancelled):
            results = []
            notes = []

            def gemini_progress(message):
                report(-1, message)

            def arc_percent(arc_number, fraction):
                span = 100 / total_arcs
                return int(min(99, (arc_number - 1) * span + fraction * span))

            for arc_number, (start, end) in enumerate(windows, start=1):
                if is_cancelled():
                    raise InterruptedError("Đã huỷ phân tích Story Arc.")
                scenes = self.project.scenes[start:end]
                report(
                    arc_percent(arc_number, 0.02),
                    f"Story Arc {arc_number}/{total_arcs}: tách keyframe {scenes[0].scene_id}–{scenes[-1].scene_id}…",
                )
                keyframes = []
                for scene_offset, scene in enumerate(scenes):
                    if is_cancelled():
                        raise InterruptedError("Đã huỷ phân tích Story Arc.")
                    report(
                        arc_percent(arc_number, 0.02 + 0.12 * (scene_offset + 1) / max(1, len(scenes))),
                        f"Story Arc {arc_number}/{total_arcs}: keyframe {scene.scene_id} ({scene_offset + 1}/{len(scenes)})…",
                    )
                    paths = self.service.extract_keyframes(
                        self.project.video_path,
                        scene,
                        os.path.join(project_dir, "keyframes", scene.scene_id.lower()),
                    )
                    keyframes.extend(paths[:2])
                report(arc_percent(arc_number, 0.18), f"Story Arc {arc_number}/{total_arcs}: cắt clip video + audio…")
                arc_clip = self.service.extract_story_arc_clip(
                    self.project.video_path,
                    scenes,
                    os.path.join(project_dir, "story_arc_clips"),
                )
                payload = {"scene_reviews": []}
                if not arc_clip:
                    notes.append(f"Story Arc {arc_number}: không tạo được clip, viết từng Scene.")
                    report(-1, f"Story Arc {arc_number}: không có clip, đang viết bù từng Scene…")
                else:
                    report(-1, f"Story Arc {arc_number}/{total_arcs}: Gemini đang viết mạch kể liên tục…")
                    try:
                        payload = self.ai.review_story_arc(
                            self.project,
                            start,
                            end,
                            context_clip_path=arc_clip,
                            keyframe_paths=keyframes[:10],
                            cancellation_check=is_cancelled,
                            progress_callback=gemini_progress,
                        )
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        notes.append(f"Story Arc {arc_number}: {exc}")
                        report(-1, f"Story Arc {arc_number}: Gemini lỗi, đang viết bù từng Scene…")
                        payload = {"scene_reviews": []}
                rows = payload.get("scene_reviews", []) if isinstance(payload, dict) else []
                by_id = {
                    str(row.get("scene_id", "")): row
                    for row in rows if isinstance(row, dict)
                }
                missing = [
                    scene.scene_id for scene in scenes
                    if scene.scene_id not in by_id or not str(by_id[scene.scene_id].get("review_text", "") or "").strip()
                ]
                if missing:
                    report(
                        arc_percent(arc_number, 0.45),
                        f"Story Arc {arc_number}: thiếu {len(missing)} Scene, đang viết bù…",
                    )
                    for scene_index in range(start, end):
                        scene = self.project.scenes[scene_index]
                        if scene.scene_id not in missing:
                            continue
                        if is_cancelled():
                            raise InterruptedError("Đã huỷ phân tích Story Arc.")
                        report(-1, f"{scene.scene_id}: đang viết bù lời kể còn thiếu…")
                        self._ensure_scene_media(scene)
                        try:
                            row = self.ai.review_scene(
                                self.project,
                                scene_index,
                                instruction="Viết lời kể cho Scene còn thiếu, nối mạch với recap trước.",
                                cancellation_check=is_cancelled,
                                progress_callback=gemini_progress,
                            )
                            row["scene_id"] = scene.scene_id
                            by_id[scene.scene_id] = row
                        except InterruptedError:
                            raise
                        except Exception as exc:
                            notes.append(f"{scene.scene_id}: không viết được ({exc})")
                            by_id[scene.scene_id] = {
                                "scene_id": scene.scene_id,
                                "review_text": "",
                                "confidence": 0.0,
                                "source_alignment": 0.0,
                            }
                for scene_index in range(start, end):
                    if is_cancelled():
                        raise InterruptedError("Đã huỷ phân tích Story Arc.")
                    scene = self.project.scenes[scene_index]
                    row = by_id.get(scene.scene_id) or {"scene_id": scene.scene_id, "review_text": ""}
                    self._apply_review_payload(scene, row)
                    available = self._available_narration_window(scene_index)
                    estimated = self.service.estimate_tts_duration(scene.review_text)
                    if scene.review_text and estimated > available:
                        fitted = self.service.fit_review_to_duration(scene.review_text, available)
                        if self.service.estimate_tts_duration(fitted) <= available + 0.05:
                            report(
                                arc_percent(arc_number, 0.58),
                                f"{scene.scene_id}: cắt bớt câu cho vừa {available:.1f}s TTS…",
                            )
                            scene.review_text = fitted
                            scene.narration_plan = self.service.normalize_narration_plan(scene, scene.narration_plan)
                            row["review_text"] = fitted
                        else:
                            report(-1, f"{scene.scene_id}: lời kể {estimated:.1f}s > {available:.1f}s, Gemini đang rút gọn…")
                            self._ensure_scene_media(scene)
                            try:
                                shortened = self.ai.review_scene(
                                    self.project,
                                    scene_index,
                                    instruction=(
                                        "Rút gọn mạnh lời review để đọc vừa timestamp nguồn; "
                                        "không dùng speed/freeze để bù thời lượng. "
                                        f"Mục tiêu không quá khoảng {max(0.5, available):.1f} giây TTS. "
                                        "Giữ mạch kể với recap trước."
                                    ),
                                    cancellation_check=is_cancelled,
                                    progress_callback=gemini_progress,
                                )
                                self._apply_review_payload(scene, shortened)
                                scene.review_text = self.service.fit_review_to_duration(scene.review_text, available)
                                scene.narration_plan = self.service.normalize_narration_plan(
                                    scene, scene.narration_plan,
                                )
                                row = {**row, **shortened, "review_text": scene.review_text}
                            except InterruptedError:
                                raise
                            except Exception as exc:
                                notes.append(f"{scene.scene_id}: không rút gọn được ({exc})")
                                scene.review_text = fitted
                                scene.narration_plan = self.service.normalize_narration_plan(
                                    scene, scene.narration_plan,
                                )
                                row["review_text"] = fitted
                    if scene.review_text and (scene.confidence < 0.6 or scene.source_alignment < 0.6):
                        report(-1, f"{scene.scene_id}: độ tin cậy {scene.confidence:.0%}, đang viết lại…")
                        scene.context_radius = min(4, scene.context_radius + 1)
                        self._ensure_scene_media(scene, expanded=True)
                        try:
                            retried = self.ai.review_scene(
                                self.project,
                                scene_index,
                                instruction="Context đã mở rộng. Chỉ kết luận điều có bằng chứng và nối mạch kể.",
                                cancellation_check=is_cancelled,
                                progress_callback=gemini_progress,
                            )
                            self._apply_review_payload(scene, retried)
                            row = {**row, **retried}
                        except InterruptedError:
                            raise
                        except Exception as exc:
                            notes.append(f"{scene.scene_id}: không viết lại được ({exc})")
                    report(
                        arc_percent(arc_number, 0.72 + 0.22 * (scene_index - start + 1) / max(1, end - start)),
                        f"Story Arc {arc_number}: lập Edit Plan {scene.scene_id}…",
                    )
                    try:
                        plan_payload = self.ai.plan_edit_scene(
                            self.project,
                            scene_index,
                            review_payload=row,
                            cancellation_check=is_cancelled,
                            progress_callback=gemini_progress,
                        )
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        notes.append(f"{scene.scene_id}: Edit Plan lỗi ({exc}), KEEP toàn Scene.")
                        plan_payload = self._default_keep_plan(scene)
                    self._apply_review_payload(scene, row, plan_payload)
                    results.append((scene_index, row, plan_payload))
                done_message = (
                    f"Story Arc {arc_number}/{total_arcs}: đã ghi {end - start} Scene."
                    if arc_number < total_arcs
                    else f"Story Arc {arc_number}/{total_arcs}: hoàn tất."
                )
                report(arc_percent(arc_number, 1.0) if arc_number < total_arcs else 99, done_message)
                self._ui_task_dispatcher.dispatch.emit(
                    lambda msg=done_message: self._commit_story_arc_to_ui(msg)
                )
            return {"results": results, "notes": notes}

        def done(payload):
            results = payload.get("results", []) if isinstance(payload, dict) else list(payload or [])
            notes = payload.get("notes", []) if isinstance(payload, dict) else []
            self._commit_story_arc_to_ui()
            if self.project.scenes:
                self.scene_list.setCurrentRow(0)
            issues = self.service.validate_project(self.project)
            self._refresh_qa_state(issues)
            errors = self.service.blocking_issues(issues)
            summary = f"Đã viết {len(windows)} Story Arc và phân bổ về {len(results)} Scene."
            if notes:
                preview = notes[0] if len(notes) == 1 else f"{notes[0]} (+{len(notes) - 1} ghi chú khác)"
                summary += " " + preview
            if errors:
                summary += f" QA còn {len(errors)} lỗi chặn Export."
            self.status_label.setText(summary)

        self._run_task(task, done, f"Gemini đang viết {len(windows)} Story Arc liên tục…", lock_scene_list=True)

    def _validate(self):
        self.service.plan_project_hybrid(self.project)
        issues = self.service.validate_project(self.project)
        self._refresh_qa_state(issues)
        self._save(silent=True)
        errors = self.service.blocking_issues(issues)
        warnings = self.service.advisory_issues(issues)
        self._save(silent=True)
        if not issues:
            QMessageBox.information(
                self,
                "Sẵn sàng Export",
                "Timestamp, TTS, overlap, lặp nội dung và độ bám sát SRT đều đạt.",
            )
            self.status_label.setText("QA đạt: sẵn sàng Export.")
            return
        dialog = _ExportWarningDialog(errors + warnings, self, allow_export=False)
        dialog.exec()
        self._focus_scene(dialog.jump_scene_id)
        if errors:
            self.status_label.setText(f"QA: {len(errors)} lỗi chặn Export, {len(warnings)} cảnh báo.")
        else:
            self.status_label.setText(f"QA đạt: {len(warnings)} cảnh báo không chặn Export.")

    def _sync_timeline(self):
        from app.layers.timeline import Timeline
        timeline = Timeline()
        self.service.plan_project_hybrid(self.project)
        layers = self.service.sync_review_track(timeline, self.project)
        timeline_path = os.path.join(os.path.dirname(self._project_file()), "timeline", "project.edl")
        os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
        decisions = self.service.build_edit_decisions(self.project)
        with open(timeline_path, "w", encoding="utf-8") as handle:
            json.dump({"format": "VIU_MOVIE_REVIEW_EDL_V2", "timeline": timeline.to_dict(),
                       "decisions": [item.to_dict() for item in decisions]},
                      handle, ensure_ascii=False, indent=2)
        self._save(silent=True)
        self.status_label.setText(
            f"Đã tạo/cập nhật Track Review với {len(layers)} câu; SRT gốc giữ nguyên."
        )

    def _review_srt_segments(self):
        output = []
        for scene in self.project.scenes:
            for segment in scene.review_segments:
                words = segment.text.split()
                limit = max(3, int(self.project.presentation.get("words_per_caption", 8)))
                char_limit = max(12, int(self.project.presentation.get("max_chars_per_line", 42)))
                # These are proportional phrase timings within a measured
                # sentence, not claimed forced-alignment word timestamps.
                groups = []
                offset = 0
                while offset < len(words):
                    end = offset
                    while end < len(words) and end - offset < limit:
                        candidate = " ".join(words[offset:end + 1])
                        if end > offset and len(candidate) > char_limit:
                            break
                        end += 1
                    end = max(offset + 1, end)
                    groups.append((offset, end))
                    offset = end
                for offset, end in groups:
                    span = segment.end - segment.start
                    output.append({"start": segment.start + span * offset / len(words),
                                   "end": segment.start + span * end / len(words),
                                   "text": " ".join(words[offset:end])})
        return sorted(output, key=lambda item: (item["start"], item["end"]))

    def _reload_voices(self):
        """Populate the voice picker from the app's voice catalog.

        Vietnamese voices come first because the review narration is Vietnamese;
        local Piper Ban Mai is the fast default, while every other installed
        voice remains selectable.
        """
        try:
            from services.voice_catalog_service import VoiceCatalogService
            entries = VoiceCatalogService(self.workspace_root).load_catalog()
        except Exception:
            entries = []
        provider_labels = {"edge": "Edge TTS", "piper": "Piper", "zerotts": "ZeroTTS", "kokoro": "Kokoro"}
        seen: set[str] = set()
        vietnamese: list[tuple[str, str]] = []
        others: list[tuple[str, str]] = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("provider", "") or "").strip().lower()
            raw_id = str(entry.get("id", "") or "").strip()
            if not provider or not raw_id:
                continue
            value = raw_id if provider == "piper" else f"{provider}:{entry.get('provider_voice') or raw_id}"
            if value in seen:
                continue
            seen.add(value)
            label = f"{entry.get('name') or raw_id} · {provider_labels.get(provider, provider)}"
            bucket = vietnamese if str(entry.get("language", "")).lower().split("-", 1)[0] == "vi" else others
            bucket.append((label, value))
        choices = vietnamese + others
        if DEFAULT_REVIEW_VOICE not in seen:
            choices.insert(0, ("Ban Mai · Piper mặc định (nhanh/cục bộ)", DEFAULT_REVIEW_VOICE))

        saved = str(self.settings.value("tts_voice", "") or "").strip()
        env_voice = str(os.getenv("MOVIE_REVIEW_TTS_VOICE", "") or "").strip()
        # Migrate the former Edge default, while preserving a voice the user
        # explicitly selected and any environment override.
        if not env_voice and saved == LEGACY_REVIEW_VOICE:
            saved = DEFAULT_REVIEW_VOICE
        saved = env_voice or saved or DEFAULT_REVIEW_VOICE
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        for label, value in choices:
            self.voice_combo.addItem(label, value)
        index = self.voice_combo.findData(saved)
        if index < 0:
            index = self.voice_combo.findData(DEFAULT_REVIEW_VOICE)
        self.voice_combo.setCurrentIndex(index if index >= 0 else 0)
        self.voice_combo.blockSignals(False)
        self.settings.setValue("tts_voice", self._selected_voice())
        self.voice_combo.setToolTip(
            f"{self.voice_combo.count()} giọng khả dụng · giọng Việt xếp trước · "
            "Edge TTS cần Internet, Piper/ZeroTTS/Kokoro chạy cục bộ."
        )

    def _selected_voice(self) -> str:
        return str(self.voice_combo.currentData() or "").strip() or DEFAULT_REVIEW_VOICE

    def _on_voice_changed(self):
        voice = self._selected_voice()
        self.settings.setValue("tts_voice", voice)
        # Rendered review audio belongs to the previous voice, so re-plan the
        # TTS durations instead of silently exporting the old narration.
        invalidated = 0
        for scene in self.project.scenes:
            if scene.tts_rendered or scene.tts_audio_path:
                scene.tts_audio_path = ""
                scene.tts_rendered = False
                invalidated += 1
        if invalidated:
            self.service.plan_project_hybrid(self.project)
            self._save(silent=True)
            if 0 <= self._selected_index < len(self.project.scenes):
                self._select_scene(self._selected_index)
        self.status_label.setText(
            f"Giọng TTS: {voice}"
            + (f" · cần tạo lại TTS cho {invalidated} Scene" if invalidated else "")
        )

    def _on_narration_settings_changed(self):
        if self._busy or not (0 <= self._selected_index < len(self.project.scenes)):
            return
        scene = self.project.scenes[self._selected_index]
        scene.tone = str(self.tone_combo.currentData() or "NEUTRAL")
        scene.voice_speed = max(0.92, min(1.08, float(self.narration_speed.value())))
        scene.tts_rendered = False
        scene.tts_audio_path = ""
        scene.narration_timings = []
        scene.has_ai_edit_plan = False
        self._save(silent=True)
        self.status_label.setText(f"Đã đổi {scene.scene_id}: {scene.tone}, {scene.voice_speed:.2f}x; cần tạo lại Piper.")

    def _open_voice_manager(self):
        from views.resource_manager import open_resource_manager
        open_resource_manager(self.workspace_root, parent=self)
        self._reload_voices()

    def _generate_tts(self, on_complete=None):
        from app.services.review_narration import narration_signature
        pending_terms = [
            row for row in self.project.glossary
            if str(row.get("status", "pending")) != "approved"
        ]
        if pending_terms:
            QMessageBox.warning(
                self, "Cần duyệt Glossary",
                f"Còn {len(pending_terms)} tên/thuật ngữ chưa duyệt. "
                "Hãy mở Glossary để chốt tên và cách đọc trước khi tạo Piper.",
            )
            return
        scenes = [scene for scene in self.project.scenes if scene.review_text.strip() and (
            not scene.tts_rendered or not os.path.isfile(scene.tts_audio_path)
            or not scene.narration_timings
            or scene.narration_signature != narration_signature(
                self.service.normalize_narration_plan(scene, scene.narration_plan), scene.voice_speed)
        )]
        if not scenes:
            if callable(on_complete):
                QTimer.singleShot(0, on_complete)
            else:
                self.status_label.setText("Giọng đã được tạo cho các lời review hiện tại.")
            return
        voice = self._selected_voice()
        try:
            from services.resource_download_service import ResourceDownloadService
            voice_issues = ResourceDownloadService(self.workspace_root).validate_tts_voice_runtime(voice)
        except Exception:
            voice_issues = []
        if voice_issues:
            QMessageBox.warning(
                self,
                "Giọng TTS chưa sẵn sàng",
                "\n".join(message for _key, message in voice_issues),
            )
            return
        self.service.plan_project_hybrid(self.project)
        tts_dir = os.path.join(os.path.dirname(self._project_file()), "audio", "tts")
        os.makedirs(tts_dir, exist_ok=True)

        total_scenes = len(scenes)

        def task(report, is_cancelled):
            from app.tts_processor import synthesize_text_to_wav_16k_mono
            from app.services.review_narration import render_narration, narration_signature
            results = []
            for number, scene in enumerate(scenes, start=1):
                if is_cancelled():
                    # Keep whatever was already synthesized: each Scene's wav is
                    # an independent artefact, so cancelling is not destructive.
                    return results, True
                report(
                    int(100 * (number - 1) / max(1, total_scenes)),
                    f"TTS {number}/{total_scenes} · {scene.scene_id} · {scene.voice_speed:.2f}x · {voice}",
                )
                narration = self.service.normalize_narration_plan(scene, scene.narration_plan)
                self.service.apply_tts_glossary(scene, self.project.glossary)
                narration = scene.narration_plan
                asset_key = hashlib.sha256((voice + narration_signature(narration, scene.voice_speed)).encode()).hexdigest()[:20]
                output = os.path.join(tts_dir, f"{scene.scene_id.lower()}_{asset_key}.wav")
                try:
                    duration, timings = render_narration(
                        narration, output, voice=voice, voice_speed=scene.voice_speed,
                        synthesize=synthesize_text_to_wav_16k_mono, cancelled=is_cancelled,
                    )
                except InterruptedError:
                    return results, True
                results.append((scene.scene_id, output, duration, timings,
                                narration_signature(narration, scene.voice_speed)))
            report(100, f"Đã tạo TTS cho {len(results)}/{total_scenes} Scene.")
            return results, is_cancelled()

        def done(payload):
            results, was_cancelled = payload
            by_id = {scene.scene_id: scene for scene in self.project.scenes}
            for scene_id, path, duration, timings, signature in results:
                scene = by_id[scene_id]
                scene.tts_audio_path = path
                scene.tts_duration = float(duration)
                scene.tts_rendered = True
                scene.narration_timings = timings
                scene.narration_signature = signature
                scene.has_ai_edit_plan = False
            overlong = [
                index for index, scene in enumerate(self.project.scenes)
                if scene.tts_rendered
                and scene.tts_duration > scene.duration / self.service.MIN_EDIT_SPEED
                    + self.service.MAX_HOLD_DURATION + 0.05
                and self._length_guard_attempts.get(scene.scene_id, 0) < 2
            ]
            if overlong and not was_cancelled and self.project.writer_source == "gemini":
                self._save(silent=True)
                self._repair_length_guard(overlong, on_complete)
                return
            self.service.plan_project_hybrid(self.project)
            self._save(silent=True)
            self._refresh_scene_list()
            self.status_label.setText(
                f"{'Đã huỷ sau khi tạo' if was_cancelled else 'Đã tạo'} TTS thật cho "
                f"{len(results)}/{total_scenes} Scene (giọng {voice}). Tiếp theo: Lập bản dựng sau TTS."
            )
            if not was_cancelled and callable(on_complete):
                QTimer.singleShot(0, on_complete)

        self._run_task(task, done, f"Đang tạo TTS Review ({total_scenes} Scene)…")

    def _repair_length_guard(self, indexes, on_complete=None):
        """Semantic Audio Guard: rewrite only measured overruns, at most twice."""
        def task(report, cancelled):
            repaired = []
            for number, index in enumerate(indexes, start=1):
                scene = self.project.scenes[index]
                target = scene.duration / self.service.MIN_EDIT_SPEED + self.service.MAX_HOLD_DURATION
                report(int((number - 1) * 100 / max(1, len(indexes))),
                       f"Length Guard {scene.scene_id}: rút lời {scene.tts_duration:.1f}s → ≤{target:.1f}s…")
                row = self.ai.review_scene(
                    self.project, index,
                    instruction=(
                        f"AUDIO GUARD: Piper đo {scene.tts_duration:.2f}s, nhưng footage tối đa {target:.2f}s. "
                        "Rút gọn về mặt ngữ nghĩa, giữ sự kiện chính và câu nối với đoạn trước/sau; "
                        "không cắt câu cụt, không tăng speed quá 1.08."
                    ),
                    cancellation_check=cancelled,
                    progress_callback=lambda message: report(-1, message),
                )
                repaired.append((index, row))
            return repaired

        def done(rows):
            for index, row in rows:
                scene = self.project.scenes[index]
                self._length_guard_attempts[scene.scene_id] = self._length_guard_attempts.get(scene.scene_id, 0) + 1
                self._apply_review_payload(scene, row)
            self._save(silent=True)
            self._refresh_scene_list()
            self._generate_tts(on_complete=on_complete)

        self._run_task(task, done, "Length Guard đang sửa các đoạn audio quá dài…", lock_scene_list=True)

    def _build_measured_edit_plan(self, on_complete=None):
        """Plan on a worker-owned snapshot; commit only a complete result."""
        import copy
        if not self.project.scenes or any(
            not scene.tts_rendered or not scene.narration_timings for scene in self.project.scenes
        ):
            QMessageBox.warning(self, "Cần tạo giọng", "Hãy tạo TTS cho toàn bộ lời kể trước khi lập bản dựng.")
            return
        snapshot = copy.deepcopy(self.project)

        def task(report, cancelled):
            plans = []
            for index, scene in enumerate(snapshot.scenes):
                if cancelled():
                    raise InterruptedError("Đã hủy lập bản dựng.")
                if scene.has_ai_edit_plan and scene.edit_plan:
                    plans.append(scene.edit_plan)
                    continue
                report(int(index * 100 / len(snapshot.scenes)), f"Chọn hình cho {scene.scene_id} theo giọng đã đo…")
                # Basic fitting is local. Synthesizing/listening/exporting does
                # not need another Gemini call for every Scene.
                duration = max(0.1, scene.duration)
                needed = max(0.1, scene.tts_duration)
                speed = max(self.service.MIN_EDIT_SPEED, min(1.0, duration / needed))
                hold = max(0.0, needed - duration / speed)
                payload = {"edit_plan": [{
                    "start": scene.start, "end": scene.end,
                    "action": "SLOW_DOWN" if speed < 0.999 else "KEEP",
                    "speed": speed, "freeze_duration": min(4.0, hold),
                    "source_cue_ids": scene.source_cue_ids,
                    "reason": "Căn thời lượng cục bộ theo TTS đã đo.",
                }]}
                plans.append(self.service.normalize_edit_plan(scene, payload["edit_plan"]))
            return plans

        def done(plans):
            for scene, plan in zip(self.project.scenes, plans):
                scene.edit_plan = plan
                scene.has_ai_edit_plan = True
            self.service.plan_project_hybrid(self.project)
            self._refresh_qa_state()
            self._refresh_scene_list()
            self._save(silent=True)
            self.status_label.setText("Đã lập bản dựng theo TTS thực tế. Xem QA trước khi export.")
            if callable(on_complete):
                QTimer.singleShot(0, on_complete)

        self._run_task(task, done, "Đang chọn hình theo lời kể…", lock_scene_list=True)

    def _export_review_srt(self):
        self.service.plan_project_hybrid(self.project)
        default = os.path.join(os.path.dirname(self._project_file()), "exports", "final_review.srt")
        os.makedirs(os.path.dirname(default), exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Xuất Review SRT", default, "SubRip (*.srt)")
        if not path:
            return
        Path(path).write_text(format_segments_to_srt(self._review_srt_segments()), encoding="utf-8-sig")
        self.project.review_srt_path = os.path.abspath(path)
        self._save(silent=True)
        self.status_label.setText(f"Đã xuất Review SRT: {path}")

    def _export_video(self, preview=False):
        if not self.project.video_path or not os.path.isfile(self.project.video_path):
            QMessageBox.warning(self, "Thiếu video", "Hãy upload video trước.")
            return
        self.service.plan_project_hybrid(self.project)
        issues = self.service.validate_project(self.project)
        self._refresh_qa_state(issues)
        self._save(silent=True)
        errors = self.service.blocking_issues(issues)
        warnings = self.service.advisory_issues(issues)
        if errors:
            dialog = _ExportWarningDialog(errors + warnings, self, allow_export=False)
            dialog.exec()
            self._focus_scene(dialog.jump_scene_id)
            self.status_label.setText(f"Chưa thể Export: còn {len(errors)} lỗi.")
            return
        if warnings and not preview:
            dialog = _ExportWarningDialog(warnings, self, allow_export=True)
            accepted = dialog.exec() == QDialog.Accepted and not dialog.jump_scene_id
            if not accepted:
                self._focus_scene(dialog.jump_scene_id)
                self.status_label.setText("Export đã tạm dừng để xem lại cảnh báo.")
                return
        default = os.path.join(os.path.dirname(self._project_file()), "exports", "final_video.mp4")
        os.makedirs(os.path.dirname(default), exist_ok=True)
        if preview:
            output = os.path.join(os.path.dirname(self._project_file()), "review_preview.mp4")
            self.player.stop()
            self.player.setSource(QUrl())
        else:
            output, _ = QFileDialog.getSaveFileName(self, "Export Movie Review", default, "Video (*.mp4)")
        if not output:
            return
        if not output.lower().endswith(".mp4"):
            output += ".mp4"
        work_dir = os.path.join(os.path.dirname(self._project_file()), "exports", ".work")
        os.makedirs(work_dir, exist_ok=True)
        srt_path = os.path.join(os.path.dirname(self._project_file()), "exports", "final_review.srt")
        Path(srt_path).write_text(format_segments_to_srt(self._review_srt_segments()), encoding="utf-8-sig")

        def task(report, is_cancelled):
            from app.services.auto_recap_engine import AutoRecapConfig, AutoRecapEngine
            from app.video_processor import embed_ass_subtitles, get_video_dimensions, get_video_duration, srt_to_ass
            report(2, "Đang chuẩn bị Export…")
            if is_cancelled():
                raise InterruptedError("Đã huỷ trước khi render.")
            render_source = self.project.video_path
            total = float(get_video_duration(self.project.video_path) or 0.0)
            decisions = self.service.build_edit_decisions(self.project, total)
            requires_edit = any(
                decision.action_type == "CUT"
                or abs(float(decision.speed) - 1.0) > 0.001
                or decision.freeze_duration > 0.001
                for decision in decisions
            )
            if requires_edit:
                edit_path = os.path.join(work_dir, "movie_review_edited.mp4")
                engine = AutoRecapEngine(AutoRecapConfig(anti_duplicate=False))
                report(5, "Đang render Edit Plan (cut/speed/freeze)…")

                def on_hold_progress(*args):
                    percent = int(args[0] or 0) if args else 0
                    message = str(args[1]) if len(args) > 1 and args[1] else "Đang render Edit Plan…"
                    report(int(5 + percent * 0.4), message)

                if not engine.render_recap_video_1pass(
                    self.project.video_path, edit_path, decisions, on_progress=on_hold_progress
                ):
                    raise RuntimeError(engine.last_render_error or "Không thể render Edit Plan.")
                render_source = edit_path
            if is_cancelled():
                raise InterruptedError("Đã huỷ sau khi render hold.")
            external_audio = ""
            voiced = [scene for scene in self.project.scenes if scene.tts_rendered and os.path.isfile(scene.tts_audio_path)]
            music_enabled = any(
                (scene.music or {}).get("track") not in {"", "NONE", None}
                and os.path.isfile(str((scene.music or {}).get("track", "")))
                for scene in self.project.scenes
            )
            # Always build one deterministic mix so preview and final export
            # share the same original/voice/music gain and ducking behavior.
            if True:
                ffmpeg = AutoRecapEngine._media_tool_path("ffmpeg")
                mix_path = os.path.join(work_dir, "movie_review_audio_mix.m4a")
                output_duration = float(get_video_duration(render_source) or 0.0)
                command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
                has_original_audio = AutoRecapEngine._input_has_audio(render_source)
                if has_original_audio:
                    command += ["-i", render_source]
                else:
                    command += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                for scene in voiced:
                    command += ["-i", scene.tts_audio_path]
                music_input_index = -1
                if music_enabled:
                    from app.services.music_library_service import MusicLibraryService
                    music_bed = os.path.join(
                        os.path.dirname(self._project_file()), "audio", "music", "movie_review_music_bed.wav"
                    )
                    os.makedirs(os.path.dirname(music_bed), exist_ok=True)
                    MusicLibraryService.render_music_bed(self.project, music_bed, output_duration)
                    music_input_index = 1 + len(voiced)
                    command += ["-i", music_bed]
                settings = self.project.presentation
                filters = [f"[0:a]volume={float(settings.get('original_gain', 0)) / 100:.4f}[original_bg]"]
                labels = ["[original_bg]"]
                voice_labels = []
                for audio_index, scene in enumerate(voiced, start=1):
                    # WAV includes its opening pause; captions begin after it.
                    start_seconds = scene.edit_output_start
                    delay_ms = max(0, int(round(start_seconds * 1000)))
                    label = f"review_voice_{audio_index}"
                    filters.append(f"[{audio_index}:a]volume={float(settings.get('voice_gain', 100))/100:.4f},adelay={delay_ms}:all=1[{label}]")
                    voice_labels.append(f"[{label}]")
                if voice_labels:
                    filters.append(
                        f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:duration=longest:normalize=0[voice_bus]"
                    )
                    if music_enabled:
                        filters.append("[voice_bus]asplit=2[voice_sidechain][voice_mix]")
                        filters.append(
                            f"[{music_input_index}:a]volume={float(settings.get('music_gain', 100))/100:.4f}[music_level];[music_level][voice_sidechain]sidechaincompress="
                            "threshold=0.02:ratio=10:attack=20:release=350:makeup=1[ducked_music]"
                        )
                        labels.extend(["[ducked_music]", "[voice_mix]"])
                    else:
                        labels.append("[voice_bus]")
                elif music_enabled:
                    labels.append(f"[{music_input_index}:a]")
                filters.append(
                    f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0[mix_sum]"
                )
                # Original audio, selected BGM and TTS can add up at an action
                # peak even though ducking is active. Keep one dB of true-peak
                # headroom so the final AAC encode cannot clip.
                filters.append("[mix_sum]alimiter=limit=0.8:attack=5:release=80:level=false[limited_mix]")
                # Leave extra headroom for the second AAC encode performed by
                # the subtitle compositor; AAC inter-sample peaks can otherwise
                # rise by roughly 2 dB after a mix that measured safe as WAV.
                filters.append("[limited_mix]volume=0.6[review_mix]")
                report(48, f"Đang trộn {len(voiced)} TTS + nhạc chọn theo Scene và tự ducking…")
                command += [
                    "-filter_complex", ";".join(filters), "-map", "[review_mix]",
                    "-t", f"{max(0.1, output_duration):.3f}", "-c:a", "aac", "-b:a", "192k", mix_path,
                ]
                mixed = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=1800,
                    **subprocess_hidden_kwargs(),
                )
                if mixed.returncode != 0:
                    raise RuntimeError("Không thể trộn TTS review với âm thanh phim.")
                external_audio = mix_path
            width, height = get_video_dimensions(render_source)
            from app.services.overlay_service import OverlayService
            overlay_render = OverlayService.renderer_config(self.project.presentation, self.project.export_config)
            caption_width = int(overlay_render.get("target_width") or width or 1920)
            caption_height = int(overlay_render.get("target_height") or height or 1080)
            ass_path = srt_to_ass(
                srt_path,
                caption_width,
                caption_height,
                # The imported movie may already contain hard-burned source
                # subtitles. Lift the independent Review track enough to keep
                # two-line Vietnamese captions visually separate from them.
                margin_v=max(0, int(caption_height * float(self.project.presentation.get("bottom_percent", 9)) / 100)),
                font_name="Arial",
                font_size=max(10, int(caption_height * float(self.project.presentation.get("font_percent", 3.2)) / 100)),
                background_box=True,
                animation_style="Fade In",
            )
            report(55, "Đang render video cuối bằng FFmpeg…")
            logos = []
            logo_path = str(self.project.presentation.get("logo_path", ""))
            if self.project.presentation.get("watermark_enabled") and logo_path and os.path.isfile(logo_path):
                from PIL import Image
                with Image.open(logo_path) as logo_image:
                    lw, lh = logo_image.size
                size = float(self.project.presentation.get("logo_percent", 12)) / 100
                position = str(self.project.presentation.get("watermark_position", "bottom-left"))
                logo_height = size * width / max(1, height) * lh / max(1, lw)
                x = 0.03 if position.endswith("left") else max(0.0, 0.97 - size)
                y = 0.03 if position.startswith("top") else max(0.0, 0.97 - logo_height)
                logos.append({"source": logo_path, "x": x, "y": y, "width": size,
                              "height": logo_height,
                              "opacity": float(self.project.presentation.get("watermark_opacity", 60)) / 100})
            title_ass = ""
            title = str(self.project.presentation.get("title", "")).strip()
            if self.project.presentation.get("title_enabled") and title:
                title_srt = os.path.join(work_dir, "review_title.srt")
                title_end = float(get_video_duration(render_source))
                if not self.project.presentation.get("title_persistent", True):
                    title_end = min(5.0, title_end)
                Path(title_srt).write_text(format_segments_to_srt([
                    {"start": 0.0, "end": title_end, "text": title}
                ]), encoding="utf-8-sig")
                title_alignment = 9 if self.project.presentation.get("title_position") == "top-right" else 7
                title_ass = srt_to_ass(title_srt, caption_width, caption_height, alignment=title_alignment,
                                       margin_v=max(12, int(caption_height * 0.05)),
                                       font_size=max(12, int(caption_height * 0.04)))

            def on_export_progress(percent, message=""):
                # embed_ass_subtitles also probes other callback arities; the
                # two-argument form is the one it finally uses.
                span = 0.39 if use_intro else 0.45
                report(int(55 + max(0, min(100, int(percent))) * span), message or "Đang render video cuối…")

            intro_path = str(self.project.presentation.get("intro_bumper_path", ""))
            use_intro = bool(self.project.presentation.get("intro_bumper_enabled")) and os.path.isfile(intro_path)
            composite_output = os.path.join(work_dir, "main_with_overlays.mp4") if use_intro else output
            ok = embed_ass_subtitles(
                render_source,
                ass_path,
                composite_output,
                fast=True,
                audio_input_path=external_audio,
                logo_layers=logos,
                text_ass_path=title_ass,
                **overlay_render,
                progress_callback=on_export_progress,
                cancellation_check=is_cancelled,
            )
            if not ok:
                if is_cancelled():
                    raise InterruptedError("Đã huỷ khi render video cuối.")
                raise RuntimeError("FFmpeg export failed; xem log để biết bộ mã hóa hoặc filter bị lỗi.")
            if use_intro:
                report(94, "Đang ghép Intro Bumper…")
                OverlayService.prepend_intro(
                    AutoRecapEngine._media_tool_path("ffmpeg"), intro_path, composite_output, output,
                    caption_width, caption_height,
                )
            report(100, "Export hoàn tất.")
            return output

        def done(result):
            if preview:
                self._draft_playing = True
                self._pending_seek_ms = 0
                self.audio_output.setVolume(1.0)
                self.player.setSource(QUrl.fromLocalFile(result))
                self.player.play()
                self.status_label.setText("Đang xem bản dựng có giọng, phụ đề và trang trí. Có thể sửa rồi xem lại.")
                return
            self.status_label.setText(f"Export hoàn tất: {result}")
            QMessageBox.information(self, "Export hoàn tất", str(result))

        self._run_task(task, done, "Đang export video bằng pipeline FFmpeg hiện có…", lock_scene_list=True)

    def _save(self, _checked=False, silent: bool = False):
        if not self._project_path and not (self.project.video_path or self.project.srt_path or self.project.scenes):
            return
        if not self._project_path:
            self._project_path = self._default_project_path(self.project.video_path)
        self.service.save(self.project, self._project_path)
        self.settings.setValue("last_project_path", self._project_path)
        self.settings.setValue("last_project_dir", os.path.dirname(self._project_path))
        self._update_project_label()
        if not silent:
            self.status_label.setText(f"Đã lưu project {self._project_name()}: {self._project_path}")

    def closeEvent(self, event):
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._save(silent=True)
        self.player.stop()
        for thread in list(self._threads):
            thread.quit()
            thread.wait(2000)
        super().closeEvent(event)


# Compatibility for any external import made while this feature was being
# developed. The launcher uses MovieReviewEditorWindow directly.
MovieReviewEditorDialog = MovieReviewEditorWindow
