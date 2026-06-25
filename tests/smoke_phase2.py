"""Phase 2 smoke test — filesystem write/move/copy/delete + permission gate.

Runs without an API key. Uses a temp directory so nothing real is touched,
and exercises both the raw writer functions and the permission-gated
dispatch path.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from core.memory import Memory  # noqa: E402
from core.permissions import PermissionManager  # noqa: E402
from core.tools import ToolContext, execute_tool  # noqa: E402
from modules.filesystem import reader, writer  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


tmp = Path(tempfile.mkdtemp(prefix="aria_p2_"))

print("== writer (raw) ==")
f1 = tmp / "note.txt"
r = writer.write_file(str(f1), "hello world", "write")
check("write_file ok", r.get("status") == "written")
check("file content correct", reader.read_file(str(f1))["content"] == "hello world")
writer.write_file(str(f1), "\nmore", "append")
check("append works", "more" in reader.read_file(str(f1))["content"])

f_nested = tmp / "sub" / "deep" / "code.py"
r = writer.write_file(str(f_nested), "print('hi')", "write")
check("write creates parent dirs", f_nested.exists())

dst = tmp / "copied.txt"
r = writer.move_or_copy_file(str(f1), str(dst), "copy")
check("copy ok", dst.exists() and r.get("status") == "copyd")

moved = tmp / "moved.txt"
r = writer.move_or_copy_file(str(dst), str(moved), "move")
check("move ok", moved.exists() and not dst.exists())

r = writer.move_or_copy_file(str(f1), str(moved), "copy", overwrite=False)
check("copy refuses overwrite", "error" in r)

r = writer.delete_file(str(moved), send_to_recycle_bin=True)
check("delete to recycle bin", r.get("status", "").startswith("sent") and not moved.exists())

r = writer.delete_file(str(f_nested), send_to_recycle_bin=False)
check("permanent delete refused", "error" in r and "disabled" in r["error"].lower())

print("== permission gate ==")
s = get_settings()
# Restrict writes to the temp dir for the gate tests.
s.allowed_directories = [str(tmp)]
pm = PermissionManager(s, approver=lambda a, p: True)  # auto-approve
d_in = pm.check("write_file", {"file_path": str(tmp / "ok.txt"), "content": "x"})
check("write inside allowed dir permitted", d_in.allowed and d_in.needs_approval)
d_out = pm.check("write_file", {"file_path": r"C:\Users\Public\evil.txt", "content": "x"})
check("write outside allowed dir blocked", not d_out.allowed)
d_blk = pm.check("delete_file", {"path": r"C:\Windows\system32\drivers\etc\hosts"})
check("delete in blocked dir refused", not d_blk.allowed)

print("== dispatch (approved) ==")
mem = Memory(":memory:")
ctx = ToolContext(s, mem, pm)
out = execute_tool("write_file", {"file_path": str(tmp / "ok.txt"), "content": "dispatched"}, ctx)
check("dispatch write succeeds", "written" in out)
check("dispatched file exists", (tmp / "ok.txt").read_text() == "dispatched")

# Auto-deny gate -> dispatch should report denial.
pm_deny = PermissionManager(s, approver=lambda a, p: False)
ctx_deny = ToolContext(s, mem, pm_deny)
out_deny = execute_tool("write_file", {"file_path": str(tmp / "no.txt"), "content": "x"}, ctx_deny)
check("denied write reports denial", "denied" in out_deny.lower())

mem.close()
import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)

print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL PHASE 2 SMOKE CHECKS PASSED")
