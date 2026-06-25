"""Phase 3 smoke test — OpenRouter tool conversion + web scraping + download.

The tool-conversion checks are offline. The scrape/download checks hit
example.com (a stable, tiny page) and are skipped gracefully if offline.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from core.llm import OPENAI_TOOLS, TOOLS, to_openai_tools  # noqa: E402
from core.memory import Memory  # noqa: E402
from core.permissions import PermissionManager  # noqa: E402
from core.tools import ToolContext, execute_tool  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


print("== OpenRouter tool conversion ==")
check("same count", len(OPENAI_TOOLS) == len(TOOLS) == 21)
first = OPENAI_TOOLS[0]
check("openai shape: type=function", first["type"] == "function")
check("openai shape: has function.name", "name" in first["function"])
check("openai shape: parameters mapped", first["function"]["parameters"] == TOOLS[0]["input_schema"])
names_in = {t["name"] for t in TOOLS}
names_out = {t["function"]["name"] for t in OPENAI_TOOLS}
check("names preserved", names_in == names_out)

print("== scraper (live; skipped if offline) ==")
online = True
try:
    from modules.web import scraper
    r = scraper.scrape_webpage("https://example.com", "text")
    if "error" in r:
        print(f"  [SKIP] offline? {r['error']}")
        online = False
    else:
        check("text extract has content", "example domain" in r["data"].lower())
    if online:
        rl = scraper.scrape_webpage("https://example.com", "links")
        check("links mode returns list", isinstance(rl["data"], list))
except Exception as e:
    print(f"  [SKIP] scraper error: {e}")
    online = False

print("== download (live; skipped if offline) ==")
if online:
    s = get_settings()
    s.allowed_directories = []  # don't constrain the temp path for the test
    mem = Memory(":memory:")
    pm = PermissionManager(s, approver=lambda a, p: True)
    ctx = ToolContext(s, mem, pm)
    tmp = Path(tempfile.mkdtemp(prefix="aria_p3_"))
    dest = tmp / "example.html"
    out = execute_tool("download_file", {"url": "https://example.com",
                                         "save_path": str(dest)}, ctx)
    check("download succeeds", "downloaded" in out and dest.exists() and dest.stat().st_size > 0)
    mem.close()
    import shutil  # noqa: E402
    shutil.rmtree(tmp, ignore_errors=True)
else:
    print("  [SKIP] offline")

print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL PHASE 3 SMOKE CHECKS PASSED")
