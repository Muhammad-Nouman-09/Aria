"""Phase 1 smoke test — runs without an API key.

Exercises imports, settings, SQLite memory, the permission gate, and a few
tool dispatches that don't require user approval or the network.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from core.memory import Memory  # noqa: E402
from core.permissions import PermissionManager  # noqa: E402
from core.tools import ToolContext, execute_tool  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


print("== settings ==")
s = get_settings()
check("settings load", bool(s.model))
check("blocked dirs parsed", len(s.blocked_directories) >= 1)

print("== memory ==")
mem = Memory(":memory:")
fid = mem.add_fact("Projects live in D:/Projects", "project")
check("add_fact returns id", isinstance(fid, int))
check("recall finds fact", any("Projects" in f["fact"] for f in mem.recall_facts("projects")))
tid = mem.add_todo("pay invoice", "high")
check("add_todo", isinstance(tid, int))
check("list_todos", len(mem.list_todos()) == 1)
check("complete_todo", mem.complete_todo(tid))
mem.set_profile("name", "Nouman")
check("profile roundtrip", mem.get_profile("name") == "Nouman")

print("== permissions ==")
pm = PermissionManager(s, approver=lambda a, p: False)  # auto-deny
d_block = pm.check("run_shell_command", {"command": "shutdown /s /t 0"})
check("dangerous shell blocked", not d_block.allowed and d_block.risk.value == "blocked")
d_ok = pm.check("run_shell_command", {"command": "Get-Date"})
check("safe shell allowed (needs approval)", d_ok.allowed and d_ok.needs_approval)
d_low = pm.check("get_system_info", {"info_type": "cpu"})
check("low-risk auto", d_low.allowed and not d_low.needs_approval)
check("blocked path detected", pm.is_path_blocked(r"C:\Windows\system32\drivers\etc\hosts"))

print("== tool dispatch ==")
ctx = ToolContext(s, mem, pm)
res_cpu = execute_tool("get_system_info", {"info_type": "cpu"}, ctx)
check("get_system_info runs", "percent" in res_cpu)
res_denied = execute_tool("run_shell_command", {"command": "Get-Date"}, ctx)
check("approval-denied shell returns notice", "denied" in res_denied.lower())
res_blocked = execute_tool("run_shell_command", {"command": "format c:"}, ctx)
check("blocked shell returns notice", "blocked" in res_blocked.lower())
res_todo = execute_tool("manage_todo", {"action": "list"}, ctx)
check("manage_todo dispatch", "todos" in res_todo)
res_stub = execute_tool("not_a_real_tool", {}, ctx)
check("unknown tool degrades gracefully",
      isinstance(res_stub, str) and any(
          k in res_stub.lower() for k in ("denied", "error", "no handler", "blocked")))

mem.close()
print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL SMOKE CHECKS PASSED")
