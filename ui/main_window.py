"""ARIA main chat window (PyQt6).

Dark theme, scrollable chat transcript with user/ARIA bubbles, collapsible
tool-call lines, a status indicator, and a text input with optional
microphone capture and spoken replies. The agent runs on a background asyncio
loop via AsyncBridge; results return to the GUI thread through Qt signals.
"""

from __future__ import annotations

import html

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QPushButton, QTextEdit, QVBoxLayout,
                             QWidget)

from config import Settings
from core.agent import Agent
from ui.async_bridge import AsyncBridge
from ui.icon import make_icon
from ui.permission_dialog import GuiApprover

STYLE = """
QMainWindow, QWidget { background: #0f172a; color: #e2e8f0; }
QTextEdit { background: #0b1220; border: 1px solid #1e293b; border-radius: 8px; padding: 8px; }
QLineEdit { background: #111827; border: 1px solid #1e293b; border-radius: 8px; padding: 8px; color: #e2e8f0; }
QPushButton { background: #2563eb; border: none; border-radius: 8px; padding: 8px 14px; color: white; }
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #334155; color: #94a3b8; }
QCheckBox { color: #94a3b8; }
QLabel#status { color: #94a3b8; }
"""

STATUS_COLORS = {
    "idle": ("#64748b", "idle"),
    "thinking": ("#f59e0b", "thinking..."),
    "listening": ("#22c55e", "listening..."),
    "speaking": ("#3b82f6", "speaking..."),
}


class MainWindow(QMainWindow):
    # Signals so background threads can update the GUI safely.
    _reply = pyqtSignal(str)
    _error = pyqtSignal(str)
    _tool = pyqtSignal(str, str, str)
    _heard = pyqtSignal(str)
    _status = pyqtSignal(str)

    def __init__(self, settings: Settings, bridge: AsyncBridge | None = None):
        super().__init__()
        self.settings = settings
        self.bridge = bridge or AsyncBridge()
        self._voice = None  # lazy VoiceSession

        self.setWindowTitle("ARIA")
        self.setWindowIcon(make_icon())
        self.resize(720, 640)
        self.setStyleSheet(STYLE)

        self._build_ui()

        # Agent with the GUI approver + tool observer.
        self.approver = GuiApprover(self)
        self.agent = Agent(settings=settings, approver=self.approver,
                           on_tool=self._on_tool_threadsafe)

        # Wire cross-thread signals to GUI slots.
        self._reply.connect(self._append_aria)
        self._error.connect(self._append_error)
        self._tool.connect(self._append_tool)
        self._heard.connect(self._on_heard)
        self._status.connect(self._set_status)

        self._add_system_line(
            f"ARIA ready · model {settings.model}. Type a message and press Enter.")

    # ----- UI construction -----
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        root.addWidget(self.chat, 1)

        self.status = QLabel("● idle")
        self.status.setObjectName("status")
        root.addWidget(self.status)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask ARIA…")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)

        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setToolTip("Speak a message")
        self.mic_btn.clicked.connect(self._voice_input)
        row.addWidget(self.mic_btn)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)

        self.speak_chk = QCheckBox("Speak")
        self.speak_chk.setChecked(settings_voice_default(self.settings))
        row.addWidget(self.speak_chk)

        root.addLayout(row)
        self.setCentralWidget(central)

    # ----- sending -----
    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._append_user(text)
        self._set_busy(True)
        self._set_status("thinking")
        fut = self.bridge.submit(self.agent.run(text))
        fut.add_done_callback(self._on_future_done)

    def _on_future_done(self, fut) -> None:
        # Runs on the asyncio loop thread; marshal back via signals.
        try:
            result = fut.result()
            self._reply.emit(result)
        except Exception as e:  # noqa: BLE001
            self._error.emit(str(e))

    # ----- voice -----
    def _get_voice(self):
        if self._voice is None:
            from modules.voice.session import VoiceSession
            self._voice = VoiceSession(self.settings)
        return self._voice

    def _voice_input(self) -> None:
        self._set_status("listening")
        self._set_busy(True)
        fut = self.bridge.submit(self._capture())
        fut.add_done_callback(self._on_capture_done)

    async def _capture(self) -> str:
        import asyncio
        voice = self._get_voice()
        return await asyncio.to_thread(voice.listen_once)

    def _on_capture_done(self, fut) -> None:
        try:
            text = fut.result()
        except Exception as e:  # noqa: BLE001
            self._error.emit(f"voice capture failed: {e}")
            return
        self._heard.emit(text or "")

    def _on_heard(self, text: str) -> None:
        self._set_busy(False)
        self._set_status("idle")
        if not text.strip():
            self._add_system_line("(heard nothing)")
            return
        self.input.setText(text)
        self._send()

    def _maybe_speak(self, text: str) -> None:
        if not self.speak_chk.isChecked():
            return
        import asyncio
        self._set_status("speaking")

        async def _speak():
            voice = self._get_voice()
            await asyncio.to_thread(voice.speak, text)

        fut = self.bridge.submit(_speak())
        fut.add_done_callback(lambda _f: self._status.emit("idle"))

    # ----- chat rendering -----
    def _bubble(self, who: str, text: str, color: str, align: str) -> None:
        safe = html.escape(text).replace("\n", "<br>")
        self.chat.append(
            f'<div style="margin:6px 0; text-align:{align};">'
            f'<span style="background:{color}; padding:6px 10px; border-radius:10px; '
            f'display:inline-block; max-width:80%; text-align:left;">'
            f'<b>{who}</b><br>{safe}</span></div>')
        self.chat.verticalScrollBar().setValue(
            self.chat.verticalScrollBar().maximum())

    def _append_user(self, text: str) -> None:
        self._bubble("you", text, "#1e3a8a", "right")

    def _append_aria(self, text: str) -> None:
        self._bubble("ARIA", text, "#1e293b", "left")
        self._set_busy(False)
        self._set_status("idle")
        self._maybe_speak(text)

    def _append_error(self, text: str) -> None:
        self._add_system_line(f"⚠ {text}")
        self._set_busy(False)
        self._set_status("idle")

    def _append_tool(self, phase: str, name: str, info: str) -> None:
        arrow = "▸" if phase == "start" else "✓"
        safe = html.escape(f"{arrow} {name}  {info}")
        self.chat.append(
            f'<div style="color:#64748b; font-size:11px; margin:2px 0;">{safe}</div>')

    def _add_system_line(self, text: str) -> None:
        self.chat.append(
            f'<div style="color:#475569; font-style:italic; margin:4px 0;">'
            f'{html.escape(text)}</div>')

    # ----- helpers -----
    def _on_tool_threadsafe(self, phase: str, name: str, info: str) -> None:
        self._tool.emit(phase, name, info)

    def _set_busy(self, busy: bool) -> None:
        self.input.setDisabled(busy)
        self.send_btn.setDisabled(busy)
        self.mic_btn.setDisabled(busy)

    def _set_status(self, state: str) -> None:
        color, label = STATUS_COLORS.get(state, STATUS_COLORS["idle"])
        self.status.setText(f'<span style="color:{color}">●</span> {label}')

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        try:
            if self._voice:
                self._voice.stop_wake()
            self.agent.close()
            self.bridge.stop()
        finally:
            super().closeEvent(event)


def settings_voice_default(settings: Settings) -> bool:
    return bool(getattr(settings, "voice_enabled", False))
