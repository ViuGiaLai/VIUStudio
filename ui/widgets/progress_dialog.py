from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QFrame, QScrollArea, QWidget, 
    QGraphicsDropShadowEffect, QPushButton, QProgressDialog,
    QApplication, QSizePolicy
)
import time
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor


class BackgroundableProgressDialog(QProgressDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._background_only = True

    def set_background_only(self, enabled: bool):
        self._background_only = bool(enabled)

    def closeEvent(self, event):
        if self._background_only:
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)


class ExportProgressDialog(QDialog):
    cancel_requested = Signal()
    bg_requested = Signal()
    canceled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exporting Video")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(520)
        self.setStyleSheet("""
            QDialog { background-color: #101826; color: #e6eef9; }
            QLabel { color: #e6eef9; background: transparent; font-size: 13px; line-height: 1.4; }
            QPushButton#exportCancelBtn {
                background-color: #2a181e;
                color: #fca5a5;
                border: 1px solid #5c202d;
                border-radius: 10px;
                padding: 8px 18px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#exportCancelBtn:hover {
                background-color: #3d1c25;
                border-color: #ef4444;
                color: #ffffff;
            }
            QPushButton#exportCancelBtn:disabled {
                background-color: #1c1417;
                color: #855b63;
                border-color: #381a20;
            }
            QPushButton#exportBgBtn {
                background-color: #24364f;
                color: #ffffff;
                border: 1px solid #335171;
                border-radius: 10px;
                padding: 8px 18px;
                font-weight: 700;
                font-size: 12px;
            }
            QPushButton#exportBgBtn:hover {
                background-color: #2d4665;
                border-color: #4575a8;
            }
            QProgressBar {
                border: 1px solid #2a3a50;
                border-radius: 10px;
                text-align: center;
                background-color: #111927;
                color: white;
                min-height: 20px;
                font-size: 12px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: #4ed0b3;
                border-radius: 10px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        self.label = QLabel("Exporting final video...\n\nWaiting to start...", self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("exportCancelBtn")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self.cancel_btn)

        self.bg_btn = QPushButton("Run in background", self)
        self.bg_btn.setObjectName("exportBgBtn")
        self.bg_btn.clicked.connect(self._on_bg_clicked)
        btn_row.addWidget(self.bg_btn)

        layout.addLayout(btn_row)

    def _on_cancel_clicked(self):
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("Cancelling...")
        self.label.setText("Exporting final video...\n\nCancelling export...")
        self.cancel_requested.emit()
        self.canceled.emit()

    def _on_bg_clicked(self):
        self.bg_requested.emit()
        self.hide()

    def setLabelText(self, text: str):
        self.label.setText(str(text or ""))

    def setValue(self, val: int):
        self.progress_bar.setValue(int(val))

    def value(self) -> int:
        return self.progress_bar.value()

    def setRange(self, min_val: int, max_val: int):
        self.progress_bar.setRange(int(min_val), int(max_val))

    def maximum(self) -> int:
        return self.progress_bar.maximum()

    def setMinimumDuration(self, _):
        pass

    def setAutoReset(self, _):
        pass

    def setAutoClose(self, _):
        pass

    def setCancelButtonText(self, text: str):
        self.bg_btn.setText(str(text))

    def closeEvent(self, event):
        self.hide()
        event.ignore()

class StepWidget(QFrame):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setObjectName("stepWidget")
        self.status = "pending"
        self.setStyleSheet("""
            #stepWidget {
                background-color: #11141d;
                border: 1px solid #1e2433;
                border-radius: 8px;
                padding: 6px;
                margin-bottom: 4px;
            }
            QLabel {
                color: #e2e8f0;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Inter', Roboto, sans-serif;
            }
            #stepName {
                font-size: 13px;
                font-weight: 600;
            }
            #stepStatus {
                font-size: 11px;
                font-weight: 600;
            }
            #substageChip {
                background: #1e293b;
                color: #93c5fd;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(6)
        header = QHBoxLayout()
        
        self.indicator = QWidget()
        self.indicator.setFixedSize(8, 8)
        self.indicator.setStyleSheet("background-color: #334155; border-radius: 4px;")
        header.addWidget(self.indicator)
        header.addSpacing(8)
        
        self.name_label = QLabel(name)
        self.name_label.setObjectName("stepName")
        header.addWidget(self.name_label)
        
        self.chip_label = QLabel("")
        self.chip_label.setObjectName("substageChip")
        self.chip_label.hide()
        header.addWidget(self.chip_label)
        
        header.addStretch()
        
        self.status_label = QLabel("Pending")
        self.status_label.setObjectName("stepStatus")
        self.status_label.setFixedWidth(80)
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setStyleSheet("color: #64748b;")
        header.addWidget(self.status_label)
        layout.addLayout(header)

        self.detail_label = QLabel("Waiting for the previous step")
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("color: #718096; font-size: 11px;")
        self.detail_label.hide()
        layout.addWidget(self.detail_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #0b1020; border: none; border-radius: 2px; }
            QProgressBar::chunk { background: #3b82f6; border-radius: 2px; }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Pulse animation for running state
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(800)
        self.pulse_timer.timeout.connect(self._toggle_pulse)
        self._pulse_state = False

    def set_substage_chip(self, text: str):
        if text:
            self.chip_label.setText(str(text).strip())
            self.chip_label.show()
        else:
            self.chip_label.hide()

    def set_status(self, status):
        self.status = status
        if status == "running":
            self.status_label.setText("Running")
            self.status_label.setStyleSheet("color: #60a5fa;")
            self.indicator.setStyleSheet("background-color: #3b82f6; border-radius: 4px;")
            self.setStyleSheet("""
                #stepWidget {
                    background-color: #162035;
                    border: 1px solid #3b82f6;
                    border-radius: 8px;
                    padding: 6px;
                    margin-bottom: 4px;
                }
                QLabel { color: #f8fafc; }
                #stepName { font-size: 13px; font-weight: 600; }
                #stepStatus { font-size: 11px; font-weight: 600; }
            """)
            self.pulse_timer.start()
            self.detail_label.show()
            self.progress_bar.show()
            if self.detail_label.text() in {"Waiting for the previous step", "Starting…"}:
                self.detail_label.setText("In progress…")
        elif status == "done":
            self.status_label.setText("✓ Done")
            self.status_label.setStyleSheet("color: #34d399; font-weight: 600;")
            self.indicator.setStyleSheet("background-color: #10b981; border-radius: 4px;")
            self.setStyleSheet("""
                #stepWidget {
                    background-color: #0d291e;
                    border: 1px solid #165b40;
                    border-radius: 8px;
                    padding: 4px 6px;
                    margin-bottom: 4px;
                }
                QLabel { color: #f8fafc; }
                #stepName { font-size: 13px; font-weight: 600; }
                #stepStatus { font-size: 11px; font-weight: 600; }
            """)
            self.pulse_timer.stop()
            self.chip_label.hide()
            self.detail_label.hide()
            self.progress_bar.hide()
        elif status == "failed":
            self.status_label.setText("Failed")
            self.status_label.setStyleSheet("color: #fca5a5;")
            self.indicator.setStyleSheet("background-color: #ef4444; border-radius: 4px;")
            self.setStyleSheet("""
                #stepWidget {
                    background-color: #2a181e;
                    border: 1px solid #4f202a;
                    border-radius: 8px;
                    padding: 6px;
                    margin-bottom: 4px;
                }
                QLabel { color: #f8fafc; }
                #stepName { font-size: 13px; font-weight: 600; }
                #stepStatus { font-size: 11px; font-weight: 600; }
            """)
            self.pulse_timer.stop()
            self.detail_label.show()
            self.progress_bar.hide()
        elif status == "skipped":
            self.status_label.setText("Skipped")
            self.status_label.setStyleSheet("color: #fde047;")
            self.indicator.setStyleSheet("background-color: #f59e0b; border-radius: 4px;")
            self.pulse_timer.stop()
            self.chip_label.hide()
            self.detail_label.hide()
            self.progress_bar.hide()
        else:
            self.status_label.setText("Pending")
            self.status_label.setStyleSheet("color: #64748b;")
            self.indicator.setStyleSheet("background-color: #334155; border-radius: 4px;")
            self.setStyleSheet("""
                #stepWidget {
                    background-color: #11141d;
                    border: 1px solid #1e2433;
                    border-radius: 8px;
                    padding: 4px 6px;
                    margin-bottom: 4px;
                }
                QLabel { color: #94a3b8; }
                #stepName { font-size: 13px; font-weight: 600; }
                #stepStatus { font-size: 11px; font-weight: 600; }
            """)
            self.chip_label.hide()
            self.progress_bar.hide()
            self.detail_label.hide()

    def set_progress(self, percent=None, detail="", chip=""):
        if detail:
            self.detail_label.setText(str(detail).strip())
            self.detail_label.show()
        if chip:
            self.set_substage_chip(chip)
        self.progress_bar.show()
        if percent is None or int(percent) < 0:
            self.progress_bar.setRange(0, 0)
            self.status_label.setText("Working")
            return
        value = max(0, min(100, int(percent)))
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(value)
        if self.status == "running":
            self.status_label.setText(f"{value}%")

    def set_error(self, detail):
        self.set_status("failed")
        self.detail_label.setText(str(detail or "Unknown error").strip())
        
        
    def _toggle_pulse(self):
        self._pulse_state = not self._pulse_state
        alpha = 255 if self._pulse_state else 120
        self.indicator.setStyleSheet(f"background-color: rgba(59, 130, 246, {alpha}); border-radius: 4px;")

class PipelineProgressDialog(QDialog):
    stop_requested = Signal()
    retry_requested = Signal(str)
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stopped = False
        self._drag_pos = None
        self._smoothed_eta = None
        self._last_failed_step_id = ""
        self._last_error_details = ""
        self.setWindowTitle("VIUStudio AI Pipeline")
        self.setFixedSize(640, 700)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.workflow_start_time = None
        self.total_timer = QTimer(self)
        self.total_timer.setInterval(1000)
        self.total_timer.timeout.connect(self._update_total_time)
        
        self.main_frame = QFrame(self)
        self.main_frame.setObjectName("mainFrame")
        self.main_frame.setFixedSize(620, 680)
        self.main_frame.move(10, 10)
        self.main_frame.setStyleSheet("""
            #mainFrame {
                background-color: #141824;
                border: 1px solid #23293a;
                border-radius: 12px;
            }
        """)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.main_frame.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self.main_frame)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        self.title_label = QLabel("AI Production Pipeline")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        header_layout.addWidget(self.title_label)

        self.overall_percent_label = QLabel("0%")
        self.overall_percent_label.setAlignment(Qt.AlignCenter)
        self.overall_percent_label.setFixedSize(48, 26)
        self.overall_percent_label.setStyleSheet(
            "background:#10243d; color:#7dd3fc; border:1px solid #28527a; "
            "border-radius:13px; font-size:12px; font-weight:700;"
        )
        
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: none;
                color: #94a3b8;
                font-size: 14px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1e2433;
                color: #f8fafc;
            }
        """)
        self.close_btn.clicked.connect(self.hide)
        header_layout.addStretch()
        header_layout.addWidget(self.overall_percent_label)
        header_layout.addWidget(self.close_btn)
        layout.addLayout(header_layout)
        
        self.overall_progress = QProgressBar()
        self.overall_progress.setFixedHeight(8)
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(False)
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                background: #11141d;
                border: 1px solid #1e2433;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.overall_progress)

        self.overall_detail = QLabel("Preparing workflow…")
        self.overall_detail.setStyleSheet("color:#8292aa; font-size:11px;")
        layout.addWidget(self.overall_detail)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 6, 4, 0)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.addStretch()
        
        self.scroll.setWidget(self.scroll_content)
        self.scroll.setStyleSheet("background: transparent;")
        layout.addWidget(self.scroll, 1)
        
        self.steps = {}
        self.step_order = []
        
        self.footer = QLabel("Initializing workflow engine...")
        self.footer.setWordWrap(True)
        self.footer.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(self.footer)

        self.error_panel = QFrame()
        self.error_panel.setObjectName("errorPanel")
        self.error_panel.setStyleSheet("""
            #errorPanel {
                background: #251217;
                border: 1px solid #5c202d;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        error_panel_layout = QVBoxLayout(self.error_panel)
        error_panel_layout.setContentsMargins(10, 8, 10, 8)
        error_panel_layout.setSpacing(8)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.error_label.setStyleSheet("color: #fecaca; font-size: 11px; background: transparent; border: none;")
        error_panel_layout.addWidget(self.error_label)

        error_btns_layout = QHBoxLayout()
        error_btns_layout.setSpacing(8)
        self.retry_btn = QPushButton("Retry Step")
        self.retry_btn.setFixedHeight(26)
        self.retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b1820;
                color: #fca5a5;
                border: 1px solid #6b2635;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #4c1d29;
                border-color: #ef4444;
                color: #ffffff;
            }
        """)
        self.retry_btn.clicked.connect(self._on_retry)

        self.copy_error_btn = QPushButton("Copy Technical Details")
        self.copy_error_btn.setFixedHeight(26)
        self.copy_error_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e2433;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #2a3449;
                color: #ffffff;
            }
        """)
        self.copy_error_btn.clicked.connect(self._on_copy_error)

        self.settings_btn = QPushButton("Open Settings")
        self.settings_btn.setFixedHeight(26)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #1e2433;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #2a3449;
                color: #ffffff;
            }
        """)
        self.settings_btn.clicked.connect(self._on_open_settings)

        error_btns_layout.addWidget(self.retry_btn)
        error_btns_layout.addWidget(self.copy_error_btn)
        error_btns_layout.addWidget(self.settings_btn)
        error_btns_layout.addStretch()
        error_panel_layout.addLayout(error_btns_layout)

        self.error_panel.hide()
        layout.addWidget(self.error_panel)

        self.total_time_label = QLabel("Elapsed 00:00  •  Remaining —")
        self.total_time_label.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(self.total_time_label)

        self.dismiss_btn = QPushButton("Close")
        self.dismiss_btn.setFixedHeight(34)
        self.dismiss_btn.setStyleSheet("""
            QPushButton {
                background-color: #1c2230;
                color: #e2e8f0;
                border: 1px solid #2b354a;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #262e42;
                border-color: #3b82f6;
                color: #ffffff;
            }
        """)
        self.dismiss_btn.clicked.connect(self.hide)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedHeight(34)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #24141a;
                color: #fca5a5;
                border: 1px solid #4a2028;
                border-radius: 6px;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #361a24;
                border-color: #ef4444;
            }
        """)
        self.stop_btn.clicked.connect(self._on_stop)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.stop_btn.setMinimumWidth(160)
        self.dismiss_btn.setMinimumWidth(160)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.dismiss_btn)
        layout.addLayout(btn_row)

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def _set_preview_overlays_suppressed(self, suppressed: bool):
        """Keep top-level video overlays below this non-modal pipeline window."""
        parent = self.parentWidget()
        video_view = getattr(parent, "video_view", None)
        if video_view is None:
            return
        subtitle = getattr(video_view, "subtitle_item", None)
        text_overlay = getattr(video_view, "text_overlay", None)
        if subtitle is not None:
            if hasattr(subtitle, "set_suppressed"):
                subtitle.set_suppressed(suppressed)
            elif hasattr(subtitle, "setVisible"):
                subtitle.setVisible(not suppressed)
        if text_overlay is not None:
            if hasattr(text_overlay, "set_suppressed"):
                text_overlay.set_suppressed(suppressed)
            elif hasattr(text_overlay, "setVisible"):
                text_overlay.setVisible(not suppressed)
        if not suppressed and hasattr(video_view, "_restore_subtitle_overlay"):
            QTimer.singleShot(0, video_view._restore_subtitle_overlay)

    def showEvent(self, event):
        self._set_preview_overlays_suppressed(True)
        super().showEvent(event)

    def add_step(self, step_id, name):
        widget = StepWidget(name)
        self.steps[step_id] = widget
        self.step_order.append(step_id)
        self.scroll_layout.insertWidget(len(self.step_order) - 1, widget)
        return widget

    def start_step(self, step_id):
        if step_id in self.steps:
            self.error_panel.hide()
            if self.workflow_start_time is None:
                self.workflow_start_time = time.monotonic()
                self.total_timer.start()
            self.steps[step_id].set_status("running")
            idx = self.step_order.index(step_id)
            val = int((idx / len(self.step_order)) * 100)
            self.overall_progress.setValue(val)
            self.overall_percent_label.setText(f"{val}%")
            self.overall_detail.setText(
                f"Step {idx + 1} of {len(self.step_order)}  •  {self.steps[step_id].name_label.text()}"
            )
            self.footer.setText(f"Stage {idx+1}/{len(self.step_order)}: {self.steps[step_id].name_label.text()}")

    def update_step_progress(self, step_id, percent=None, detail=""):
        if step_id not in self.steps:
            return
        widget = self.steps[step_id]
        if widget.status != "running":
            self.start_step(step_id)
        widget.set_progress(percent, detail)
        idx = self.step_order.index(step_id)
        stage_fraction = (
            0.0 if percent is None or int(percent) < 0
            else max(0, min(100, int(percent))) / 100.0
        )
        overall = int(((idx + stage_fraction) / max(1, len(self.step_order))) * 100)
        self.overall_progress.setValue(overall)
        self.overall_percent_label.setText(f"{overall}%")
        self.overall_detail.setText(
            f"Step {idx + 1} of {len(self.step_order)}  •  {widget.name_label.text()}"
        )
        if detail:
            self.footer.setText(str(detail).strip())

    def finish_step(self, step_id):
        if step_id in self.steps:
            self.steps[step_id].set_status("done")
            idx = self.step_order.index(step_id)
            val = int(((idx + 1) / len(self.step_order)) * 100)
            self.overall_progress.setValue(val)
            self.overall_percent_label.setText(f"{val}%")

    def fail_step(self, step_id):
        if step_id in self.steps:
            self.steps[step_id].set_status("failed")
            self.footer.setText(f"Error encountered during: {self.steps[step_id].name_label.text()}")
            self.footer.setStyleSheet("color: #FF4444; font-weight: bold; margin-top: 15px;")
            self._stop_total_timer()

    def skip_step(self, step_id):
        if step_id in self.steps:
            self.steps[step_id].set_status("skipped")

    def set_error(self, step_id, reason):
        step = self.steps.get(step_id)
        if step is not None:
            step.set_error(reason)
            step_name = step.name_label.text()
        else:
            step_name = str(step_id or "Current step")
        self._last_failed_step_id = str(step_id or "")
        message = str(reason or "Unknown error").strip()
        self._last_error_details = f"Failed in step: {step_name} (ID: {step_id})\n{message}"
        self.error_label.setText(f"Failed in {step_name}:\n{message}")
        self.error_panel.show()
        self.footer.setText(f"Stopped at: {step_name}")
        self.footer.setStyleSheet("color:#fca5a5; font-size:12px; font-weight:600;")
        self._stop_total_timer()

    def set_completed(self):
        self.stop_btn.hide()
        self.error_panel.hide()
        for step_id in self.step_order:
            widget = self.steps.get(step_id)
            if widget is None:
                continue
            if widget.status == "running":
                widget.set_status("done")
            elif widget.status == "pending":
                widget.set_status("skipped")
        self.overall_progress.setValue(100)
        self.overall_percent_label.setText("100%")
        self.overall_detail.setText("All requested steps completed")
        self.footer.setText("✨ Pipeline execution complete! Video is ready.")
        self.footer.setStyleSheet("color: #00FF88; font-weight: bold; font-size: 14px; margin-top: 15px;")
        self._stop_total_timer()

    def _on_retry(self):
        self.retry_requested.emit(self._last_failed_step_id or "")

    def _on_copy_error(self):
        details = self._last_error_details or self.error_label.text()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(details)
        orig_text = self.copy_error_btn.text()
        self.copy_error_btn.setText("✓ Copied!")
        QTimer.singleShot(2000, lambda: self.copy_error_btn.setText(orig_text))

    def _on_open_settings(self):
        self.settings_requested.emit()

    def _update_total_time(self):
        if self.workflow_start_time is None:
            return
        elapsed = max(0.1, time.monotonic() - self.workflow_start_time)
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        hours, mins = divmod(mins, 60)
        elapsed_text = (
            f"{hours}:{mins:02d}:{secs:02d}" if hours > 0
            else f"{mins:02d}:{secs:02d}"
        )
        value = self.overall_progress.value()
        if value >= 100:
            eta_text = "Done"
        elif value < 3:
            eta_text = "Calculating…"
        else:
            raw_remaining = (elapsed / value) * (100 - value)
            if self._smoothed_eta is None:
                self._smoothed_eta = raw_remaining
            else:
                self._smoothed_eta = (0.7 * self._smoothed_eta) + (0.3 * raw_remaining)
            rem_sec = int(self._smoothed_eta)
            r_hrs, r_rem = divmod(rem_sec, 3600)
            r_mins, r_secs = divmod(r_rem, 60)
            if r_hrs > 0:
                eta_text = f"{r_hrs}:{r_mins:02d}:{r_secs:02d}"
            else:
                eta_text = f"{r_mins:02d}:{r_secs:02d}"
        self.total_time_label.setText(f"Elapsed {elapsed_text}  •  Remaining {eta_text}")

    def _stop_total_timer(self):
        if self.total_timer.isActive():
            self.total_timer.stop()
        if self.workflow_start_time is None:
            return
        elapsed = max(0.1, time.monotonic() - self.workflow_start_time)
        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        hours, mins = divmod(mins, 60)
        elapsed_text = (
            f"{hours}:{mins:02d}:{secs:02d}" if hours > 0
            else f"{mins:02d}:{secs:02d}"
        )
        remaining_text = "00:00" if self.overall_progress.value() >= 100 else "—"
        self.total_time_label.setText(f"Elapsed {elapsed_text}  •  Remaining {remaining_text}")
        self.workflow_start_time = None
        self._smoothed_eta = None

    def _on_stop(self):
        self._stopped = True
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Stopping...")
        self.footer.setText("Stopping pipeline...")
        self.footer.setStyleSheet("color: #FF6B6B; font-weight: bold; font-size: 14px; margin-top: 15px;")
        self.stop_requested.emit()

    def cancel_stop_request(self):
        self._stopped = False
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("Stop")
        self.footer.setText("Pipeline is still running.")
        self.footer.setStyleSheet("color: #888; font-size: 13px; margin-top: 15px;")

    def hideEvent(self, event):
        self._stop_total_timer()
        super().hideEvent(event)
        self._set_preview_overlays_suppressed(False)

    # Drag support for frameless window
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(self.pos() + event.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class MiniProgressStatusBar(QFrame):
    """A sleek, persistent mini progress bar docked at the workspace footer.

    Displays real-time pipeline status, substage chips, progress percent,
    and ETA, allowing users to monitor background jobs or cancel them without
    keeping the full dialog open.
    """
    show_dialog_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("miniProgressStatusBar")
        self.setFixedHeight(34)
        self.setStyleSheet("""
            #miniProgressStatusBar {
                background-color: #0b0f17;
                border-top: 1px solid #1a2333;
                border-radius: 6px;
                padding: 0 10px;
            }
            QLabel {
                color: #94a3b8;
                font-size: 11px;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Inter', Roboto, sans-serif;
            }
            #miniBadge {
                font-size: 10px;
                font-weight: 700;
                padding: 2px 7px;
                border-radius: 4px;
            }
            #miniPercent {
                color: #38bdf8;
                font-weight: 700;
                font-size: 11px;
            }
            #miniDetail {
                color: #e2e8f0;
                font-weight: 500;
            }
            #miniEta {
                color: #64748b;
                font-size: 11px;
            }
            QProgressBar {
                background: #141a26;
                border: 1px solid #232d40;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #10b981);
                border-radius: 2px;
            }
            QPushButton {
                background-color: #1a2233;
                color: #cbd5e1;
                border: 1px solid #2c384e;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 600;
                padding: 3px 10px;
            }
            QPushButton:hover {
                background-color: #26334d;
                color: #ffffff;
            }
            #miniStopBtn {
                background-color: #2b141a;
                color: #fca5a5;
                border: 1px solid #52202c;
            }
            #miniStopBtn:hover {
                background-color: #3d1b24;
                border-color: #ef4444;
                color: #ffffff;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(10)

        # Status badge
        self.badge = QLabel("IDLE")
        self.badge.setObjectName("miniBadge")
        layout.addWidget(self.badge)

        # Workflow Title & Substage Chip
        self.workflow_label = QLabel("Pipeline")
        self.workflow_label.setStyleSheet("color: #f8fafc; font-weight: 600; font-size: 11px;")
        layout.addWidget(self.workflow_label)

        self.chip_label = QLabel("")
        self.chip_label.setStyleSheet("background: #1e293b; color: #93c5fd; border: 1px solid #334155; border-radius: 4px; padding: 1px 5px; font-size: 9px; font-weight: 600;")
        self.chip_label.hide()
        layout.addWidget(self.chip_label)

        # Detail text
        self.detail_label = QLabel("Ready")
        self.detail_label.setObjectName("miniDetail")
        self.detail_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.detail_label, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedSize(130, 6)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # Percent
        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("miniPercent")
        self.percent_label.setFixedWidth(34)
        self.percent_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.percent_label)

        # ETA / Elapsed
        self.eta_label = QLabel("—")
        self.eta_label.setObjectName("miniEta")
        layout.addWidget(self.eta_label)

        # Expand / Details button
        self.show_btn = QPushButton("Details ↗")
        self.show_btn.setFixedHeight(24)
        self.show_btn.clicked.connect(self.show_dialog_requested.emit)
        layout.addWidget(self.show_btn)

        # Stop button
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("miniStopBtn")
        self.stop_btn.setFixedHeight(24)
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        self.stop_btn.hide()
        layout.addWidget(self.stop_btn)

        self._update_badge("idle")

    def _update_badge(self, status: str):
        st = status.lower()
        if st == "running":
            self.badge.setText("RUNNING")
            self.badge.setStyleSheet("background: #152b47; color: #60a5fa; border: 1px solid #2563eb;")
            self.stop_btn.show()
        elif st == "done":
            self.badge.setText("DONE")
            self.badge.setStyleSheet("background: #0f382c; color: #34d399; border: 1px solid #059669;")
            self.stop_btn.hide()
        elif st in ("failed", "error"):
            self.badge.setText("ERROR")
            self.badge.setStyleSheet("background: #38161d; color: #f87171; border: 1px solid #dc2626;")
            self.stop_btn.hide()
        elif st == "stopped":
            self.badge.setText("STOPPED")
            self.badge.setStyleSheet("background: #382715; color: #fbbf24; border: 1px solid #d97706;")
            self.stop_btn.hide()
        else:
            self.badge.setText("IDLE")
            self.badge.setStyleSheet("background: #141924; color: #64748b; border: 1px solid #252e3d;")
            self.stop_btn.hide()

    def set_active(self, workflow_name: str = "AI Pipeline", detail: str = "Processing…"):
        self.workflow_label.setText(workflow_name)
        self.detail_label.setText(detail)
        self.chip_label.hide()
        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")
        self.eta_label.setText("—")
        self._update_badge("running")
        self.show()

    def set_progress(self, percent=None, detail: str = "", chip: str = "", eta_text: str = ""):
        if percent is not None and int(percent) >= 0:
            val = max(0, min(100, int(percent)))
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(val)
            self.percent_label.setText(f"{val}%")
        else:
            self.progress_bar.setRange(0, 0)
            self.percent_label.setText("…")
        if detail:
            self.detail_label.setText(str(detail).strip())
        if chip:
            self.chip_label.setText(str(chip).strip())
            self.chip_label.show()
        else:
            self.chip_label.hide()
        if eta_text:
            self.eta_label.setText(str(eta_text).strip())

    def set_done(self, message: str = "Pipeline completed"):
        self._update_badge("done")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.percent_label.setText("100%")
        self.detail_label.setText(message)
        self.eta_label.setText("✓")
        self.chip_label.hide()

    def set_error(self, message: str = "Pipeline encountered an error"):
        self._update_badge("error")
        self.detail_label.setText(str(message).strip())
        self.chip_label.hide()

    def set_stopped(self):
        self._update_badge("stopped")
        self.detail_label.setText("Execution cancelled")
        self.chip_label.hide()

    def set_idle(self):
        self._update_badge("idle")
        self.detail_label.setText("Ready")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")
        self.eta_label.setText("—")
        self.chip_label.hide()
