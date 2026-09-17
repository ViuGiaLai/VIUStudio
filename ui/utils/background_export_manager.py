"""Central registry and lifecycle manager for background video export jobs.

Enables:
1. Running video exports in the background while keeping UI interactive.
2. Switching projects or returning to Launcher without interrupting running renders.
3. Real-time progress observation in Launcher and active Editor windows.
4. Automatic persistence of completed video artifacts and recent projects.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, QTimer


@dataclass
class ExportJob:
    job_id: str
    project_id: str
    project_name: str
    project_state_path: str
    video_path: str
    output_path: str
    worker: Any  # QThread / FinalExportWorker
    percent: int = 0
    message: str = "Starting export..."
    status: str = "running"  # "running", "completed", "failed", "cancelled"
    error: str = ""
    is_backgrounded: bool = False
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    @property
    def is_active(self) -> bool:
        return self.status == "running"


class BackgroundExportManager(QObject):
    """Singleton coordinator for background exports across windows and launcher."""

    job_registered = Signal(str)
    job_progress = Signal(str, int, str)       # job_id, percent, message
    job_completed = Signal(str, str)            # job_id, output_path
    job_failed = Signal(str, str)               # job_id, error
    job_cancelled = Signal(str)                 # job_id
    job_backgrounded_changed = Signal(str, bool) # job_id, is_backgrounded

    _instance: Optional[BackgroundExportManager] = None

    @classmethod
    def get_instance(cls) -> BackgroundExportManager:
        if cls._instance is None:
            cls._instance = BackgroundExportManager()
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._jobs: Dict[str, ExportJob] = {}
        self._worker_to_job_id: Dict[int, str] = {}

    def register_job(
        self,
        project_id: str,
        project_name: str,
        project_state_path: str,
        video_path: str,
        output_path: str,
        worker: Any,
    ) -> ExportJob:
        """Register an export worker and monitor its progress/lifecycle."""
        timestamp = int(time.time() * 1000)
        safe_id = (project_id or os.path.splitext(os.path.basename(video_path or "proj"))[0]).strip().replace(" ", "_")
        job_id = f"{safe_id}_{timestamp}"

        job = ExportJob(
            job_id=job_id,
            project_id=project_id,
            project_name=project_name or safe_id,
            project_state_path=os.path.abspath(project_state_path) if project_state_path else "",
            video_path=os.path.abspath(video_path) if video_path else "",
            output_path=os.path.abspath(output_path) if output_path else "",
            worker=worker,
            started_at=time.time(),
        )

        self._jobs[job_id] = job
        if worker is not None:
            self._worker_to_job_id[id(worker)] = job_id
            # Connect signals using helper methods bound to job_id
            try:
                worker.progress.connect(
                    lambda pct, msg, jid=job_id: self._on_worker_progress(jid, pct, msg)
                )
            except Exception as exc:
                print(f"[BackgroundExportManager] Could not connect progress signal: {exc}")

            try:
                worker.finished.connect(
                    lambda out, err, jid=job_id: self._on_worker_finished(jid, out, err)
                )
            except Exception as exc:
                print(f"[BackgroundExportManager] Could not connect finished signal: {exc}")

        self.job_registered.emit(job_id)
        return job

    def get_job(self, job_id: str) -> Optional[ExportJob]:
        return self._jobs.get(job_id)

    def get_active_jobs(self) -> List[ExportJob]:
        return [job for job in self._jobs.values() if job.is_active]

    def has_active_exports(self) -> bool:
        return any(job.is_active for job in self._jobs.values())

    def get_job_by_worker(self, worker: Any) -> Optional[ExportJob]:
        if worker is None:
            return None
        job_id = self._worker_to_job_id.get(id(worker))
        return self._jobs.get(job_id) if job_id else None

    def is_worker_registered(self, worker: Any) -> bool:
        if worker is None:
            return False
        job_id = self._worker_to_job_id.get(id(worker))
        if not job_id:
            return False
        job = self._jobs.get(job_id)
        return bool(job and job.is_active)

    def get_job_for_project(self, state_path_or_id: str, video_path: str = "") -> Optional[ExportJob]:
        """Find an active export job matching project state path, project id, or video path."""
        norm_target_state = os.path.normcase(os.path.abspath(state_path_or_id)) if state_path_or_id and os.path.exists(state_path_or_id) else ""
        norm_target_video = os.path.normcase(os.path.abspath(video_path)) if video_path and os.path.exists(video_path) else ""
        target_id = str(state_path_or_id or "").strip().lower()

        for job in self.get_active_jobs():
            if norm_target_state and job.project_state_path:
                if os.path.normcase(os.path.abspath(job.project_state_path)) == norm_target_state:
                    return job
            if target_id and job.project_id and job.project_id.lower() == target_id:
                return job
            if norm_target_video and job.video_path:
                if os.path.normcase(os.path.abspath(job.video_path)) == norm_target_video:
                    return job
        return None

    def set_backgrounded(self, job_id: str, is_bg: bool = True) -> None:
        job = self._jobs.get(job_id)
        if job and job.is_backgrounded != is_bg:
            job.is_backgrounded = is_bg
            self.job_backgrounded_changed.emit(job_id, is_bg)

    def set_backgrounded_by_worker(self, worker: Any, is_bg: bool = True) -> None:
        job = self.get_job_by_worker(worker)
        if job:
            self.set_backgrounded(job.job_id, is_bg)

    def is_backgrounded(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        return bool(job and job.is_backgrounded)

    def cancel_job(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if not job or not job.is_active:
            return
        worker = job.worker
        if worker is not None:
            try:
                worker.requestInterruption()
            except Exception as exc:
                print(f"[BackgroundExportManager] Error requesting interruption: {exc}")

            def _force_stop():
                try:
                    if getattr(worker, "isRunning", lambda: False)():
                        worker.terminate()
                        worker.wait(200)
                except Exception:
                    pass
                self._on_worker_finished(job_id, "", "Operation cancelled by user")

            QTimer.singleShot(2500, _force_stop)
        else:
            self._on_worker_finished(job_id, "", "Operation cancelled by user")

    def _on_worker_progress(self, job_id: str, percent: int, message: str) -> None:
        job = self._jobs.get(job_id)
        if not job or not job.is_active:
            return
        job.percent = max(0, min(100, int(percent or 0)))
        if message:
            job.message = str(message).strip()
        self.job_progress.emit(job_id, job.percent, job.message)

    def _on_worker_finished(self, job_id: str, output_path: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if not job or not job.is_active:
            return

        job.completed_at = time.time()
        err_text = str(error or "").strip()

        if err_text:
            if "cancel" in err_text.lower():
                job.status = "cancelled"
                job.error = err_text
                job.message = "Export cancelled"
                print(f"[BackgroundExportManager] Job {job_id} cancelled.")
                self.job_cancelled.emit(job_id)
            else:
                job.status = "failed"
                job.error = err_text
                job.message = f"Export failed: {err_text}"
                print(f"[BackgroundExportManager] Job {job_id} failed: {err_text}")
                self.job_failed.emit(job_id, err_text)
        else:
            job.status = "completed"
            job.percent = 100
            job.message = "Export complete"
            resolved_output = os.path.abspath(output_path) if output_path else job.output_path
            job.output_path = resolved_output
            print(f"[BackgroundExportManager] Job {job_id} completed successfully: {resolved_output}")

            # Ensure recent_projects.json reflects the completed project
            self._sync_recent_projects_on_complete(job)
            self.job_completed.emit(job_id, resolved_output)

        # Release worker thread safely
        worker = job.worker
        if worker is not None:
            try:
                from utils.thread_lifecycle import release_thread_when_stopped
                release_thread_when_stopped(worker)
            except Exception:
                pass

    def _sync_recent_projects_on_complete(self, job: ExportJob) -> None:
        """Update recent projects list so Launcher and disk reflect the final video."""
        try:
            from views.launcher import _load_recent_projects, _save_recent_projects, LauncherWindow
            projects = _load_recent_projects()
            record = LauncherWindow._normalize_recent_record({
                "project_state_path": job.project_state_path,
                "video_path": job.video_path,
                "display_name": job.project_name,
                "opened_at": int(time.time()),
            })
            if record is not None:
                key = LauncherWindow._recent_project_key(record)
                filtered = [p for p in projects if LauncherWindow._recent_project_key(p) != key]
                filtered.insert(0, record)
                _save_recent_projects(None, filtered[:24])
        except Exception as exc:
            print(f"[BackgroundExportManager] Could not update recent projects on finish: {exc}")
