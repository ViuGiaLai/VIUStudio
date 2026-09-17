"""Small glossary editor used by the standalone Movie Review workspace."""
from __future__ import annotations

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QInputDialog, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout)


class ReviewGlossaryDialog(QDialog):
    def __init__(self, terms, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Glossary nhân vật & thuật ngữ")
        self.resize(820, 500)
        self._terms = [dict(item) for item in terms]
        root = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Tên chuẩn", "Loại", "Tên khác", "Cách đọc TTS", "Trạng thái"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        root.addWidget(self.table)
        row = QHBoxLayout()
        for text, callback in (("Thêm", self._add), ("Xóa", self._delete), ("Duyệt", self._approve),
                               ("Duyệt tất cả", self._approve_all), ("Gộp mục đã chọn", self._merge_selected)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        row.addStretch(1)
        root.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._reload()

    def _reload(self):
        self.table.setRowCount(len(self._terms))
        for row, term in enumerate(self._terms):
            values = (term.get("canonical_name", ""), term.get("type", "concept"),
                      ", ".join(term.get("aliases", [])), term.get("tts_pronunciation_override", "") or "",
                      term.get("status", "pending"))
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def _sync(self):
        for row, term in enumerate(self._terms):
            term["canonical_name"] = self.table.item(row, 0).text().strip()
            term["type"] = self.table.item(row, 1).text().strip() or "concept"
            term["aliases"] = [part.strip() for part in self.table.item(row, 2).text().split(",") if part.strip()]
            term["tts_pronunciation_override"] = self.table.item(row, 3).text().strip() or None
            term["status"] = self.table.item(row, 4).text().strip() or "pending"

    def _add(self):
        self._sync()
        self._terms.append({"term_id": f"TERM-{len(self._terms)+1:04d}", "canonical_name": "",
                            "aliases": [], "type": "character", "status": "pending"})
        self._reload()
        self.table.setCurrentCell(len(self._terms) - 1, 0)
        self.table.editItem(self.table.currentItem())

    def _delete(self):
        row = self.table.currentRow()
        if row >= 0:
            self._terms.pop(row)
            self._reload()

    def _approve(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.item(row, 4).setText("approved")

    def _approve_all(self):
        for row in range(self.table.rowCount()):
            self.table.item(row, 4).setText("approved")

    def _merge_selected(self):
        self._sync()
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if len(rows) != 2:
            return
        keep, remove = rows
        first, second = self._terms[keep], self._terms[remove]
        aliases = list(first.get("aliases", [])) + [second.get("canonical_name", "")] + list(second.get("aliases", []))
        first["aliases"] = list(dict.fromkeys(value for value in aliases if value and value != first.get("canonical_name")))
        first["status"] = "approved" if first.get("status") == second.get("status") == "approved" else "pending"
        self._terms.pop(remove)
        self._reload()

    def values(self):
        self._sync()
        return [item for item in self._terms if item.get("canonical_name")]
