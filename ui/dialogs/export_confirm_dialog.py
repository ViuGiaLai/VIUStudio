from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from app.anti_duplicate import AntiDuplicateSettings
from ui.dialogs.anti_duplicate_custom_dialog import AntiDuplicateCustomDialog


class ExportConfirmDialog(QDialog):
    """Confirmation dialog for export summary with 1-pass Auto Recap toggles & Custom settings."""

    def __init__(
        self,
        summary_lines: list[str],
        *,
        is_already_recapped: bool = False,
        initial_recap: bool = True,
        ad_settings: AntiDuplicateSettings | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.is_already_recapped = is_already_recapped
        self.ad_settings = ad_settings or AntiDuplicateSettings(
            enabled=True, continuous_mode=True, allow_horizontal_flip=True
        )
        self.setWindowTitle("Export Summary & Confirmation")
        self.setMinimumWidth(560)
        self.setMinimumHeight(520)
        self.resize(580, 560)
        self._setup_style()
        self._init_ui(summary_lines, initial_recap)

    def _setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QTextEdit {
                background-color: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-size: 12px;
                line-height: 1.4;
            }
            QCheckBox {
                color: #f1f5f9;
                font-size: 13px;
                font-weight: 600;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #475569;
                background-color: #0f172a;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border-color: #38bdf8;
            }
            QPushButton#customBtn {
                background-color: #1e293b;
                color: #38bdf8;
                border: 1px solid #0284c7;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#customBtn:hover {
                background-color: #0369a1;
                color: #ffffff;
            }
            QPushButton#customBtn:disabled {
                background-color: #1e293b;
                color: #475569;
                border-color: #334155;
            }
            QPushButton#startBtn {
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 9px 24px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#startBtn:hover {
                background-color: #1d4ed8;
            }
            QPushButton#cancelBtn {
                background-color: #334155;
                color: #cbd5e1;
                border: none;
                border-radius: 6px;
                padding: 9px 18px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#cancelBtn:hover {
                background-color: #475569;
            }
        """)

    def _init_ui(self, summary_lines: list[str], initial_recap: bool):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 18, 20, 18)

        # Header
        header_layout = QHBoxLayout()
        icon_lbl = QLabel("📦")
        icon_lbl.setFont(QFont("Segoe UI", 18))
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t_lbl = QLabel("Export Final Video")
        t_lbl.setFont(QFont("Segoe UI", 14, QFont.Bold))
        t_lbl.setStyleSheet("color: #38bdf8;")
        title_col.addWidget(t_lbl)

        sub_lbl = QLabel("Kiểm tra thông số cấu hình video trước khi bắt đầu xuất.")
        sub_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        title_col.addWidget(sub_lbl)
        header_layout.addLayout(title_col)
        header_layout.addStretch(1)
        layout.addLayout(header_layout)

        # Summary text
        self.summary_edit = QTextEdit()
        self.summary_edit.setReadOnly(True)
        self.summary_edit.setPlainText("\n".join(summary_lines))
        layout.addWidget(self.summary_edit, 1)

        # Recap Options Card
        recap_card = QFrame()
        recap_card.setStyleSheet("background-color: #1e293b; border: 1px solid #334155; border-radius: 8px;")
        rc_layout = QVBoxLayout(recap_card)
        rc_layout.setContentsMargins(14, 10, 14, 10)
        rc_layout.setSpacing(6)

        top_rc = QHBoxLayout()
        self.recap_cb = QCheckBox("✨ Bật Chống trùng lặp (Auto Recap 1-Pass)")
        self.recap_cb.setChecked(initial_recap)
        self.recap_cb.setEnabled(True)
        self.recap_cb.setToolTip(
            "Áp dụng bộ lọc kháng bản quyền (Punch Zoom 5.5s, Lật gương, 4 Tone màu, BGM lót...) ngay trong 1 lần xuất."
        )

        top_rc.addWidget(self.recap_cb)
        top_rc.addStretch(1)

        self.custom_btn = QPushButton("⚙️ Tùy chỉnh bước...")
        self.custom_btn.setObjectName("customBtn")
        self.custom_btn.setEnabled(self.recap_cb.isChecked())
        self.custom_btn.clicked.connect(self._open_custom_dialog)
        top_rc.addWidget(self.custom_btn)

        self.recap_cb.toggled.connect(self._on_recap_toggled)
        rc_layout.addLayout(top_rc)

        self.summary_lbl = QLabel(
            f"Thiết lập: {self.ad_settings.summary_text()}"
            if self.recap_cb.isChecked()
            else "Thiết lập: Đang tắt"
        )
        self.summary_lbl.setStyleSheet("color: #94a3b8; font-size: 11px; margin-left: 26px;")
        rc_layout.addWidget(self.summary_lbl)

        layout.addWidget(recap_card)

        # Buttons Row
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.cancel_btn = QPushButton("Hủy (Cancel)")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.start_btn = QPushButton("🚀 Bắt đầu xuất (Start Export)")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.start_btn)

        layout.addLayout(btn_row)

    def _on_recap_toggled(self, checked: bool):
        self.custom_btn.setEnabled(checked)
        if not checked:
            self.summary_lbl.setText("Thiết lập: Đang tắt")
        else:
            self.summary_lbl.setText(f"Thiết lập: {self.ad_settings.summary_text()}")

    def _open_custom_dialog(self):
        dlg = AntiDuplicateCustomDialog(self.ad_settings, parent=self)
        if dlg.exec():
            self.ad_settings = dlg.settings
            self.summary_lbl.setText(f"Thiết lập: {self.ad_settings.summary_text()}")

    def get_result(self) -> tuple[bool, AntiDuplicateSettings]:
        wants_recap = bool(self.recap_cb.isChecked())
        return wants_recap, self.ad_settings
