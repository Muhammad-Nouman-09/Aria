"""Phase 5 smoke test — PyQt6 GUI under the offscreen platform (no display).

Verifies: widgets construct, the async bridge runs coroutines, the
cross-thread permission approver delivers via a queued signal, and a full
GUI -> bridge -> agent -> signal -> GUI message round-trip works (with a fake
agent so no network/API key is needed).
"""

import os
import sys
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # must precede PyQt import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from config import get_settings  # noqa: E402
from ui.async_bridge import AsyncBridge  # noqa: E402
from ui.icon import make_icon  # noqa: E402
from ui.permission_dialog import GuiApprover, PermissionDialog  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


app = QApplication.instance() or QApplication([])

print("== widgets construct ==")
check("icon not null", not make_icon().isNull())
dlg = PermissionDialog("run_shell_command", "Command:\n  Get-Date")
check("permission dialog built", dlg.windowTitle().startswith("ARIA"))
check("dialog shows preview",
      "Get-Date" in dlg.findChild(QPlainTextEdit).toPlainText())

print("== async bridge ==")
bridge = AsyncBridge()


async def _coro():
    import asyncio
    await asyncio.sleep(0.01)
    return 21 * 2


fut = bridge.submit(_coro())
check("bridge runs coroutine", fut.result(timeout=5) == 42)

print("== cross-thread approver ==")
approver = GuiApprover()
approver._request.disconnect()  # replace modal dialog with an auto-approver


def _fake_show(action, preview, box):
    box["result"] = True
    box["event"].set()


approver._request.connect(_fake_show)
holder = {}


def _worker():
    holder["result"] = approver("write_file", "WRITE file: x")


t = threading.Thread(target=_worker)
t.start()
deadline = time.time() + 5
while t.is_alive() and time.time() < deadline:
    app.processEvents()
    time.sleep(0.005)
t.join(timeout=1)
check("approval delivered via queued signal", holder.get("result") is True)

print("== full GUI round-trip (fake agent) ==")
from ui.main_window import MainWindow  # noqa: E402


class FakeAgent:
    def __init__(self):
        self.on_tool = None

    async def run(self, text, source="text"):
        return f"echo: {text}"

    def close(self):
        pass


s = get_settings()
s.openrouter_api_key = "test-key"  # lets the real Agent build during __init__
win = MainWindow(s, bridge=bridge)
win.agent = FakeAgent()  # swap in fake; no network
win.input.setText("hello aria")
win._send()

deadline = time.time() + 5
while "echo: hello aria" not in win.chat.toPlainText() and time.time() < deadline:
    app.processEvents()
    time.sleep(0.01)
check("user bubble rendered", "hello aria" in win.chat.toPlainText())
check("agent reply rendered", "echo: hello aria" in win.chat.toPlainText())

print("== tray ==")
from ui.tray import Tray  # noqa: E402

tray = Tray(win, app)
check("tray built with menu", tray.contextMenu() is not None
      and len(tray.contextMenu().actions()) >= 3)

bridge.stop()
print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL PHASE 5 SMOKE CHECKS PASSED")
