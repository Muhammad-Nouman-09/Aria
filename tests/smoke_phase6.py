"""Phase 6 smoke test — semantic memory, reminder scheduler, screenshot.

Semantic recall and screenshots are environment-dependent (model download /
display), so they SKIP rather than fail when unavailable. The scheduler fire
and natural-language time parsing always run.
"""

import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.memory import Memory  # noqa: E402
from modules.tasks.scheduler import ReminderScheduler, parse_when  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


print("== natural-language time parsing ==")
now = datetime(2026, 6, 25, 10, 0, 0)
t_rel = parse_when("in 2 minutes", now=now)
check("'in 2 minutes' -> +2min", t_rel == now + timedelta(minutes=2))
t_tom = parse_when("tomorrow at 3pm", now=now)
check("'tomorrow at 3pm' -> next day 15:00",
      t_tom.day == 26 and t_tom.hour == 15 and t_tom.minute == 0)
t_iso = parse_when("2026-07-01 09:30", now=now)
check("ISO datetime parsed", t_iso.year == 2026 and t_iso.hour == 9)

print("== reminder scheduler fires ==")
mem = Memory(":memory:")
fired = threading.Event()
captured = {}


def _on_fire(msg):
    captured["msg"] = msg
    fired.set()


sched = ReminderScheduler(mem, on_fire=_on_fire)
sched.start()
sched.add("stand-up meeting", datetime.now() + timedelta(seconds=1.5))
got = fired.wait(timeout=6)
check("reminder fired within timeout", got)
check("reminder message delivered", captured.get("msg") == "stand-up meeting")
time.sleep(0.5)  # let APScheduler finish auto-removing the fired one-shot job
sched.shutdown()

print("== semantic memory (ChromaDB plumbing) ==")
try:
    import hashlib

    import chromadb  # noqa: F401
    from chromadb import Documents, EmbeddingFunction, Embeddings

    DIM = 96

    class BagOfWordsEF(EmbeddingFunction):
        """Deterministic hashing embedder — no model download. Overlapping
        words -> closer vectors, enough to verify retrieval plumbing."""

        def __call__(self, inputs: Documents) -> Embeddings:
            vecs = []
            for text in inputs:
                v = [0.0] * DIM
                for word in text.lower().split():
                    h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                    v[h % DIM] += 1.0
                vecs.append(v)
            return vecs

    tmp = Path(tempfile.mkdtemp(prefix="aria_p6_"))
    smem = Memory(tmp / "p6.db", semantic=True, chroma_dir=tmp / "chroma",
                  embedding_function=BagOfWordsEF())
    if smem.semantic is None:
        check("semantic store initializes", False)
    else:
        check("semantic store initializes", True)
        smem.add_fact("My main client is Ali from XYZ Corp", "person")
        smem.add_fact("The project source code lives in D:/Projects/aria", "project")
        smem.add_fact("I prefer tea over coffee in the morning", "preference")
        hits = smem.recall_facts("project source code in Projects", limit=3)
        top = hits[0]["fact"].lower() if hits else ""
        print(f"    top hit: {top!r}")
        check("semantic recall returns results", len(hits) > 0)
        check("semantic recall ranks the code fact first", "d:/projects" in top)
    smem.close()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
except ImportError:
    print("  [SKIP] chromadb not installed")

print("== screenshot (display-dependent; optional) ==")
try:
    from modules.system.screen import take_screenshot
    res = take_screenshot(ocr=False)
    if "error" in res:
        print(f"  [SKIP] screenshot unavailable: {res['error']}")
    else:
        check("screenshot saved", Path(res["path"]).exists())
except Exception as e:  # noqa: BLE001
    print(f"  [SKIP] screenshot: {e}")

mem.close()
print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL PHASE 6 SMOKE CHECKS PASSED")
