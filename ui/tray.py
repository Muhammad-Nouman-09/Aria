"""System tray icon with a right-click menu."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ui.icon import make_icon


class Tray(QSystemTrayIcon):
    def __init__(self, window, app: QApplication):
        super().__init__(make_icon(), parent=app)
        self.window = window
        self.app = app
        self.setToolTip("ARIA")

        menu = QMenu()
        open_action = QAction("Open ARIA", menu)
        open_action.triggered.connect(self._open)
        menu.addAction(open_action)

        speak_action = QAction("Toggle spoken replies", menu)
        speak_action.triggered.connect(self._toggle_speak)
        menu.addAction(speak_action)

        menu.addSeparator()
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _open(self) -> None:
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _toggle_speak(self) -> None:
        chk = getattr(self.window, "speak_chk", None)
        if chk is not None:
            chk.setChecked(not chk.isChecked())

    def _quit(self) -> None:
        self.hide()
        self.window.close()
        self.app.quit()

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._open()
