"""Bridge between Qt's main-thread event loop and the agent's asyncio loop.

Qt runs on the main thread; the agent's coroutines run on a dedicated asyncio
loop in a background thread. `submit()` schedules a coroutine onto that loop
from any thread and returns a concurrent.futures.Future.
"""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Coroutine


class AsyncBridge:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="aria-asyncio")
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro: Coroutine) -> Future:
        """Schedule a coroutine on the background loop; returns a Future."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def stop(self) -> None:
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=2.0)
