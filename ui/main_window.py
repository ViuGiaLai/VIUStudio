import sys
import os
from PySide6.QtWidgets import (
    QApplication, QMainWindow)
from PySide6.QtCore import Qt, QTimer, QSettings, Signal
from PySide6.QtGui import QIcon

APP_PATH = os.path.join(os.path.dirname(__file__), '..', 'app')
if APP_PATH not in sys.path:
    sys.path.append(APP_PATH)

from services import GUIProjectBridge, ProjectService, VoiceCatalogService
from controllers import OcrController, PipelineController, PreviewController, ProjectController, SubtitleController, VideoFilterController
from features.timeline_selection import TimelineSelectionMixin
from features.visual_layer_editor import VisualLayerEditorMixin
from features.voice_catalog import VoiceCatalogMixin
from features.runtime_media import RuntimeMediaMixin
from features.window_ui import WindowUiMixin
from features.speaker_voice import SpeakerVoiceMixin
from features.filter_subtitle_style import FilterSubtitleStyleMixin
from features.project_state import ProjectStateMixin
from features.preview_configuration import PreviewConfigurationMixin
from features.segment_editor import SegmentEditorMixin
from features.timeline_editing import TimelineEditingMixin
from features.voice_subtitle_preview import VoiceSubtitlePreviewMixin
from features.workflow_actions import WorkflowActionsMixin
from features.model_settings import ModelSettingsMixin
from features.update_feature import UpdateFeatureMixin
from features.auto_recap_feature import AutoRecapFeatureMixin
from features.pipeline_lifecycle import PipelineLifecycleMixin
from features.multi_video_timeline import MultiVideoTimelineMixin
from utils.bootstrap_media_backend import BootstrapMediaBackend
from runtime_paths import asset_path, workspace_root
from runtime_profile import is_remote_profile


_REIMAGINED_THEME = """
/* ── VIUStudio Studio Dark Pro Theme: Obsidian Canvas + Electric Indigo + Emerald CTA ── */
QMainWindow, QWidget#centralWidget {
    background: #080b11;
    color: #f1f5f9;
}

/* ── Navigation Rail ────────────────────────────────────────────────────────── */
QFrame#navigationRail {
    background: #0d121c;
    border: 1px solid #1a2333;
    border-radius: 14px;
}
QLabel#navigationMark {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
    color: #ffffff;
    border-radius: 12px;
    font-size: 20px;
    font-weight: 900;
}
QLabel#navigationBrand {
    color: #cbd5e1;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1.2px;
}
QFrame#navigationDivider {
    background: #1e293b;
    border: none;
    height: 1px;
}
QToolButton#navigationButton {
    background: #101622;
    color: #94a3b8;
    border: 1px solid #1a2436;
    border-radius: 9px;
    padding: 5px 2px;
    font-size: 10px;
    font-weight: 700;
}
QToolButton#navigationButton:hover {
    background: #182236;
    color: #f8fafc;
    border-color: #3b82f6;
}
QToolButton#navigationButton:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #4f46e5);
    color: #ffffff;
    border: 1px solid #818cf8;
}
QToolButton#navigationButton:disabled {
    background: #090d15;
    color: #475569;
    border: 1px solid #131a26;
}
QToolButton#navigationUtilityButton {
    background: #0d121c;
    color: #94a3b8;
    border: 1px solid #182030;
    border-radius: 9px;
    padding: 4px 2px;
    font-size: 10px;
    font-weight: 700;
}
QToolButton#navigationUtilityButton:hover {
    background: #182236;
    color: #f8fafc;
    border-color: #3b82f6;
}

/* ── Command Header ─────────────────────────────────────────────────────────── */
QFrame#commandHeader {
    background: #0d121c;
    border: 1px solid #1a2333;
    border-radius: 14px;
}
QLabel#commandContext {
    color: #818cf8;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#commandProject {
    color: #f8fafc;
    font-size: 14px;
    font-weight: 800;
}
QPushButton#headerActionBtn {
    background: #141c2c;
    border: 1px solid #233045;
    border-radius: 10px;
    color: #e2e8f0;
    font-size: 11px;
    font-weight: 700;
    padding: 0px 14px;
}
QPushButton#headerActionBtn[accent="true"] {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f59e0b, stop:1 #d97706);
    color: #ffffff;
    border: 1px solid #fbbf24;
    font-weight: 800;
}
QPushButton#headerActionBtn:hover {
    background: #1c273c;
    border-color: #3b82f6;
    color: #ffffff;
}
QPushButton#headerActionBtn[accent="true"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fbbf24, stop:1 #f59e0b);
    border-color: #fde68a;
    color: #ffffff;
}
QPushButton#headerNavBtn, QPushButton#headerMenuBtn {
    background: transparent;
    color: #94a3b8;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0px 12px;
    font-size: 11px;
    font-weight: 650;
}
QPushButton#headerNavBtn:hover, QPushButton#headerMenuBtn:hover {
    background: #151d2b;
    color: #f8fafc;
    border-color: #24334a;
}

/* ── Workspaces & Panels ────────────────────────────────────────────────────── */
QScrollArea#leftPanelArea {
    background: #0d121c;
    border: 1px solid #1a2333;
    border-radius: 14px;
}
QWidget#leftPanelContainer { background: #0d121c; }
QWidget#rightPanel {
    background: #080b11;
    border: 1px solid #1a2333;
    border-radius: 14px;
}

/* ── Cards & Inspectors ─────────────────────────────────────────────────────── */
QFrame#heroCard, QFrame#statusCard, QFrame#sideInfoCard, QFrame#audioSourcePanel {
    background-color: #121826;
    border: 1px solid #1e283a;
    border-radius: 12px;
}
QFrame#subtitleInspectorHandle {
    background-color: #121826;
    border: 1px solid #1e283a;
    border-left: none;
    border-top-right-radius: 12px;
    border-bottom-right-radius: 12px;
}
QFrame#segmentInspectorCard {
    background-color: #121826;
    border: 1px solid #1e283a;
    border-radius: 10px;
}

/* ── Preview Transport & Control Bar ────────────────────────────────────────── */
QFrame#previewTransportBar {
    background: #0d121c;
    border: 1px solid #1a2333;
    border-radius: 12px;
}
QLabel#inspectorStatusPill {
    background: #064e3b;
    border: 1px solid #059669;
    border-radius: 8px;
    color: #6ee7b7;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1px;
    padding: 3px 8px;
}
QLabel#previewTransportBar QLabel {
    color: #94a3b8;
    font-size: 10px;
    font-weight: 700;
}
QPushButton#previewTransportIconBtn {
    background: #141c2c;
    border: 1px solid #233045;
    border-radius: 8px;
    padding: 0;
}
QPushButton#previewTransportIconBtn:hover {
    background: #1c273c;
    border-color: #6366f1;
    color: #ffffff;
}
QPushButton#previewTransportIconBtn:pressed {
    background: #4f46e5;
    border-color: #818cf8;
}
QPushButton#previewToolBtn {
    background-color: #121826;
    color: #cbd5e1;
    border: 1px solid #1e283a;
    border-radius: 6px;
    padding: 0px 8px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#previewToolBtn:hover {
    background-color: #1c273c;
    color: #ffffff;
    border-color: #6366f1;
}
QPushButton#previewToolBtn:pressed {
    background-color: #4f46e5;
    border-color: #818cf8;
}
QPushButton#previewToolBtn[toolKind="ocr"]:checked {
    background-color: #4338ca;
    color: #ffffff;
    border-color: #818cf8;
}
QComboBox#previewSpeedCombo {
    min-width: 66px;
    max-width: 66px;
    min-height: 26px;
    background-color: #121826;
    border: 1px solid #1e283a;
    border-radius: 6px;
    color: #e2e8f0;
}
QLabel#previewTimeLabel {
    background: #064e3b;
    border: 1px solid #059669;
    border-radius: 6px;
    color: #34d399;
    font-weight: 800;
    padding: 3px 8px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
}
QLabel#previewSectionTitle {
    color: #f8fafc;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.2px;
}
QLabel#sectionTitle {
    color: #818cf8;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.2px;
}
QLabel#previewStatePill {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    color: #94a3b8;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: .8px;
    padding: 3px 8px;
}
QPushButton#previewScaleBtn {
    background: #151f30;
    border: 1px solid #283950;
    border-radius: 8px;
    color: #38bdf8;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: .8px;
    padding: 3px 8px;
}
QPushButton#previewScaleBtn:hover {
    background: #1e2f47;
    color: #7dd3fc;
    border-color: #38bdf8;
}
QPushButton#workflowTabBtn {
    min-height: 36px;
    background-color: #121826;
    color: #94a3b8;
    border: 1px solid #1e283a;
    border-radius: 8px;
}
QPushButton#workflowTabBtn:hover {
    background-color: #1a2334;
    border-color: #334155;
    color: #f1f5f9;
}
QPushButton#workflowTabBtn:checked {
    background-color: #1e2548;
    color: #818cf8;
    border-color: #6366f1;
}

/* ── Primary Generate CTA ────────────────────────────────────────────────────── */
QPushButton#mainActionBtn, QToolButton#mainActionBtn {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
    color: #ffffff;
    border: 1px solid #34d399;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 800;
    padding: 0px 18px;
    letter-spacing: 0.4px;
}
QPushButton#mainActionBtn:hover, QToolButton#mainActionBtn:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #34d399, stop:1 #10b981);
    border-color: #6ee7b7;
}
QPushButton#mainActionBtn:pressed, QToolButton#mainActionBtn:pressed {
    background-color: #047857;
    border-color: #059669;
}
QPushButton#mainActionBtn:disabled, QToolButton#mainActionBtn:disabled {
    background-color: #112620;
    color: #3b5f54;
    border-color: #1b3830;
}

/* ── Subtitle Inspector Action Buttons ───────────────────────────────────────── */
QPushButton#subtitleInspectorAction {
    background-color: #131c2b;
    color: #e2e8f0;
    border: 1px solid #223246;
    border-radius: 5px;
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#subtitleInspectorAction:hover {
    background-color: #1c2a3e;
    color: #ffffff;
    border-color: #38bdf8;
}
QPushButton#subtitleInspectorAction:pressed {
    background-color: #0e1622;
    border-color: #0284c7;
}
QPushButton#subtitleInspectorDangerAction {
    background-color: #1f1216;
    color: #f87171;
    border: 1px solid #451b24;
    border-radius: 5px;
    padding: 3px 6px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#subtitleInspectorDangerAction:hover {
    background-color: #2e161c;
    color: #fca5a5;
    border-color: #ef4444;
}
QPushButton#subtitleInspectorDangerAction:pressed {
    background-color: #140b0e;
    border-color: #b91c1c;
}

/* ── General Buttons ─────────────────────────────────────────────────────────── */
QPushButton {
    background-color: #141c2c;
    color: #cbd5e1;
    border: 1px solid #233045;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 11px;
}
QPushButton:hover {
    background-color: #1c273c;
    border-color: #3b82f6;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #0f1724;
    border-color: #1d4ed8;
}
QPushButton:disabled {
    background-color: #0b0f17;
    color: #475569;
    border-color: #172030;
}

/* ── Inputs & Editors ────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #090e17;
    border: 1px solid #1e283a;
    border-radius: 8px;
    color: #f1f5f9;
    padding: 7px 10px;
    selection-background-color: #4f46e5;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #6366f1;
    background-color: #0d1422;
}
QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {
    background-color: #070a10;
    color: #475569;
    border: 1px solid #151d2a;
}
QTextEdit#segmentInspectorEditor {
    background-color: #090e17;
    border: 1px solid #1e283a;
    border-radius: 8px;
    padding: 10px 12px;
    color: #f1f5f9;
}
QTextEdit#segmentInspectorEditor:focus {
    border: 1px solid #6366f1;
    background-color: #0d1422;
}

/* ── Sliders ─────────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #1e283a;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #6366f1;
    border: 2px solid #818cf8;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:hover {
    background: #818cf8;
    border-color: #a5b4fc;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4f46e5, stop:1 #6366f1);
    border-radius: 2px;
}

/* ── Scrollbars ──────────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    border: none;
    background: #080b11;
    width: 7px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #1e283a;
    min-height: 24px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover { background: #334155; }
QScrollBar:horizontal {
    border: none;
    background: #080b11;
    height: 7px;
}
QScrollBar::handle:horizontal {
    background: #1e283a;
    min-width: 24px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover { background: #334155; }

/* ── Tooltip ─────────────────────────────────────────────────────────────────── */
QToolTip {
    background: #111724;
    color: #f1f5f9;
    border: 1px solid #24344d;
    border-radius: 6px;
    padding: 5px 9px;
    font-size: 11px;
}
"""

def _default_asr_engine() -> str:
    return "sensevoice"


class VideoTranslatorGUI(PipelineLifecycleMixin, MultiVideoTimelineMixin, AutoRecapFeatureMixin, ModelSettingsMixin, UpdateFeatureMixin, WorkflowActionsMixin, VoiceSubtitlePreviewMixin, TimelineEditingMixin, SegmentEditorMixin, PreviewConfigurationMixin, ProjectStateMixin, FilterSubtitleStyleMixin, SpeakerVoiceMixin, WindowUiMixin, RuntimeMediaMixin, VoiceCatalogMixin, VisualLayerEditorMixin, TimelineSelectionMixin, QMainWindow):
    VOICE_ENTRY_ID_ROLE = Qt.UserRole + 1
    runtime_log_received = Signal(str)
    subtitle_ass_ready = Signal(int, str, str, object)

    def __init__(self):
        super().__init__()
        self._current_video_path = ""
        title = "VIUStudio Video Translator"
        if is_remote_profile():
            title += " (Remote)"
        self.setWindowTitle(title)
        self.settings = QSettings("VIUStudio", "VideoTranslatorGUI")
        self.setAcceptDrops(True)
        self.logo_path = asset_path("viustudio.png")
        if os.path.exists(self.logo_path):
            self.setWindowIcon(QIcon(self.logo_path))
        self.setWindowFlag(Qt.FramelessWindowHint)

        # Start maximized, but keep the window genuinely resizable.  Locking
        # it to the first monitor's pixel size prevented Qt from adapting the
        # layout when users moved between laptop/desktop displays or changed
        # DPI scaling.
        self.setWindowState(Qt.WindowMaximized)
        self.setMinimumSize(1024, 640)
        self._responsive_layout_pending = False
        self._responsive_layout_mode = "desktop"
        self._initial_layout_finalized = False

        # Stylesheet for Premium Dark Mode
        self.setStyleSheet("""
            /* ── Base ─────────────────────────────────────────────── */
            QMainWindow {
                background-color: #0b1118;
            }
            QWidget {
                color: #cdd9e5;
                font-family: 'Segoe UI', 'Inter', Arial, sans-serif;
            }
            #centralWidget {
                background-color: #0b1118;
            }

            /* ── Panels ───────────────────────────────────────────── */
            #leftPanelArea {
                background-color: #0e1520;
                border-right: 1px solid #1a2536;
            }
            #leftPanelContainer {
                background-color: #0e1520;
            }
            #rightPanel {
                background-color: #0b1118;
            }

            /* ── Cards ─────────────────────────────────────────────── */
            QFrame#heroCard, QFrame#statusCard, QFrame#sideInfoCard {
                background-color: #0f1c2b;
                border: 1px solid #1e3047;
                border-radius: 12px;
            }
            QFrame#audioSourcePanel {
                background-color: #0f1c2b;
                border: 1px solid #1e3047;
                border-radius: 10px;
            }
            QFrame#subtitleInspectorHandle {
                background-color: #0f1c2b;
                border: 1px solid #1e3047;
                border-left: none;
                border-top-right-radius: 12px;
                border-bottom-right-radius: 12px;
            }

            /* ── Group boxes ─────────────────────────────────────── */
            QGroupBox {
                border: none;
                border-radius: 0px;
                margin-top: 0px;
                font-weight: 700;
                color: #e0eaf4;
                background-color: transparent;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #4da6e8;
            }

            /* ── Typography ──────────────────────────────────────── */
            QLabel#heroTitle {
                font-size: 19px;
                font-weight: 700;
                color: #eaf4ff;
                letter-spacing: 0.2px;
            }
            QLabel#statusHeadline {
                font-size: 14px;
                font-weight: 700;
                color: #eaf4ff;
            }
            QLabel#sectionTitle {
                font-size: 11px;
                font-weight: 700;
                color: #4da6e8;
                letter-spacing: 0.8px;
                text-transform: uppercase;
            }
            QLabel#heroBody, QLabel#statusBody, QLabel#helperLabel, QLabel#previewContextLabel {
                color: #7a8fa8;
                line-height: 1.45em;
            }
            QLabel#helperLabel[filterModified="true"] {
                color: #4da6e8;
                font-weight: 700;
            }
            QLabel#audioSourceTitle {
                color: #eaf4ff;
                font-weight: 700;
            }
            QLabel {
                background: transparent;
                color: #c2cfe0;
                font-size: 12px;
            }

            /* ── Chips / Pills ───────────────────────────────────── */
            QLabel#timingChip {
                background-color: #0c1624;
                color: #38bdf8;
                border: 1px solid #1a2d46;
                border-radius: 5px;
                padding: 2px 7px;
                font-size: 11px;
                font-weight: 600;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            }
            QLabel#durationChip {
                background-color: #141f2e;
                color: #94a3b8;
                border: 1px solid #233346;
                border-radius: 5px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 600;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
            }
            QLabel#statusPill {
                background-color: #0e2235;
                color: #6ec6f5;
                border: 1px solid #1e4a6a;
                border-radius: 999px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: 700;
            }
            QLabel#statusChip {
                background-color: #131e2e;
                color: #c8d6e6;
                border: 1px solid #253a54;
                border-radius: 999px;
                padding: 3px 10px;
                font-size: 10px;
                font-weight: 600;
            }
            QLabel#statusChip[state="ok"] {
                background-color: #0e2a1e;
                color: #7de8b0;
                border: 1px solid #1e6445;
            }
            QLabel#statusChip[state="running"] {
                background-color: #2a1f08;
                color: #ffd97a;
                border: 1px solid #7a5518;
            }
            QLabel#statusChip[state="na"] {
                background-color: #131e2e;
                color: #7a8fa8;
                border: 1px solid #1e3047;
            }
            QLabel#statusChip[state="pending"] {
                background-color: #131e2e;
                color: #c8d6e6;
                border: 1px solid #253a54;
            }

            /* ── Buttons ─────────────────────────────────────────── */
            QPushButton {
                background-color: #162130;
                color: #c2cfe0;
                border: 1px solid #243a55;
                border-radius: 8px;
                padding: 7px 14px;
                font-weight: 600;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #1c2d42;
                border-color: #3a6090;
                color: #e0eaf4;
            }
            QPushButton:pressed {
                background-color: #122030;
                border-color: #2f5078;
            }
            QPushButton:disabled {
                background-color: #0e1824;
                color: #3d5068;
                border-color: #1a2a3a;
            }

            /* Subtitle Inspector — clean, reliable five-action toolbar */
            QPushButton#subtitleInspectorAction {
                background-color: #131c2b;
                color: #e2e8f0;
                border: 1px solid #223246;
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#subtitleInspectorAction:hover {
                background-color: #1c2a3e;
                color: #ffffff;
                border-color: #38bdf8;
            }
            QPushButton#subtitleInspectorAction:pressed {
                background-color: #0e1622;
                border-color: #0284c7;
            }
            QPushButton#subtitleInspectorDangerAction {
                background-color: #1f1216;
                color: #f87171;
                border: 1px solid #451b24;
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#subtitleInspectorDangerAction:hover {
                background-color: #2e161c;
                color: #fca5a5;
                border-color: #ef4444;
            }
            QPushButton#subtitleInspectorDangerAction:pressed {
                background-color: #140b0e;
                border-color: #b91c1c;
            }
            QPushButton#subtitleInspectorAction:disabled,
            QPushButton#subtitleInspectorDangerAction:disabled {
                background-color: #0e1522;
                color: #475569;
                border-color: #182230;
            }
            QPushButton#subtitleHighlightBtn {
                background-color: #121c2d;
                color: #64748b;
                border: 1px solid #1e2c40;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 12px;
            }
            QPushButton#subtitleHighlightBtn:enabled {
                background-color: #1e1b4b;
                color: #c7d2fe;
                border-color: #4338ca;
            }
            QPushButton#subtitleHighlightBtn:enabled:hover {
                background-color: #312e81;
                color: #ffffff;
                border-color: #6366f1;
            }
            QTextEdit#segmentInspectorEditor {
                background-color: #080d15;
                color: #f8fafc;
                border: 1px solid #233246;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
                selection-background-color: #4338ca;
                selection-color: #ffffff;
            }
            QTextEdit#segmentInspectorEditor:focus {
                border-color: #6366f1;
            }

            /* Generate — primary CTA */
            QPushButton#mainActionBtn, QToolButton#mainActionBtn {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #36d0ad, stop:1 #22a889);
                color: #061511;
                border: 1px solid #48dfbd;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 800;
                padding: 0px 18px;
                letter-spacing: 0.4px;
            }
            QPushButton#mainActionBtn:hover, QToolButton#mainActionBtn:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #50e2c0, stop:1 #2fbd9b);
                border-color: #7af0d2;
            }
            QPushButton#mainActionBtn:pressed, QToolButton#mainActionBtn:pressed {
                background-color: #1d9478;
                border-color: #1d9478;
            }
            QPushButton#mainActionBtn:disabled, QToolButton#mainActionBtn:disabled {
                background-color: #17352f;
                color: #57766f;
                border-color: #214b42;
            }
            QToolButton#mainActionBtn::menu-indicator { image: none; width: 0px; }

            /* Header actions */
            QPushButton#headerActionBtn {
                background-color: #142338;
                color: #d5e5f5;
                border: 1px solid #2d4b6b;
                border-radius: 10px;
                font-size: 12px;
                font-weight: 700;
                padding: 0px 14px;
            }
            QPushButton#headerActionBtn[accent="true"] {
                background-color: #15304a;
                color: #9fd7ff;
                border-color: #2d6f9d;
            }
            QPushButton#headerActionBtn:hover,
            QPushButton#headerActionBtn[accent="true"]:hover {
                background-color: #1c3a57;
                border-color: #4b97ca;
                color: #f2f8ff;
            }
            QPushButton#headerActionBtn:pressed { background-color: #10283f; }
            QPushButton#headerActionBtn:disabled {
                background-color: #101b29;
                color: #52657a;
                border-color: #1c2d40;
            }

            /* Header navigation and overflow stay visually quieter. */
            QPushButton#headerNavBtn, QPushButton#headerMenuBtn {
                background-color: transparent;
                color: #9eb1c7;
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 0px 12px;
                font-size: 12px;
                font-weight: 650;
            }
            QPushButton#headerNavBtn:hover, QPushButton#headerMenuBtn:hover {
                background-color: #15253a;
                color: #e9f2fb;
                border-color: #29435f;
            }
            QPushButton#headerNavBtn:pressed, QPushButton#headerMenuBtn:pressed {
                background-color: #102033;
            }
            QPushButton#headerMenuBtn::menu-indicator { image: none; width: 0px; }

            QPushButton#secondaryActionBtn {
                background-color: #142338;
                color: #c8d8e8;
                border: 1px solid #29445f;
                border-radius: 9px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#secondaryActionBtn:hover {
                background-color: #1a3049;
                border-color: #427ba8;
                color: #eef7ff;
            }

            QPushButton#titleBarButton, QPushButton#titleBarCloseButton {
                background-color: transparent;
                color: #788ba2;
                border: none;
                border-radius: 8px;
                padding: 0px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#titleBarButton:hover {
                background-color: #17263a;
                color: #f1f6fb;
            }
            QPushButton#titleBarCloseButton:hover {
                background-color: #d94b5b;
                color: #ffffff;
            }

            /* Compact preview transport and editing tools */
            QFrame#previewTransportBar {
                background-color: #0c1725;
                border: 1px solid #1d3148;
                border-radius: 10px;
            }
            QFrame#previewTransportSeparator {
                background-color: #22384f;
                border: none;
                margin-top: 5px;
                margin-bottom: 5px;
            }
            QPushButton#previewTransportIconBtn {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0px;
            }
            QPushButton#previewTransportIconBtn:hover {
                background-color: #172a40;
                border-color: #315578;
            }
            QPushButton#previewTransportIconBtn:pressed {
                background-color: #0f2236;
                border-color: #3b719e;
            }
            QPushButton#previewTransportIconBtn:disabled {
                background-color: transparent;
                border-color: transparent;
            }
            QPushButton#previewToolBtn {
                background-color: #111f30;
                color: #b8c9da;
                border: 1px solid #263d57;
                border-radius: 4px;
                padding: 0px 6px;
                font-size: 11px;
                font-weight: 650;
            }
            QPushButton#previewToolBtn:hover {
                background-color: #19304a;
                color: #eef7ff;
                border-color: #4077a5;
            }
            QPushButton#previewToolBtn:pressed {
                background-color: #10263b;
                border-color: #4b91c5;
            }
            QPushButton#previewToolBtn[toolKind="ocr"]:checked {
                background-color: #3b2557;
                color: #f1ddff;
                border-color: #a855f7;
            }
            QPushButton#previewToolBtn:disabled {
                background-color: #0e1926;
                color: #46596d;
                border-color: #192a3c;
            }
            QLabel#previewSpeedLabel {
                color: #72879e;
                font-size: 10px;
                font-weight: 700;
            }
            QComboBox#previewSpeedCombo {
                background-color: #111f30;
                color: #d7e5f2;
                border: 1px solid #29445f;
                border-radius: 4px;
                padding: 0px 4px;
                font-size: 11px;
                font-weight: 700;
            }
            QComboBox#previewSpeedCombo:hover {
                background-color: #172b42;
                border-color: #4077a5;
            }
            QLabel#previewTimeLabel {
                background-color: #0e282a;
                color: #6ee7d6;
                border: 1px solid #205052;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                font-weight: 800;
            }

            /* Workflow tab buttons */
            QPushButton#workflowTabBtn {
                background-color: #121f30;
                color: #7a8fa8;
                border: 1px solid #1e3047;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
            QPushButton#workflowTabBtn:hover {
                background-color: #182840;
                border-color: #3570a0;
                color: #a8c8e0;
            }
            QPushButton#workflowTabBtn:checked {
                background-color: #1a3550;
                color: #eaf4ff;
                border-color: #3a90d0;
            }

            /* Inspector handle button */
            QPushButton#subtitleInspectorHandleBtn {
                background-color: #132031;
                color: #4da6e8;
                border: 1px solid #1e3d58;
                border-right: none;
                border-top-left-radius: 999px;
                border-bottom-left-radius: 999px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                font-size: 18px;
                font-weight: 900;
                padding: 0px;
            }
            QPushButton#subtitleInspectorHandleBtn:hover {
                background-color: #1a2d44;
                border-color: #3a80c0;
            }

            /* ── Menus ───────────────────────────────────────────── */
            QMenu#headerMoreMenu, QMenu#generateMenu, QMenu#generateStepMenu {
                background-color: #0d1828;
                color: #c8d6e6;
                border: 1px solid #1e3047;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu#headerMoreMenu::item, QMenu#generateMenu::item, QMenu#generateStepMenu::item {
                background-color: transparent;
                color: #c8d6e6;
                padding: 7px 14px;
                border-radius: 6px;
            }
            QMenu#generateStepMenu::item:enabled {
                background-color: #112134;
                color: #d8eeff;
                border: 1px solid #254a6a;
                font-weight: 700;
            }
            QMenu#generateStepMenu::item:disabled {
                background-color: #0d1828;
                color: rgba(120, 140, 165, 100);
                border: 1px solid #162030;
                font-weight: 400;
            }
            QMenu#headerMoreMenu::item:selected, QMenu#generateMenu::item:selected,
            QMenu#generateStepMenu::item:selected {
                background-color: #1a3048;
                color: #eaf4ff;
            }
            QMenu#generateStepMenu::item:disabled:selected {
                background-color: #0d1828;
                color: rgba(120, 140, 165, 100);
            }
            QMenu#headerMoreMenu::separator, QMenu#generateMenu::separator,
            QMenu#generateStepMenu::separator {
                height: 1px;
                background: #1e3047;
                margin: 5px 8px;
            }

            /* ── Inputs ──────────────────────────────────────────── */
            QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #0d1825;
                border: 1px solid #243a55;
                border-radius: 8px;
                color: #dce8f4;
                padding: 7px 10px;
                selection-background-color: #1e4a7a;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #3a90d0;
                background-color: #0e2035;
            }
            QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled,
            QSpinBox:disabled, QDoubleSpinBox:disabled {
                background-color: #0b1420;
                color: #3d5068;
                border: 1px solid #162030;
            }

            /* Segment inspector text area */
            QScrollArea#segmentEditorScroll { background-color: transparent; border: none; }
            QWidget#segmentEditorContainer { background-color: transparent; }
            QFrame#segmentInspectorCard {
                background-color: #0f1c2b;
                border: 1px solid #1e3047;
                border-radius: 0px;
            }
            QTextEdit#segmentInspectorEditor {
                background-color: #0d1825;
                border: 1px solid #1e3a58;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QTextEdit#segmentInspectorEditor:focus {
                border: 1px solid #3a90d0;
                background-color: #0e2035;
            }

            /* ── Progress bar ────────────────────────────────────── */
            QProgressBar {
                border: 1px solid #1a2f45;
                border-radius: 8px;
                text-align: center;
                background-color: #0d1825;
                color: #7a9ab8;
                font-size: 10px;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #29b89f, stop:1 #1980c0);
                border-radius: 8px;
            }

            /* ── Checkboxes / Radios ─────────────────────────────── */
            QCheckBox { background: transparent; color: #b8cce0; spacing: 6px; }
            QCheckBox::indicator {
                width: 15px; height: 15px;
                border: 1px solid #2a4560;
                border-radius: 4px;
                background-color: #0e1e30;
            }
            QCheckBox::indicator:checked {
                background-color: #1e80c0;
                border-color: #3aaced;
                image: none;
            }
            QCheckBox::indicator:hover { border-color: #3a6090; }
            QRadioButton { background: transparent; color: #b8cce0; spacing: 6px; }
            QRadioButton::indicator {
                width: 14px; height: 14px;
                border: 1px solid #2a4560;
                border-radius: 7px;
                background-color: #0e1e30;
            }
            QRadioButton::indicator:checked {
                background-color: #1e80c0;
                border-color: #3aaced;
            }

            /* ── Scroll bars ─────────────────────────────────────── */
            QScrollArea { border: none; background-color: #0e1520; }
            QScrollBar:vertical {
                border: none;
                background: #0b1118;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #1e3555;
                min-height: 28px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: #2a4e7a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar:horizontal {
                border: none;
                background: #0b1118;
                height: 8px;
            }
            QScrollBar::handle:horizontal {
                background: #1e3555;
                min-width: 28px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover { background: #2a4e7a; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QStackedWidget#leftPanelStack { background: transparent; }

            /* ── ComboBox dropdown ───────────────────────────────── */
            QComboBox QAbstractItemView {
                background-color: #0d1825;
                color: #dce8f4;
                selection-background-color: #1e4a7a;
                border: 1px solid #243a55;
                border-radius: 6px;
                outline: none;
                padding: 4px;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                width: 10px;
                height: 10px;
            }

            /* ── Message boxes ───────────────────────────────────── */
            QMessageBox { background-color: #0d1825; }
            QMessageBox QLabel { color: #c8d6e6; background: transparent; }
            QMessageBox QPushButton { min-width: 90px; }

            /* ── Tabs ────────────────────────────────────────────── */
            QTabWidget::pane {
                border: 1px solid #1e3047;
                border-radius: 10px;
                background: #0d1825;
                top: -1px;
            }
            QTabBar::tab {
                background: #111e30;
                color: #7a8fa8;
                padding: 8px 14px;
                border: 1px solid #1e3047;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                min-width: 100px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #0d1825;
                color: #4da6e8;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background: #162030;
                color: #a8c0d8;
            }

            /* ── Sliders ─────────────────────────────────────────── */
            QSlider::groove:horizontal {
                height: 4px;
                background: #1a2f45;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #3a90d0;
                border: 1px solid #2070b0;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #5ab0f0;
                border-color: #3a90d0;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1e5a9a, stop:1 #3a90d0);
                border-radius: 2px;
            }

            /* ── Tooltip ─────────────────────────────────────────── */
            QToolTip {
                background-color: #0d1825;
                color: #c8d6e6;
                border: 1px solid #1e3047;
                border-radius: 6px;
                padding: 5px 9px;
                font-size: 11px;
            }
        """)

        # -----------------------------
        # State (must exist before setup_ui)
        # -----------------------------
        # Track generated/selected artifacts for quick inspection.
        # Keys are stable IDs, values are absolute file paths.
        self.processed_artifacts = {}
        self._runtime_logs = []
        self._pending_runtime_log_entries = []
        self._runtime_log_view_entry_count = 0
        self._runtime_log_flush_timer = QTimer(self)
        self._runtime_log_flush_timer.setSingleShot(True)
        self._runtime_log_flush_timer.setInterval(100)
        self._runtime_log_flush_timer.timeout.connect(self._flush_runtime_log_entries)
        self._editor_highlight_chunks = {}
        self._editor_highlight_state = {}
        self.runtime_log_received.connect(self._append_runtime_log_entry)
        self.workspace_root = workspace_root()
        self._cleanup_temp_root()
        self.project_service = ProjectService(self.workspace_root)
        self.project_bridge = GUIProjectBridge(self.project_service)
        self.voice_catalog_service = VoiceCatalogService(self.workspace_root)
        self.subtitle_controller = SubtitleController(self)
        self.pipeline_controller = PipelineController(self)
        self.preview_controller = PreviewController(self)
        self.project_controller = ProjectController(self)
        self.video_filter_controller = VideoFilterController(self)
        self.ocr_controller = OcrController(self)
        self.current_project_state = None
        # Do not inherit a legacy global Subtitle Source from .env.  Opening
        # a project below will replace this with that project's own setting.
        os.environ["TRANSCRIPTION_ENGINE"] = _default_asr_engine()
        self.current_segment_models = []
        self.current_translated_segment_models = []
        self.selected_whisper_model_name = "auto"
        self._last_audio_preview_path = ""
        self._segment_preview_threads = {}
        self._voice_sample_preview_thread = None
        self._voiceover_force_refresh = False
        self.voice_catalog_entries_all = []
        self.voice_catalog_entries = []

        self.voice_catalog_map = {}
        self._voice_signals_bound = False
        self._media_backend_ready = False
        self._blur_region_signal_bound = False
        self._blur_edit_finished_signal_bound = False
        self._preview_audio_signals_bound = False
        self.media_player = BootstrapMediaBackend()
        self.voice_preview_dialog = None
        self._voice_preview_row_buttons = {}
        self._tracked_progress_dialogs = []
        self._timeline_timing_undo_stack = []
        self._timeline_timing_redo_stack = []
        self._suspend_timeline_undo = False
        self._timeline_waveform_cache_key = None
        self._timeline_waveform_samples = []
        self._timeline_waveform_duration_s = 0.0
        self._timeline_waveform_worker = None
        self._desired_timeline_waveform_request = None
        self._timeline_video_thumb_cache_key = None
        self._timeline_video_thumbnails = []
        self._timeline_thumbnail_worker = None
        self._desired_timeline_thumbnail_request = None
        self._pending_timeline_waveform_refresh = False
        self._pending_timeline_thumbnail_refresh = False
        self._allow_post_pipeline_preview_assets = False
        self._subtitle_custom_style_state = None
        self._subtitle_preset_apply_in_progress = False
        # Exact full-block subtitle backgrounds are measured by libass.  Keep
        # that expensive work out of the GUI thread; the active ASS track is
        # intentionally retained until the newest debounced result is ready.
        self._subtitle_ass_request_token = 0
        self._subtitle_ass_worker_running = False
        self._subtitle_ass_worker_threads = []
        self._subtitle_ass_pending_snapshot = None
        self.subtitle_ass_ready.connect(self._on_async_subtitle_ass_ready)
        self._video_filter_ui_sync = False
        self._video_filter_preset_key = "original"
        self._video_filter_intensity = 75
        self._video_filter_adjust_overrides = {
            "brightness": 0,
            "contrast": 0,
            "saturation": 0,
            "temperature": 0,
            "highlights": 0,
            "shadows": 0,
        }
        self._video_filter_user_modified = {
            "brightness": False,
            "contrast": False,
            "saturation": False,
            "temperature": False,
            "highlights": False,
            "shadows": False,
        }
        self._pending_video_filter_preview = False
        self._filter_thumbnail_visible = False
        self._filter_preview_blur_was_checked = False
        self._filter_preview_ocr_was_editable = False
        self._suspend_ocr_overlay = False
        self._ocr_overlay_visible = True
        self._ocr_translator_active = False
        self._ocr_translator_rect = (0.2, 0.2, 0.6, 0.25)
        self._ocr_translator_capture_worker = None
        self._ocr_translator_translation_worker = None
        self._play_video_filter_preview_when_ready = False
        self._filter_thumbnail_target_height = 320
        self._video_filter_preview_dirty = False
        self._video_filter_apply_requested = False
        self._blur_edit_finish_syncing = False
        self._blur_region_preview_dirty = False
        # Blur/Mask are MPV filter effects. During a paused geometry edit we
        # suppress only the active layer from the filter graph so an old,
        # stale effect is never left behind the lightweight edit overlay.
        self._deferred_effect_edit_type = ""
        self._deferred_effect_edit_layer_id = ""
        # A selected layer becomes editable only after an explicit paused
        # selection.  Playback and its pause transition never implicitly
        # restore edit chrome for the previously selected layer.
        self._preview_edit_layer_id = ""
        self._review_mode_active = False
        # Overlay drags can emit dozens of events per second.  Persisting the
        # full project/timeline for each one causes synchronous JSON and
        # project-file writes on the UI thread, so collect rapid edits and
        # save their final state shortly after interaction settles.
        self._pending_timeline_persist = False
        self._pending_mask_state_persist = False
        self._pending_blur_state_persist = False
        self._timeline_persist_timer = QTimer(self)
        self._timeline_persist_timer.setSingleShot(True)
        self._timeline_persist_timer.setInterval(180)
        self._timeline_persist_timer.timeout.connect(self._flush_pending_timeline_persist)
        # Simple pipeline runner (Run All)
        self._pipeline_active = False
        self._pipeline_step = ""

        # Pre-rendered video state
        self.last_preview_video_path = ""
        self.last_styled_preview_path = ""
        self.last_styled_preview_signature = ""
        self.last_exact_preview_5s_path = ""

        self._deferred_startup_stage1_done = False
        self._deferred_startup_stage2_done = False

        self.setup_ui()
        self._apply_reimagined_theme()
        self._configure_local_voice_mode_ui()
        self._timeline_visual_refresh_timer = QTimer(self)
        self._timeline_visual_refresh_timer.setSingleShot(True)
        self._timeline_visual_refresh_timer.timeout.connect(self._run_pending_timeline_visual_refresh)
        QTimer.singleShot(0, self._run_deferred_startup_stage1)
        QTimer.singleShot(600, self._run_deferred_startup_stage2)

    def _apply_reimagined_theme(self):
        """Append the Studio 2 theme after widgets exist.

        The original stylesheet remains as a compatibility base for legacy
        custom widgets; these selectors define the new shell and override the
        shared chrome without changing the rendering/processing code.
        """
        self.setStyleSheet(self.styleSheet() + "\n" + _REIMAGINED_THEME)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoTranslatorGUI()
    window.show()
    sys.exit(app.exec())


