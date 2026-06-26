"""Audit-log viewer: a read-only table of recent actions ARIA took."""

from __future__ import annotations

from PyQt6.QtWidgets import (QDialog, QHeaderView, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)

from core.memory import Memory

COLUMNS = ["Time", "Action", "Approved by", "Result"]


class AuditDialog(QDialog):
    def __init__(self, memory: Memory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.setWindowTitle("ARIA — Audit log")
        self.resize(640, 420)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        layout.addWidget(refresh)

        self.reload()

    def reload(self) -> None:
        rows = self.memory.recent_audit(limit=200)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [row.get("timestamp", ""), row.get("action", ""),
                      row.get("approved_by", ""), row.get("result", "")]
            for c, val in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(str(val)))
