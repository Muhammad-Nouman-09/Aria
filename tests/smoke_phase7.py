"""Phase 7 smoke test — email gating, startup registry, audit, .env upsert,
and offscreen settings/audit dialogs. No real email account or display needed.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import ENV_PATH, get_settings, update_env_value  # noqa: E402
from core.memory import Memory  # noqa: E402
from core.permissions import PermissionManager, Risk  # noqa: E402
from core.tools import NOT_YET_IMPLEMENTED, ToolContext, execute_tool  # noqa: E402
from modules.integrations.email import EmailClient  # noqa: E402
from modules.system.startup import is_startup_enabled, set_startup  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


print("== tool coverage ==")
check("no tools left unimplemented", NOT_YET_IMPLEMENTED == {})

print("== email gating (not configured) ==")
s = get_settings()
ec = EmailClient(s)
r_read = ec.read_email()
check("read_email reports not configured", "not configured" in str(r_read).lower())
r_send = ec.send_email("a@b.com", "hi", "body")
check("send_email reports not configured", "not configured" in str(r_send).lower())

# Through the dispatcher (auto-approve so we reach the handler).
mem = Memory(":memory:")
pm = PermissionManager(s, approver=lambda a, p: True)
check("send_email is HIGH risk", pm.check("send_email", {}).risk == Risk.HIGH)
ctx = ToolContext(s, mem, pm, scheduler=None)
res = execute_tool("read_email", {}, ctx)
check("dispatch reaches email handler", "not configured" in res.lower())

print("== startup registry roundtrip ==")
NAME = "ARIA_SMOKE_TEST"
set_startup(True, NAME, '"C:\\fake\\aria.exe"')
check("startup enabled", is_startup_enabled(NAME))
set_startup(False, NAME)
check("startup disabled", not is_startup_enabled(NAME))

print("== audit log recall ==")
mem.log_audit("run_shell_command", {"command": "Get-Date"},
              approved_by="user", result="success")
audit = mem.recent_audit(limit=10)
check("audit row recorded", len(audit) >= 1 and audit[0]["action"] == "run_shell_command")

print("== .env upsert ==")
tmp_env = Path(tempfile.mkdtemp(prefix="aria_p7_")) / ".env"
update_env_value("FOO", "bar", tmp_env)
update_env_value("FOO", "baz", tmp_env)
text = tmp_env.read_text(encoding="utf-8")
check("env key updated in place", "FOO=baz" in text and text.count("FOO=") == 1)

print("== offscreen dialogs ==")
from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from ui.audit_dialog import AuditDialog  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402

ad = AuditDialog(mem)
check("audit dialog populated", ad.table.rowCount() >= 1)
sd = SettingsDialog(s)
check("settings dialog has toggles", len(sd._checks) >= 5)

mem.close()
print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL PHASE 7 SMOKE CHECKS PASSED")
