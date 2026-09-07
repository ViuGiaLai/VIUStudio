import hashlib
import math
import os
import json
import time
import shutil
import re
import tempfile

from PySide6.QtCore import QSettings, Qt, QTimer, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from runtime_paths import asset_path, subprocess_hidden_kwargs, workspace_root



def _recent_projects_path():
    # ``__file__`` lives inside ``_internal`` in a frozen build. Recent
    # project data belongs beside the executable, not inside bundled assets.
    return os.path.join(workspace_root(), "recent_projects.json")


def _load_recent_projects(settings=None):
    path = _recent_projects_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
                return payload if isinstance(payload, list) else []
    except (OSError, UnicodeError, ValueError, TypeError):
        return []
    return []


def _save_recent_projects(settings, projects):
    path = _recent_projects_path()
    parent = os.path.dirname(os.path.abspath(path)) or os.getcwd()
    os.makedirs(parent, exist_ok=True)
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".tmp", prefix=".recent_",
            dir=parent, delete=False,
        ) as handle:
            temporary_path = handle.name
            json.dump(list(projects or []), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = ""
    finally:
        if temporary_path:
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def _project_pipeline_status(video_path: str = "", state_path: str = "") -> tuple[str, str]:
    """Read the persisted project stage without creating or modifying it."""
    if not state_path:
        name = os.path.splitext(os.path.basename(video_path))[0] or "project"
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower() or "project"
        digest = hashlib.sha1(os.path.abspath(video_path).encode("utf-8")).hexdigest()[:8]
        state_path = os.path.join(workspace_root(), "projects", f"{slug}_{digest}", "project.json")
    try:
        with open(os.path.normpath(state_path), "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError, TypeError):
        return "Ready", "#8394aa"
    artifacts = dict(state.get("artifacts") or {})
    steps = dict(state.get("steps") or {})
    if artifacts.get("final_video"):
        return "Export complete", "#6ee7d6"
    if artifacts.get("voice_vi") or artifacts.get("mixed_vi"):
        return "TTS complete", "#6ee7d6"
    if str(steps.get("translate_raw", "")).lower() == "done" or artifacts.get("translation_final"):
        return "Translate complete", "#78b8ff"
    if artifacts.get("transcript_segments"):
        return "Transcript complete", "#f6c453"
    return "Ready", "#8394aa"


def _extract_thumbnail(video_path: str, output_path: str) -> str:
    if not os.path.exists(video_path):
        return ""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    import subprocess
    try:
        subprocess.run(
            [_ffmpeg_path(), "-y", "-i", video_path, "-vframes", "1", "-q:v", "3",
             "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
             output_path],
            capture_output=True, timeout=30, **subprocess_hidden_kwargs(),
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception:
        pass
    return ""


def _ffmpeg_path():
    from runtime_paths import bin_path
    return os.path.join(bin_path(), "ffmpeg", "ffmpeg.exe")


def _get_video_duration(video_path: str) -> float:
    try:
        import subprocess
        ffprobe = _ffmpeg_path().replace("ffmpeg.exe", "ffprobe.exe")
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30, **subprocess_hidden_kwargs(),
        )
        if result.returncode == 0:
            return float(result.stdout.strip() or 0)
    except Exception:
        pass
    return 0.0


MSG_STYLE = """
    QMessageBox { background-color: #0d121c; }
    QLabel { color: #f1f5f9; font-size: 12px; }
    QPushButton { background-color: #121826; color: #f8fbff; border: 1px solid #1e283a;
        border-radius: 6px; padding: 6px 16px; font-weight: 600; font-size: 11px; }
    QPushButton:hover { background-color: #1c273c; border-color: #6366f1; }
"""


class ProjectCard(QFrame):
    def __init__(self, video_path: str, thumbnail_cache_dir: str, parent=None, *,
                 project_state_path: str = "", display_name: str = ""):
        super().__init__(parent)
        self.video_path = video_path
        self.project_state_path = project_state_path
        self._orig_pixmap = None
        self.setObjectName("projectCard")
        self.setMinimumSize(220, 210)
        self.setMaximumWidth(300)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QFrame#projectCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
            QFrame#projectCard:hover {
                border: 1px solid #6366f1;
                background-color: #172033;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.thumb_label = QLabel()
        self.thumb_label.setMinimumSize(200, 120)
        self.thumb_label.setFixedHeight(125)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background-color: #06080d; border-radius: 8px; color: #64748b; font-size: 11px;")
        self.thumb_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.thumb_label)

        self.name_label = QLabel(display_name or os.path.basename(video_path) or "Untitled Project")
        self.name_label.setWordWrap(True)
        self.name_label.setMaximumHeight(34)
        self.name_label.setStyleSheet("color: #f8fafc; font-size: 12px; font-weight: 600; line-height: 1.2em;")
        layout.addWidget(self.name_label)

        stage_text, stage_color = _project_pipeline_status(video_path, project_state_path)
        self.stage_badge = QLabel(stage_text)
        self.stage_badge.setAlignment(Qt.AlignCenter)
        self.stage_badge.setStyleSheet(
            f"background-color: #080b11; color: {stage_color}; border: 1px solid #1e293b; "
            "border-radius: 999px; padding: 4px 10px; font-size: 10px; font-weight: 700;"
        )
        layout.addWidget(self.stage_badge)

        self._load_thumb(thumbnail_cache_dir)

    def _load_thumb(self, cache_dir):
        if not self.video_path or not os.path.exists(self.video_path):
            self.thumb_label.setText("Empty Project")
            return
        thumb_path = os.path.join(cache_dir, _thumbnail_name(self.video_path))
        if not os.path.exists(thumb_path):
            thumb_path = _extract_thumbnail(self.video_path, thumb_path)
        if os.path.exists(thumb_path):
            self._orig_pixmap = QPixmap(thumb_path)
            self._update_thumb()
        else:
            self.thumb_label.setText("No Preview")

    def _update_thumb(self):
        if self._orig_pixmap is None or self._orig_pixmap.isNull():
            return
        w = max(100, self.thumb_label.width())
        h = max(80, self.thumb_label.height())
        self.thumb_label.setPixmap(self._orig_pixmap.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_thumb()

    def mousePressEvent(self, event):
        if not self.isEnabled():
            event.ignore()
            return
        win = self.window()
        if getattr(win, "_is_accepting", False):
            event.ignore()
            return
        win.selected_video = self.video_path
        win.selected_project_state_path = self.project_state_path
        win.accept()


def _extract_waveform_audio(video_path: str, temp_root: str, duration_s: float = 0.0) -> str:
    video_hash = hashlib.md5(video_path.encode("utf-8")).hexdigest()[:12]
    audio_path = os.path.join(temp_root, f"waveform_{video_hash}.wav")
    if os.path.exists(audio_path):
        return audio_path
    if not os.path.exists(video_path):
        return ""
    os.makedirs(os.path.dirname(audio_path) or ".", exist_ok=True)
    import subprocess
    try:
        subprocess.run(
            [_ffmpeg_path(), "-y", "-loglevel", "error", "-i", video_path,
             "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path],
            check=True,
            timeout=max(180, min(86400, int(max(0.0, duration_s) * 0.5 + 120))),
            **subprocess_hidden_kwargs(),
        )
        print(f"[Launcher] Waveform audio extracted: {audio_path}")
    except Exception as exc:
        print(f"[Launcher] Waveform extract failed: {exc}")
        return ""
    return audio_path if os.path.exists(audio_path) else ""


def _prepare_timeline_visual_cache(video_path: str, temp_root: str) -> None:
    """Build the editor's static V1/A1 cache before opening the editor."""
    try:
        import subprocess

        source = os.path.abspath(video_path)
        stat = os.stat(source)
        digest = hashlib.md5(source.encode("utf-8")).hexdigest()[:12]
        cache_dir = os.path.join(temp_root, "timeline_visuals")
        thumb_dir = os.path.join(temp_root, "timeline_thumbnails")
        manifest_path = os.path.join(cache_dir, f"{digest}.json")
        os.makedirs(cache_dir, exist_ok=True)

        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                existing = json.load(handle)
            if (
                int(existing.get("visual_version", 0)) == 4
                and
                existing.get("source") == source
                and existing.get("size") == int(stat.st_size)
                and existing.get("mtime_ns") == int(stat.st_mtime_ns)
                and existing.get("waveform")
                and all(os.path.exists(path) for _time, path in existing.get("thumbnails", []))
            ):
                print("[Launcher] Timeline visuals loaded from cache")
                return
        except (OSError, ValueError, TypeError):
            pass

        duration_s = _get_video_duration(source)
        if duration_s <= 60.0:
            interval_s = max(2.0, duration_s / 12.0)
        elif duration_s <= 300.0:
            interval_s = max(5.0, duration_s / 30.0)
        else:
            interval_s = max(20.0, duration_s / 90.0)
        thumb_count = max(1, min(120, int(math.ceil(duration_s / interval_s))))
        timestamps = [0.0] if duration_s <= 1.0 else [
            min(duration_s - 0.05, index * interval_s) for index in range(thumb_count)
        ]
        os.makedirs(thumb_dir, exist_ok=True)

        def build_waveform():
            waveform = []
            audio_path = _extract_waveform_audio(source, temp_root, duration_s)
            waveform_duration = duration_s
            if audio_path and os.path.exists(audio_path):
                from app.audio_waveform import build_waveform_envelope

                waveform, audio_duration = build_waveform_envelope(audio_path)
                waveform_duration = max(waveform_duration, audio_duration)
            return waveform, waveform_duration

        def build_thumbnail(index_and_time):
            index, timestamp_s = index_and_time
            output_path = os.path.join(thumb_dir, f"launcher_{digest}_v4_{index:03d}.jpg")
            if not os.path.exists(output_path):
                subprocess.run(
                    [_ffmpeg_path(), "-y", "-loglevel", "error", "-ss", f"{timestamp_s:.3f}",
                     "-i", source, "-frames:v", "1", "-q:v", "4",
                     "-vf", "scale=180:-1:force_original_aspect_ratio=decrease", output_path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=20,
                    **subprocess_hidden_kwargs(),
                )
            return [float(timestamp_s), output_path] if os.path.exists(output_path) and os.path.getsize(output_path) > 0 else None

        # Two independent FFmpeg workers seek the original video directly,
        # while waveform extraction runs alongside them. This stays bounded
        # (two thumbnail processes plus one audio process) and avoids splits.
        from concurrent.futures import ThreadPoolExecutor
        import threading
        print(f"[Launcher] Preparing {thumb_count} timeline thumbnails with 2 workers + waveform worker")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="viustudio-thumbs") as thumbnail_pool:
            # Keep waveform CPU/audio work independent from the two thumbnail
            # slots so all three tasks can progress concurrently.
            waveform_result = []
            waveform_error = []
            def run_waveform():
                try:
                    waveform_result.extend(build_waveform())
                except Exception as exc:
                    waveform_error.append(exc)
            waveform_thread = threading.Thread(target=run_waveform, name="viustudio-waveform", daemon=True)
            waveform_thread.start()
            thumbnails = [item for item in thumbnail_pool.map(build_thumbnail, enumerate(timestamps)) if item]
            waveform_thread.join()
        if waveform_error:
            raise waveform_error[0]
        waveform, duration_s = waveform_result if waveform_result else ([], duration_s)

        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump({
                "visual_version": 4, "source": source, "size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns),
                "duration_s": float(duration_s), "waveform": waveform, "thumbnails": thumbnails,
            }, handle)
        print(f"[Launcher] Timeline visuals prepared: waveform={len(waveform)}, thumbnails={len(thumbnails)}")
    except Exception as exc:
        print(f"[Launcher] Timeline visual preparation skipped: {exc}")


class _SplitVideoWorker(QThread):
    progress = Signal(int, str)
    finished_result = Signal(bool, str)

    def __init__(self, cmd, total_duration, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.total_duration = total_duration

    def run(self):
        from video_processor import run_ffmpeg_with_progress
        try:
            def _prog(event):
                pct = int(event.percent or 0)
                self.progress.emit(pct, f"Splitting… {pct}%")

            ok, _, err = run_ffmpeg_with_progress(
                self.cmd,
                self.total_duration,
                progress_callback=_prog,
                cancellation_check=self.isInterruptionRequested,
            )
            self.finished_result.emit(ok, "" if ok else (err or "FFmpeg process returned non-zero code"))
        except InterruptedError:
            self.finished_result.emit(False, "Cancelled by user")
        except Exception as e:
            self.finished_result.emit(False, str(e))


class LauncherWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.selected_video = ""
        self.selected_project_state_path = ""
        self.selected_device = "cuda"
        self._thumbnail_dir = os.path.join(workspace_root(), "temp", "launcher_thumbs")
        self._loader_timer = None
        self._is_accepting = False

        from runtime_paths import asset_path
        from PySide6.QtGui import QIcon
        logo = asset_path("viustudio.png")
        if os.path.exists(logo):
            self.setWindowIcon(QIcon(logo))

        self.setWindowTitle("VIUStudio - Video Translator")
        self.setMinimumSize(860, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #080b11;
                color: #cdd9e5;
                font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif;
            }
            #headerCard {
                background-color: #0d121c;
                border: 1px solid #1e293b;
                border-radius: 14px;
            }
            #projectCard {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 12px;
            }
            #projectCard:hover {
                border: 1px solid #6366f1;
                background-color: #172033;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #080b11;
                width: 7px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #1e293b;
                min-height: 28px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #334155;
            }
            QFrame#launcherAside {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0d121c, stop:1 #080b11);
                border: 1px solid #1e293b;
                border-radius: 18px;
            }
            QLabel#launcherEyebrow {
                color: #818cf8; font-size: 10px; font-weight: 800;
                letter-spacing: 1.4px;
            }
            QLabel#launcherHero {
                color: #f8fafc; font-size: 27px; font-weight: 900;
            }
            QLabel#launcherAsideBody { color: #94a3b8; font-size: 12px; line-height: 1.4em; }
            QLabel#launcherStep {
                color: #cbd5e1; font-size: 12px; font-weight: 700;
                background: #131926; border: 1px solid #1e293b;
                border-radius: 10px; padding: 10px;
            }
            QLabel#launcherInstallState {
                color: #34d399; font-size: 11px; font-weight: 700;
                background: #064e3b; border: 1px solid #059669;
                border-radius: 10px; padding: 10px;
            }
            QFrame#launcherMainColumn { background: #080b11; border: none; }
            QLabel#launcherSectionLabel { color: #818cf8; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
        """)

        self._build_ui()
        QTimer.singleShot(0, self._load_recent)
        QTimer.singleShot(0, self._validate_resources_for_device)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        aside = QFrame()
        aside.setObjectName("launcherAside")
        aside.setFixedWidth(238)
        aside_layout = QVBoxLayout(aside)
        aside_layout.setContentsMargins(18, 22, 18, 18)
        aside_layout.setSpacing(12)
        eyebrow = QLabel("VIU STUDIO / 01")
        eyebrow.setObjectName("launcherEyebrow")
        aside_layout.addWidget(eyebrow)
        hero = QLabel("Make every\nframe speak.")
        hero.setObjectName("launcherHero")
        hero.setWordWrap(True)
        aside_layout.addWidget(hero)
        body = QLabel("A focused workspace for transcription, translation, voiceover and final delivery.")
        body.setObjectName("launcherAsideBody")
        body.setWordWrap(True)
        aside_layout.addWidget(body)
        aside_layout.addSpacing(8)
        for step in ("01  Bring in a video", "02  Shape the subtitle", "03  Export with confidence"):
            step_label = QLabel(step)
            step_label.setObjectName("launcherStep")
            aside_layout.addWidget(step_label)
        aside_layout.addStretch(1)
        install_state = QLabel("Checking tools…")
        install_state.setObjectName("launcherInstallState")
        install_state.setWordWrap(True)
        aside_layout.addWidget(install_state)
        self.install_state_label = install_state
        root.addWidget(aside)

        main_column = QVBoxLayout()
        main_column.setContentsMargins(0, 0, 0, 0)
        main_column.setSpacing(16)
        root.addLayout(main_column, 1)

        header_frame = QFrame()
        header_frame.setObjectName("headerCard")
        header = QHBoxLayout(header_frame)
        header.setContentsMargins(18, 16, 18, 16)
        header.setSpacing(16)

        title = QLabel("VIUStudio")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #f8fafc; letter-spacing: 0.3px;")
        subtitle = QLabel("Video Translation & Voiceover Studio")
        subtitle.setStyleSheet("font-size: 12px; color: #94a3b8; font-weight: 500;")

        header_text = QVBoxLayout()
        header_text.setSpacing(4)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)

        has_gpu, gpu_name, cuda_ready = self._detect_gpu_with_cuda()
        gpu_usable = has_gpu and cuda_ready
        self.selected_device = "cuda" if gpu_usable else "cpu"
        LauncherWindow._gpu_name = gpu_name if has_gpu else ""

        self._gpu_label = QLabel()
        self._gpu_label.setStyleSheet("font-size: 11px; color: #64748b;")
        header_text.addWidget(self._gpu_label)
        self._update_gpu_label(has_gpu, gpu_name, cuda_ready)

        self._missing_label = QLabel("", self)
        self._missing_label.setWordWrap(True)
        self._missing_label.setStyleSheet(
            "font-size: 11px; color: #fca5a5; padding: 4px 8px;"
            " background-color: #271418; border: 1px solid #4c1d24; border-radius: 6px;"
        )
        self._missing_label.hide()
        header_text.addWidget(self._missing_label)

        device_row = QHBoxLayout()
        device_row.setSpacing(0)
        self.cpu_btn = QPushButton("CPU")
        self.cpu_btn.setCheckable(True)
        self.cpu_btn.setChecked(not gpu_usable)
        self.cpu_btn.setEnabled(True)
        self.gpu_btn = QPushButton("GPU (Accelerated)" if gpu_usable else "GPU (N/A)")
        self.gpu_btn.setCheckable(True)
        self.gpu_btn.setChecked(gpu_usable)
        self.gpu_btn.setEnabled(gpu_usable)

        btn_style = """
            QPushButton {
                color: #94a3b8; border: 1px solid #1e293b; padding: 5px 14px;
                font-size: 11px; font-weight: 700; border-radius: 0;
                background-color: #0d121c;
            }
            QPushButton:hover {
                background-color: #151d2c; color: #f1f5f9;
            }
            QPushButton:checked {
                background-color: #1e1b4b; color: #818cf8; border-color: #6366f1;
            }
            QPushButton:disabled {
                color: #334155; border-color: #131926; background-color: #080b11;
            }
        """
        self.cpu_btn.setStyleSheet(btn_style + "QPushButton { border-top-left-radius: 8px; border-bottom-left-radius: 8px; }")
        self.gpu_btn.setStyleSheet(btn_style + "QPushButton { border-top-right-radius: 8px; border-bottom-right-radius: 8px; border-left: none; }")

        def _select_cpu(checked):
            if checked:
                self.gpu_btn.setChecked(False)
                self._set_selected_device("cpu")
                self._validate_resources_for_device()
            elif not self.gpu_btn.isChecked():
                self.cpu_btn.setChecked(True)

        def _select_gpu(checked):
            if checked:
                self.cpu_btn.setChecked(False)
                self._set_selected_device("cuda")
                self._validate_resources_for_device()
            elif not self.cpu_btn.isChecked():
                self.gpu_btn.setChecked(True)

        self.cpu_btn.clicked.connect(_select_cpu)
        self.gpu_btn.clicked.connect(_select_gpu)

        device_row.addWidget(self.cpu_btn)
        device_row.addWidget(self.gpu_btn)
        device_row.addStretch()
        header_text.addLayout(device_row)
        header.addLayout(header_text, 1)

        action_rows = QVBoxLayout()
        action_rows.setSpacing(8)
        action_row_one = QHBoxLayout()
        action_row_one.setSpacing(8)
        action_row_two = QHBoxLayout()
        action_row_two.setSpacing(8)

        self.new_btn = QPushButton("+ New Project")
        self.new_btn.setMinimumHeight(38)
        self.new_btn.setMinimumWidth(135)
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.setStyleSheet("""
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #10b981, stop:1 #059669);
                color: #ffffff;
                font-weight: 700;
                font-size: 13px;
                border-radius: 8px;
                border: 1px solid #34d399;
                padding: 6px 16px;
                letter-spacing: 0.2px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #34d399, stop:1 #10b981);
                border-color: #6ee7b7;
            }
            QPushButton:pressed {
                background-color: #047857;
                border-color: #059669;
                padding-top: 7px;
            }
            QPushButton:disabled {
                background-color: #112620;
                color: #3b5f54;
                border-color: #1b3830;
            }
        """)
        self.new_btn.clicked.connect(self._on_new_project)
        action_row_one.addWidget(self.new_btn)

        sec_btn_style = """
            QPushButton {
                background-color: #121826;
                color: #cbd5e1;
                font-weight: 600;
                font-size: 12px;
                border-radius: 8px;
                border: 1px solid #1e283a;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #1c273c;
                border-color: #6366f1;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #4f46e5;
                border-color: #818cf8;
                padding-top: 7px;
            }
        """

        self.split_btn = QPushButton("Split Video")
        self.split_btn.setMinimumHeight(38)
        self.split_btn.setMinimumWidth(100)
        self.split_btn.setCursor(Qt.PointingHandCursor)
        self.split_btn.setStyleSheet(sec_btn_style)
        self.split_btn.clicked.connect(self._on_split_video)
        action_row_one.addWidget(self.split_btn)

        self.resource_btn = QPushButton("Setup & Resources")
        self.resource_btn.setMinimumHeight(38)
        self.resource_btn.setMinimumWidth(135)
        self.resource_btn.setCursor(Qt.PointingHandCursor)
        self.resource_btn.setStyleSheet(sec_btn_style)
        self.resource_btn.clicked.connect(self._on_setup_resources)
        action_row_one.addWidget(self.resource_btn)

        self.open_project_btn = QPushButton("Open Projects Folder")
        self.open_project_btn.setMinimumHeight(38)
        self.open_project_btn.setMinimumWidth(145)
        self.open_project_btn.setCursor(Qt.PointingHandCursor)
        self.open_project_btn.setStyleSheet(sec_btn_style)
        self.open_project_btn.setToolTip("Open the VIUStudio projects folder")
        self.open_project_btn.clicked.connect(self._on_open_project_folder)
        action_row_two.addWidget(self.open_project_btn)

        self.clean_video_btn = QPushButton("Clean Data")
        self.clean_video_btn.setMinimumHeight(38)
        self.clean_video_btn.setMinimumWidth(100)
        self.clean_video_btn.setCursor(Qt.PointingHandCursor)
        self.clean_video_btn.setStyleSheet("""
            QPushButton {
                background-color: #271418;
                color: #fca5a5;
                font-weight: 600;
                font-size: 12px;
                border-radius: 8px;
                border: 1px solid #4c1d24;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3d1b22;
                border-color: #ef4444;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #1f0f12;
                padding-top: 7px;
            }
        """)
        self.clean_video_btn.setToolTip("Remove generated project data and video preview caches")
        self.clean_video_btn.clicked.connect(self._on_clean_video_data)
        action_row_two.addWidget(self.clean_video_btn)

        self.about_btn = QPushButton("About / Help")
        self.about_btn.setMinimumHeight(38)
        self.about_btn.setMinimumWidth(100)
        self.about_btn.setCursor(Qt.PointingHandCursor)
        self.about_btn.setStyleSheet(sec_btn_style)
        self.about_btn.clicked.connect(self._on_about)
        action_row_two.addWidget(self.about_btn)

        action_rows.addLayout(action_row_one)
        action_rows.addLayout(action_row_two)
        header.addLayout(action_rows)
        main_column.addWidget(header_frame)

        self.section_label = QLabel("Recent Projects")
        self.section_label.setStyleSheet("font-size: 12px; font-weight: 800; color: #818cf8; letter-spacing: 0.8px; text-transform: uppercase;")
        self.section_label.setObjectName("launcherSectionLabel")
        main_column.addWidget(self.section_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(16)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll.setWidget(self.grid_widget)
        main_column.addWidget(scroll, 1)

        self.empty_label = QLabel("No recent projects. Click \"+ New Project\" to start.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #64748b; font-size: 13px;")
        self.empty_label.hide()
        main_column.addWidget(self.empty_label)

        self.loading_label = QLabel("Preparing video...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("color: #34d399; font-size: 15px; font-weight: 700; padding: 20px;")
        self.loading_label.hide()
        main_column.addWidget(self.loading_label)

    def accept(self):
        if getattr(self, "_is_accepting", False):
            return

        if not self.selected_video or not os.path.exists(self.selected_video):
            self._is_accepting = True
            super().accept()
            return

        try:
            service = self._resource_service()
            is_ok, missing = service.validate_device(self.selected_device)
            if not is_ok:
                from PySide6.QtWidgets import QMessageBox
                labels = [label for _rid, label in missing]
                if self.selected_device == "cpu":
                    prefix = "CPU mode needs:"
                else:
                    prefix = "GPU mode needs:"
                mb = QMessageBox(self)
                mb.setIcon(QMessageBox.Warning)
                mb.setWindowTitle("Missing Resources")
                mb.setText(f"{prefix}\n\n" + "\n".join(f"- {label}" for label in labels))
                mb.setInformativeText("Open Manage Resources to download them.")
                mb.addButton("Manage Resources", QMessageBox.AcceptRole)
                mb.addButton("Close", QMessageBox.RejectRole)
                mb.setStyleSheet(MSG_STYLE)
                mb.exec()
                self._validate_resources_for_device()
                return
        except Exception as exc:
            print(f"[Launcher] Resource validation failed: {exc}")

        self._is_accepting = True
        self._set_selected_device(self.selected_device)
        self.loading_label.show()
        self.loading_label.setText("Opening project...\nTimeline visuals will load in the background.")
        self.new_btn.setEnabled(False)
        # Do not run a second FFmpeg thumbnail/waveform pipeline here.  The
        # editor already owns cancellable background workers and persistent
        # caches for both assets.  The launcher used to wait up to 12 seconds
        # while also allowing those workers to be duplicated after timeout.
        self._extraction_done = True
        QTimer.singleShot(0, self._finish_accept)

    def _stop_loader_timer(self):
        timer = getattr(self, "_loader_timer", None)
        if timer is not None:
            try:
                timer.stop()
                timer.timeout.disconnect(self._on_loader_tick)
            except Exception:
                pass
            self._loader_timer = None

    def _on_loader_tick(self):
        if not getattr(self, "_extraction_done", False):
            return
        self._stop_loader_timer()
        self._finish_accept()

    def _finish_accept(self):
        self._stop_loader_timer()
        self.loading_label.hide()
        self.new_btn.setEnabled(True)
        self._save_device_env()
        super().accept()

    def reject(self):
        self._stop_loader_timer()
        super().reject()

    def closeEvent(self, event):
        self._stop_loader_timer()
        super().closeEvent(event)

    @staticmethod
    def _save_device_env():
        device = getattr(LauncherWindow, "_selected_device", "cuda")
        gpu_name = getattr(LauncherWindow, "_gpu_name", "")
        print(f"[Launcher] Saving VIUSTUDIO_DEVICE={device}, GPU={gpu_name}")
        os.environ["VIUSTUDIO_DEVICE"] = device
        os.environ["VIUSTUDIO_GPU_NAME"] = gpu_name
        # ``__file__`` points inside _internal in a PyInstaller build. The
        # writable package root is the only place both later GUI launches and
        # the spawned worker can consistently read.
        env_path = os.path.join(workspace_root(), ".env")
        try:
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            found = False
            for i, line in enumerate(lines):
                if line.startswith("VIUSTUDIO_DEVICE="):
                    lines[i] = f"VIUSTUDIO_DEVICE={device}\n"
                    found = True
                    break
            if not found:
                lines.append(f"VIUSTUDIO_DEVICE={device}\n")
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception as e:
            print(f"[Launcher] Failed to write .env: {e}")

    def _set_selected_device(self, device: str) -> None:
        """Apply the launcher choice immediately and make it authoritative."""
        normalized = "cuda" if str(device or "").strip().lower() == "cuda" else "cpu"
        self.selected_device = normalized
        LauncherWindow._selected_device = normalized
        # The Main UI and its local worker inherit this exact value. Do not
        # wait for thumbnail preprocessing to finish before publishing it.
        os.environ["VIUSTUDIO_DEVICE"] = normalized

    def _resource_service(self):
        from runtime_paths import workspace_root
        from services import ResourceDownloadService
        return ResourceDownloadService(workspace_root())

    def _on_setup_resources(self):
        """Open the guided installer from the launcher."""
        from views.setup_wizard import open_setup_wizard
        selected_engine = open_setup_wizard(workspace_root(), parent=self)
        if selected_engine:
            # Setup and editor share the same persisted engine key. Keep the
            # legacy ``fast`` value for Piper projects from older builds.
            persisted_engine = "fast" if selected_engine == "piper" else selected_engine
            QSettings("VIUStudio", "VideoTranslatorGUI").setValue("voice_engine", persisted_engine)
        self._validate_resources_for_device()

    def _validate_resources_for_device(self):
        try:
            service = self._resource_service()
        except Exception as exc:
            print(f"[Launcher] Failed to load resource service: {exc}")
            self.new_btn.setEnabled(True)
            return
        device = self.selected_device
        is_ok, missing = service.validate_device(device)
        ffmpeg_ready = os.path.isfile(_ffmpeg_path()) and os.path.isfile(
            _ffmpeg_path().replace("ffmpeg.exe", "ffprobe.exe")
        )
        if not ffmpeg_ready:
            missing = list(missing or [])
            missing.append(("ffmpeg", "FFmpeg/FFprobe tools"))
            is_ok = False
        install_state = getattr(self, "install_state_label", None)
        if install_state is not None:
            install_state.setText(
                "Ready to create a project" if is_ok else
                "Setup needed — use Manage Resources or check the bundled tools"
            )
        self.new_btn.setEnabled(is_ok)
        if device == "cuda":
            has_gpu = True
            gpu_name = ""
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True, text=True, timeout=10,
                    **subprocess_hidden_kwargs(),
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_name = result.stdout.strip().split("\n")[0].strip()
            except Exception:
                pass
            cuda_ready = is_ok
            self._update_gpu_label(has_gpu, gpu_name, cuda_ready)
            if not cuda_ready:
                self.gpu_btn.setEnabled(False)
                self.gpu_btn.setText("GPU (N/A)")
        elif device == "cpu":
            has_gpu, _gpu_name, cuda_ready = self._detect_gpu_with_cuda()
            gpu_usable = has_gpu and cuda_ready
            if gpu_usable:
                self.gpu_btn.setEnabled(True)
                self.gpu_btn.setText("GPU (Recommended)")
                self._update_gpu_label(has_gpu, _gpu_name, cuda_ready)
        if is_ok:
            self._missing_label.hide()
            self._missing_label.setText("")
            if hasattr(self, "new_btn") and self.new_btn.toolTip():
                self.new_btn.setToolTip("")
        else:
            labels = [label for _rid, label in missing]
            if device == "cpu":
                prefix = "CPU mode needs:"
            else:
                prefix = "GPU mode needs:"
            text = f"{prefix} {', '.join(labels)}. Open Manage Resources to set them up."
            self._missing_label.setText(text)
            self._missing_label.show()
            self.new_btn.setToolTip(text)
        try:
            for i in range(self.grid.count()):
                item = self.grid.itemAt(i)
                if item is None:
                    continue
                widget = item.widget()
                if isinstance(widget, ProjectCard):
                    widget.setEnabled(is_ok)
        except Exception:
            pass

    def _load_recent(self):
        projects = _load_recent_projects()
        os.makedirs(self._thumbnail_dir, exist_ok=True)

        for i in reversed(range(self.grid.count())):
            widget = self.grid.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # New records point to project.json. Keep legacy video-only records
        # working, and also discover projects created before launcher history
        # was written.
        existing = []
        seen_projects = set()
        for item in projects:
            record = self._normalize_recent_record(item)
            if record is None:
                continue
            project_key = self._recent_project_key(record)
            if not project_key or project_key in seen_projects:
                continue
            seen_projects.add(project_key)
            existing.append(record)
        projects_root = os.path.join(workspace_root(), "projects")
        if os.path.isdir(projects_root):
            for entry in os.scandir(projects_root):
                state_path = os.path.join(entry.path, "project.json")
                if entry.is_dir() and os.path.isfile(state_path):
                    record = self._normalize_recent_record({"project_state_path": state_path, "opened_at": 0})
                    project_key = self._recent_project_key(record) if record is not None else ""
                    if record is not None and project_key and project_key not in seen_projects:
                        existing.append(record)
                        seen_projects.add(project_key)
        existing.sort(key=lambda item: int(item.get("opened_at", 0) or 0), reverse=True)
        if existing != projects:
            _save_recent_projects(None, existing[:24])

        if not existing:
            self.empty_label.show()
            return
        self.empty_label.hide()

        available_width = max(800, self.grid_widget.width(), self.width() - 48)
        columns = max(3, min(4, available_width // 260))
        for i, proj in enumerate(existing):
            card = ProjectCard(
                proj.get("video_path", ""), self._thumbnail_dir, self,
                project_state_path=proj.get("project_state_path", ""),
                display_name=proj.get("display_name", ""),
            )
            row, col = divmod(i, max(1, columns))
            self.grid.addWidget(card, row, col)
            self.grid.setColumnStretch(col, 0)
        self.grid.setColumnStretch(columns, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._load_recent)

    def _on_new_project(self):
        if getattr(self, "_is_accepting", False):
            return
        from services import ProjectService
        state = ProjectService(workspace_root()).create_project()
        self.selected_video = ""
        self.selected_project_state_path = os.path.join(state.project_root, "project.json")
        self.accept()

    @staticmethod
    def _normalize_recent_record(item):
        if not isinstance(item, dict):
            return None
        raw_state_path = str(item.get("project_state_path", "") or "").strip()
        raw_video_path = str(item.get("video_path", "") or "").strip()
        state_path = os.path.normpath(raw_state_path) if raw_state_path else ""
        video_path = os.path.normpath(raw_video_path) if raw_video_path else ""
        payload = {}
        if not state_path and video_path and os.path.isfile(video_path):
            name = os.path.splitext(os.path.basename(video_path))[0] or "project"
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower() or "project"
            digest = hashlib.sha1(os.path.abspath(video_path).encode("utf-8")).hexdigest()[:8]
            legacy_state = os.path.join(workspace_root(), "projects", f"{slug}_{digest}", "project.json")
            if os.path.isfile(legacy_state):
                state_path = os.path.normpath(legacy_state)
        if state_path and os.path.isfile(state_path):
            projects_root = os.path.normcase(os.path.abspath(os.path.join(workspace_root(), "projects")))
            absolute_state = os.path.normcase(os.path.abspath(state_path))
            try:
                if os.path.commonpath([absolute_state, projects_root]) != projects_root:
                    return None
            except ValueError:
                return None
            try:
                with open(state_path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError, TypeError):
                return None
            video_path = str(payload.get("input_video", "") or video_path)
            if not video_path:
                clips = list((payload.get("settings") or {}).get("timeline_video_clips") or [])
                video_path = next((str(c.get("source", "")) for c in clips if isinstance(c, dict)), "")
            return {
                "project_state_path": state_path,
                "project_id": str(payload.get("project_id", "") or ""),
                "video_path": os.path.normpath(video_path) if video_path else "",
                "display_name": str(payload.get("display_name") or os.path.basename(video_path) or payload.get("project_id") or "Untitled Project"),
                "opened_at": int(item.get("opened_at", 0) or 0),
            }
        if video_path and os.path.isfile(video_path):
            return {"project_state_path": "", "video_path": video_path,
                    "display_name": os.path.basename(video_path),
                    "opened_at": int(item.get("opened_at", 0) or 0)}
        return None

    @staticmethod
    def _recent_project_key(record):
        if not isinstance(record, dict):
            return ""
        project_id = str(record.get("project_id", "") or "").strip().lower()
        if project_id:
            return f"id:{project_id}"
        state_path = str(record.get("project_state_path", "") or "").strip()
        if state_path:
            return f"state:{os.path.normcase(os.path.abspath(state_path))}"
        video_path = str(record.get("video_path", "") or "").strip()
        return f"video:{os.path.normcase(os.path.abspath(video_path))}" if video_path else ""

    def _on_manage_resources(self):
        from views.resource_manager import open_resource_manager
        open_resource_manager(parent=self)
        self._validate_resources_for_device()

    def _on_open_project_folder(self):
        from PySide6.QtWidgets import QMessageBox
        projects_dir = os.path.join(workspace_root(), "projects")
        try:
            os.makedirs(projects_dir, exist_ok=True)
            if hasattr(os, "startfile"):
                os.startfile(projects_dir)
            else:
                from PySide6.QtGui import QDesktopServices
                from PySide6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl.fromLocalFile(projects_dir))
        except Exception as exc:
            message = QMessageBox(QMessageBox.Warning, "Open Project Folder",
                f"Could not open the projects folder:\n\n{exc}", QMessageBox.Ok, self)
            message.setStyleSheet(MSG_STYLE)
            message.exec()

    def _on_clean_video_data(self):
        from PySide6.QtWidgets import QMessageBox

        confirm = QMessageBox(QMessageBox.Warning, "Clean Video Data",
            "Remove all generated project data and video preview caches?\n\n"
            "Source videos, downloaded models, Piper voices, CUDA files, and application resources will not be touched.",
            QMessageBox.Yes | QMessageBox.No, self)
        confirm.setStyleSheet(MSG_STYLE)
        if confirm.exec() != QMessageBox.Yes:
            return

        # Keep generated project/cache data in the explicit writable runtime
        # root rather than deriving it from a module location.
        root = workspace_root()
        targets = [
            os.path.join(root, "projects"),
            os.path.join(root, "temp"),
        ]

        # Project cards can still own loaded thumbnail pixmaps from temp.
        # Detach them and process their deferred deletion before removing the
        # cache tree; this avoids a common first-click Windows file lock.
        try:
            from PySide6.QtWidgets import QApplication
            for index in reversed(range(self.grid.count())):
                item = self.grid.takeAt(index)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
            QApplication.processEvents()
        except Exception:
            pass

        removed = 0
        errors = []
        for target in targets:
            if not os.path.exists(target):
                continue
            last_error = None
            # FFmpeg/thumbnail work can release a file just after the user
            # confirms cleanup. Retry briefly instead of making the user
            # click Clean Video Data a second time.
            for attempt in range(5):
                try:
                    shutil.rmtree(target)
                    removed += 1
                    last_error = None
                    break
                except FileNotFoundError:
                    last_error = None
                    break
                except OSError as exc:
                    last_error = exc
                    if attempt < 4:
                        try:
                            QApplication.processEvents()
                        except Exception:
                            pass
                        time.sleep(0.25 * (attempt + 1))
            if last_error is not None:
                errors.append(f"{os.path.basename(target)}: {last_error}")
        for target in targets:
            try:
                os.makedirs(target, exist_ok=True)
            except OSError:
                pass
        # Cleaning all generated project data also resets the launcher history;
        # no deleted project should remain listed in recent_projects.json.
        try:
            _save_recent_projects(None, [])
            self._load_recent()
        except Exception as exc:
            errors.append(f"recent projects: {exc}")

        if errors:
            detail = "\n".join(errors)
            message = QMessageBox(QMessageBox.Warning, "Clean Video Data",
                f"Some data could not be removed:\n\n{detail}", QMessageBox.Ok, self)
            message.setStyleSheet(MSG_STYLE)
            message.exec()
        else:
            message = QMessageBox(QMessageBox.Information, "Clean Video Data",
                "Generated project data and video caches were cleared.", QMessageBox.Ok, self)
            message.setStyleSheet(MSG_STYLE)
            message.exec()

    def _on_about(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices, QPixmap
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTextBrowser, QVBoxLayout, QHBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("About VIUStudio")
        dialog.setMinimumSize(650, 650)
        dialog.setStyleSheet("QDialog { background: #0a101e; color: #d7e3f4; }")
        layout = QVBoxLayout(dialog)
        title = QLabel("VIUStudio V7 — Tool Information", dialog)
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #ffffff;")
        layout.addWidget(title)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            "QTextBrowser { background: #0f1928; color: #d7e3f4; border: 1px solid #1e3045; "
            "border-radius: 8px; padding: 10px; }"
        )
        browser.setHtml("""
        <h3 style='color:#8ad7ff;'>Description</h3>
        <p>VIUStudio is a Windows application that supports both CPU and GPU processing.</p>
        <p>GPU mode provides the best overall experience and performance. GPU acceleration currently supports NVIDIA GPUs.</p>
        <p>If CUDA is not detected correctly, first update your NVIDIA GPU driver. If needed, install CUDA 12.4 from:<br>
        <a href='https://developer.nvidia.com/cuda-12-4-0-download-archive'>CUDA 12.4 Download Archive</a></p>

        <h3 style='color:#8ad7ff;'>Tutorial / Resource Setup</h3>
        <p>Download the resource, then place it in the matching VIUStudio folder:</p>
        <table cellspacing='6'>
        <tr><td><b>Whisper models</b></td><td><code>VIUStudio\\models\\faster_whisper</code></td></tr>
        <tr><td><b>CUDA / cuDNN runtime</b></td><td><code>VIUStudio\\bin\\cuda12_fw</code></td></tr>
        <tr><td><b>SenseVoice</b></td><td>Bundled by default in <code>VIUStudio\\models\\sensevoice</code></td></tr>
        <tr><td><b>RapidOCR models</b></td><td>Bundled by default; optional files use <code>VIUStudio\\rapidocr\\models</code></td></tr>
        <tr><td><b>Piper voices</b></td><td><code>VIUStudio\\models\\piper</code> (Vietnamese) or <code>VIUStudio\\models\\piper-en</code> (English)</td></tr>
        <tr><td><b>Speaker Detection</b></td><td><code>VIUStudio\\models\\pyannote</code></td></tr>
        </table>
        <p>Resource Manager provides download links for supported optional resources. Extract downloaded archives into the folder shown above.</p>

        <h3 style='color:#8ad7ff;'>How to Setup</h3>
        <p>VIUStudio has two processing modes: <b>CPU Mode</b> and <b>GPU Mode</b>.</p>
        <p><b>CPU Mode:</b> Ready to use immediately without additional downloads. Optional resources add more models, voices, or features.</p>
        <p><b>GPU Mode:</b> Requires the <b>GPU Acceleration Pack</b>. Download and extract it into <code>VIUStudio\\bin</code>. Whisper Medium is optional but recommended for better GPU transcription quality.</p>
        <p>Other resources are optional enhancements. VIUStudio works without them unless you select a feature that needs one.</p>

        <h3 style='color:#8ad7ff;'>How to Use</h3>
        <p><b>Left side:</b> Workflow progress, configuration, and options.</p>
        <p><b>Right side — Top:</b> Video Preview and action buttons on the left; the selected Timeline layer's Inspector on the right.</p>
        <p><b>Right side — Bottom:</b> Timeline Editor and timeline editing actions.</p>
        <ol>
        <li>Use the setup guidance above and download any resources you need.</li>
        <li>Open Settings and select the Subtitle Source and AI Translation provider.</li>
        <li>In Language, select the input and output languages.</li>
        <li>Click <b>Generate</b>: choose <b>Full Pipeline</b> to run automatically, or <b>Step-by-Step</b> for individual phase control.</li>
        </ol>

        <h3 style='color:#8ad7ff;'>Developer Information</h3>
        <p>GitHub: <a href='https://github.com/ViuGiaLai/VIUStudio'>github.com/ViuGiaLai/VIUStudio</a></p>
        """)
        layout.addWidget(browser, 1)

        donation_row = QHBoxLayout()
        donation_row.setSpacing(18)
        donation_label = QLabel("Donate Vietnam\nScan to support development", dialog)
        donation_label.setStyleSheet("color:#d7e3f4; font-weight:600;")
        qr_label = QLabel(dialog)
        qr_label.setAlignment(Qt.AlignCenter)
        qr_path = asset_path("qr.png")
        qr_pixmap = QPixmap(qr_path)
        if not qr_pixmap.isNull():
            qr_label.setPixmap(qr_pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            qr_label.setText("QR unavailable")
        donation_row.addWidget(donation_label)
        donation_row.addWidget(qr_label)
        donation_row.addStretch()

        coffee_group = QHBoxLayout()
        coffee_group.setSpacing(5)
        # coffee_text = QLabel("International Donation\nClick to Buy Me a Coffee", dialog)
        # coffee_text.setStyleSheet("color:#d7e3f4; font-weight:600;")
        # coffee_group.addWidget(coffee_text)
        
        coffee_path = asset_path("buymeacoffee.png")
        coffee_pixmap = QPixmap(coffee_path)
        coffee_image = QLabel(dialog)
        coffee_image.setAlignment(Qt.AlignCenter)
        if not coffee_pixmap.isNull():
            coffee_image.setPixmap(coffee_pixmap.scaled(190, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            coffee_image.setText("Buy Me a Coffee image unavailable")
        coffee_image.setToolTip("Open Buy Me a Coffee")
        coffee_image.setCursor(Qt.PointingHandCursor)
        coffee_image.setAccessibleName("International Donation - Buy Me a Coffee")
        coffee_image.mousePressEvent = lambda _event: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/hcaht"))
        coffee_group.addWidget(coffee_image)
        donation_row.addLayout(coffee_group)
        layout.addLayout(donation_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _on_split_video(self):
        from PySide6.QtWidgets import QMessageBox, QInputDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Long Video to Split", "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm);;All Files (*)"
        )
        if not path:
            return

        duration = _get_video_duration(path)
        if duration <= 7200:
            mb = QMessageBox(QMessageBox.Information, "No Split Needed",
                "This video is under 2 hours. You can open it directly with '+ New Project'.",
                QMessageBox.Ok, self)
            mb.setStyleSheet(MSG_STYLE)
            mb.exec()
            return

        h = int(duration // 3600)
        m = int((duration % 3600) // 60)

        seg_minutes, ok = QInputDialog.getInt(
            self, "Segment Duration",
            f"Video is {h}h {m}m.\nSplit into segments of how many minutes?",
            120, 10, 1440, 10,
        )
        if not ok:
            return

        seg_seconds = seg_minutes * 60
        base, ext = os.path.splitext(path)
        out_pattern = f"{base}_part%03d{ext}"

        reply = QMessageBox(QMessageBox.Question, "Confirm Split",
            f"Split into {seg_minutes}-minute segments using stream copy (no re-encode, fast).\n\n"
            f"Output: {out_pattern}\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, self)
        reply.setStyleSheet(MSG_STYLE)
        if reply.exec() != QMessageBox.Yes:
            return

        from widgets.progress_dialog import PipelineProgressDialog
        progress = PipelineProgressDialog(self)
        progress.title_label.setText("Split Long Video")
        progress.add_step("split", f"Splitting into {seg_minutes}-minute segments")
        progress.start_step("split")

        cmd = [
            _ffmpeg_path(), "-y", "-i", path, "-c", "copy",
            "-f", "segment", "-segment_time", str(seg_seconds),
            "-reset_timestamps", "1", out_pattern,
        ]
        worker = _SplitVideoWorker(cmd, duration, self)
        progress.stop_requested.connect(worker.requestInterruption)

        split_result = {"ok": False, "error": ""}

        def _on_prog(pct, msg):
            progress.update_step_progress("split", pct, msg)

        def _on_done(ok, err):
            split_result["ok"] = ok
            split_result["error"] = err
            if ok:
                progress.finish_step("split")
                progress.set_completed()
            else:
                progress.set_error("split", err or "Split failed")
            QTimer.singleShot(600, progress.accept)

        worker.progress.connect(_on_prog)
        worker.finished_result.connect(_on_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        progress.exec()

        if not split_result["ok"]:
            mb = QMessageBox(QMessageBox.Critical, "Split Failed",
                "Could not split the video.\n\n" + (split_result["error"] or "FFmpeg returned an error."),
                QMessageBox.Ok, self)
            mb.setStyleSheet(MSG_STYLE)
            mb.exec()
            return

        mb = QMessageBox(QMessageBox.Information, "Done",
            f"Video split into {seg_minutes}-minute segments.\nSaved alongside the original file.",
            QMessageBox.Ok, self)
        mb.setStyleSheet(MSG_STYLE)
        mb.exec()

    def _detect_gpu_with_cuda(self):
        has_gpu = False
        gpu_name = ""
        cuda_ready = False
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10,
                **subprocess_hidden_kwargs(),
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_name = result.stdout.strip().split("\n")[0].strip()
                has_gpu = True
        except Exception:
            pass
        if not has_gpu:
            try:
                import torch
                if torch.cuda.is_available():
                    name = torch.cuda.get_device_name(0)
                    vram = torch.cuda.get_device_properties(0).total_mem // (1024 ** 3)
                    gpu_name = f"{name} ({vram}GB)"
                    has_gpu = True
            except Exception:
                pass
        if has_gpu:
            try:
                service = self._resource_service()
                cuda_ready = service.is_requirement_met("cuda:whisper")
            except Exception:
                pass
        return has_gpu, gpu_name, cuda_ready

    def _update_gpu_label(self, has_gpu: bool, gpu_name: str, cuda_ready: bool):
        if has_gpu:
            if cuda_ready:
                self._gpu_label.setText(f"GPU: {gpu_name}  \u2713 CUDA ready")
                self._gpu_label.setStyleSheet("font-size: 11px; color: #4ecdc4;")
            else:
                self._gpu_label.setText(f"GPU: {gpu_name}  \u2717 Need GPU Acceleration Pack")
                self._gpu_label.setStyleSheet("font-size: 11px; color: #ffa500;")
        else:
            self._gpu_label.setText("CPU only")
            self._gpu_label.setStyleSheet("font-size: 11px; color: #5a7a9a;")

    @staticmethod
    def add_recent(settings_or_none, selection):
        if isinstance(selection, dict):
            raw_state_path = str(selection.get("project_state_path", "") or "").strip()
            raw_video_path = str(selection.get("video_path", "") or "").strip()
            project_state_path = os.path.normpath(raw_state_path) if raw_state_path else ""
            video_path = os.path.normpath(raw_video_path) if raw_video_path else ""
        else:
            project_state_path = ""
            raw_video_path = str(selection or "").strip()
            video_path = os.path.normpath(raw_video_path) if raw_video_path else ""
        record = LauncherWindow._normalize_recent_record({
            "project_state_path": project_state_path,
            "video_path": video_path,
            "opened_at": int(time.time()),
        })
        if record is None:
            return
        projects = _load_recent_projects()
        normalized = [LauncherWindow._normalize_recent_record(p) for p in projects]
        normalized = [p for p in normalized if p is not None]
        key = LauncherWindow._recent_project_key(record)
        normalized = [p for p in normalized if LauncherWindow._recent_project_key(p) != key]
        record["opened_at"] = int(time.time())
        normalized.insert(0, record)
        projects = normalized
        projects = projects[:12]
        _save_recent_projects(None, projects)


def _thumbnail_name(video_path: str) -> str:
    import hashlib
    h = hashlib.md5(video_path.encode()).hexdigest()
    return f"{h}.jpg"


def show_launcher(settings_or_none):
    """Show launcher and return a project/video selection descriptor."""
    w = LauncherWindow()
    if w.exec() == QDialog.Accepted:
        return {
            "project_state_path": w.selected_project_state_path,
            "video_path": w.selected_video,
        }
    return None
