"""Background exports management dialog.

Displays all active and recent background export jobs with live progress bars,
status indicators, and action buttons (Cancel, Open Folder).
"""
from __future__ import annotations

import os
from typing import Dict, Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QFrame,
    QWidget,
)

from utils.background_export_manager import BackgroundExportManager, ExportJob


class BackgroundExportsDialog(QDialog):
    """Floating dialog to view and manage background video export jobs."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Background Exports - VIUStudio")
        self.setMinimumSize(540, 360)
        self.resize(600, 420)
        self.setStyleSheet("""
            QDialog {
                background-color: #0b1118;
                color: #cdd9e5;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QLabel {
                color: #cdd9e5;
            }
            QFrame#jobCard {
                background-color: #111a26;
                border: 1px solid #1e2c3d;
                border-radius: 10px;
                padding: 10px;
            }
            QProgressBar {
                background-color: #0d141e;
                border: 1px solid #1e2d40;
                border-radius: 5px;
                height: 14px;
                text-align: center;
                color: #f0f6fc;
                font-size: 10px;
                font-weight: 700;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 4px;
            }
            QPushButton#actionBtn {
                background-color: #162436;
                color: #38bdf8;
                border: 1px solid #223c5b;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#actionBtn:hover {
                background-color: #1e334d;
                border-color: #38bdf8;
                color: #ffffff;
            }
            QPushButton#cancelBtn {
                background-color: #271418;
                color: #fca5a5;
                border: 1px solid #4c1d24;
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#cancelBtn:hover {
                background-color: #3d1b22;
                border-color: #ef4444;
                color: #ffffff;
            }
            QPushButton#cancelBtn:disabled {
                background-color: #181014;
                color: #55333a;
                border-color: #2a161b;
            }
            QPushButton#closeBtn {
                background-color: #162030;
                color: #94a3b8;
                border: 1px solid #24354c;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#closeBtn:hover {
                background-color: #1e2c40;
                color: #ffffff;
            }
        """)

        self._job_widgets: Dict[str, dict] = {}
        self._build_ui()
        self._connect_manager()
        self.refresh_jobs()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        title_label = QLabel("⚡ Video Export Queue (Background Jobs)")
        title_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #34d399;")
        header_row.addWidget(title_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll, 1)

        self.empty_label = QLabel("No active or recent background exports.")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #64748b; font-size: 12px; padding: 30px;")
        layout.addWidget(self.empty_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close", self)
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _connect_manager(self):
        mgr = BackgroundExportManager.get_instance()
        mgr.job_progress.connect(self._on_job_progress)
        mgr.job_completed.connect(self._on_job_completed)
        mgr.job_failed.connect(self._on_job_failed)
        mgr.job_cancelled.connect(self._on_job_cancelled)
        mgr.job_registered.connect(self._on_job_registered)

    def refresh_jobs(self):
        mgr = BackgroundExportManager.get_instance()
        jobs = list(mgr._jobs.values())
        if not jobs:
            self.empty_label.show()
            return
        self.empty_label.hide()

        # Sort jobs: running first, then completed by time descending
        jobs.sort(key=lambda j: (0 if j.is_active else 1, -j.started_at))

        for job in jobs:
            if job.job_id not in self._job_widgets:
                self._create_job_card(job)
            else:
                self._update_job_card(job)

    def _create_job_card(self, job: ExportJob):
        card = QFrame()
        card.setObjectName("jobCard")
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(12, 10, 12, 10)
        c_layout.setSpacing(8)

        # Top row: name + status badge
        top_row = QHBoxLayout()
        name_lbl = QLabel(f"🎬 {job.project_name}")
        name_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #f1f5f9;")
        top_row.addWidget(name_lbl)
        top_row.addStretch()

        badge_lbl = QLabel(self._status_text(job))
        badge_lbl.setStyleSheet(self._status_style(job))
        top_row.addWidget(badge_lbl)
        c_layout.addLayout(top_row)

        # Output path
        out_name = os.path.basename(job.output_path) if job.output_path else "export.mp4"
        file_lbl = QLabel(f"Output: {out_name}")
        file_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        file_lbl.setToolTip(job.output_path)
        c_layout.addWidget(file_lbl)

        # Progress bar
        pbar = QProgressBar()
        pbar.setRange(0, 100)
        pbar.setValue(job.percent)
        pbar.setVisible(job.is_active)
        c_layout.addWidget(pbar)

        # Message & action buttons
        bot_row = QHBoxLayout()
        msg_lbl = QLabel(job.message or "")
        msg_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
        bot_row.addWidget(msg_lbl, 1)

        open_btn = QPushButton("Open Folder")
        open_btn.setObjectName("actionBtn")
        open_btn.setVisible(job.status == "completed")
        open_btn.clicked.connect(lambda _=False, j=job: self._open_folder(j.output_path))
        bot_row.addWidget(open_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.setVisible(job.is_active)
        cancel_btn.clicked.connect(lambda _=False, jid=job.job_id: self._cancel_job(jid))
        bot_row.addWidget(cancel_btn)

        c_layout.addLayout(bot_row)

        # Insert before stretch
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._job_widgets[job.job_id] = {
            "card": card,
            "badge": badge_lbl,
            "pbar": pbar,
            "msg": msg_lbl,
            "open_btn": open_btn,
            "cancel_btn": cancel_btn,
        }

    def _update_job_card(self, job: ExportJob):
        w = self._job_widgets.get(job.job_id)
        if not w:
            return
        w["badge"].setText(self._status_text(job))
        w["badge"].setStyleSheet(self._status_style(job))
        w["pbar"].setValue(job.percent)
        w["pbar"].setVisible(job.is_active)
        w["msg"].setText(job.message or "")
        w["open_btn"].setVisible(job.status == "completed")
        w["cancel_btn"].setVisible(job.is_active)

    def _status_text(self, job: ExportJob) -> str:
        if job.status == "running":
            return f"⚡ {job.percent}%"
        if job.status == "completed":
            return "✓ Completed"
        if job.status == "cancelled":
            return "Cancelled"
        if job.status == "failed":
            return "Failed"
        return job.status.capitalize()

    def _status_style(self, job: ExportJob) -> str:
        if job.status == "running":
            return "color: #34d399; font-weight: 700; font-size: 11px; background: #12362a; border-radius: 6px; padding: 2px 8px;"
        if job.status == "completed":
            return "color: #6ee7d6; font-weight: 700; font-size: 11px; background: #0e2a2c; border-radius: 6px; padding: 2px 8px;"
        if job.status == "cancelled":
            return "color: #94a3b8; font-weight: 600; font-size: 11px; background: #1e293b; border-radius: 6px; padding: 2px 8px;"
        if job.status == "failed":
            return "color: #fca5a5; font-weight: 600; font-size: 11px; background: #271418; border-radius: 6px; padding: 2px 8px;"
        return "color: #94a3b8; font-size: 11px;"

    def _open_folder(self, output_path: str):
        if output_path and os.path.exists(output_path):
            folder = os.path.dirname(output_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        elif output_path:
            folder = os.path.dirname(output_path)
            if os.path.exists(folder):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _cancel_job(self, job_id: str):
        BackgroundExportManager.get_instance().cancel_job(job_id)

    def _on_job_progress(self, job_id: str, percent: int, message: str):
        job = BackgroundExportManager.get_instance().get_job(job_id)
        if job:
            if job_id in self._job_widgets:
                self._update_job_card(job)
            else:
                self.refresh_jobs()

    def _on_job_completed(self, job_id: str, output_path: str):
        self.refresh_jobs()

    def _on_job_failed(self, job_id: str, error: str):
        self.refresh_jobs()

    def _on_job_cancelled(self, job_id: str):
        self.refresh_jobs()

    def _on_job_registered(self, job_id: str):
        self.refresh_jobs()
