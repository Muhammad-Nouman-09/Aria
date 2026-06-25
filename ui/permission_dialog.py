"""Approval dialog shown before HIGH-risk actions.

Plus GuiApprover: a thread-safe adapter so the agent's tool worker thread can
request approval and block until the user answers on the GUI thread.
"""

from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QPlainTextEdit,
                             QVBoxLayout)


class PermissionDialog(QDialog):
    def __init__(self, action: str, preview: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ARIA — Approval required")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)

        heading = QLabel(f"ARIA wants to run: <b>{action}</b>")
        heading.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(heading)

        body = QPlainTextEdit(preview)
        body.setReadOnly(True)
        body.setMaximumHeight(220)
        layout.addWidget(body)

        buttons = QDialogButtonBox()
        self.approve_btn = buttons.addButton(
            "Approve", QDialogButtonBox.ButtonRole.AcceptRole)
        self.deny_btn = buttons.addButton(
            "Deny", QDialogButtonBox.ButtonRole.RejectRole)
        self.approve_btn.clicked.connect(self.accept)
        self.deny_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)


class GuiApprover(QObject):
    """Callable passed to PermissionManager as the approver.

    Invoked from a worker thread; emits a signal that shows the dialog on the
    GUI thread, then blocks the worker until the user responds.
    """

    _request = pyqtSignal(str, str, object)

    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window
        # Queued automatically because emit happens from another thread.
        self._request.connect(self._show_dialog)

    def __call__(self, action: str, preview: str) -> bool:
        box = {"event": threading.Event(), "result": False}
        self._request.emit(action, preview, box)
        box["event"].wait()
        return box["result"]

    def _show_dialog(self, action: str, preview: str, box: dict) -> None:
        try:
            dlg = PermissionDialog(action, preview, self.parent_window)
            box["result"] = dlg.exec() == QDialog.DialogCode.Accepted
        finally:
            box["event"].set()
