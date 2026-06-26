"""Reminder scheduling on top of APScheduler + SQLite.

Reminders persist in the `reminders` table and are (re)scheduled on startup,
so they survive restarts. `parse_when` turns natural-language time strings
("in 10 minutes", "tomorrow at 3pm", "2026-06-26 17:00") into a datetime.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Callable

from dateutil import parser as dtparser

from core.memory import Memory

_REL = re.compile(r"\bin\s+(\d+)\s+(second|minute|hour|day|week)s?\b", re.I)
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


def parse_when(text: str, now: datetime | None = None) -> datetime:
    """Best-effort natural-language -> datetime. Raises ValueError if hopeless."""
    now = now or datetime.now()
    raw = (text or "").strip()
    low = raw.lower()

    # "in N <unit>"
    m = _REL.search(low)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = {
            "second": timedelta(seconds=n),
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
        }[unit]
        return now + delta

    # "tomorrow [at] ..." / "today [at] ..."
    if "tomorrow" in low or "today" in low:
        base = now + timedelta(days=1) if "tomorrow" in low else now
        hour, minute = _extract_time(low, default=(9, 0))
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Fall back to dateutil (handles ISO, "June 26 5pm", "5pm", etc.)
    try:
        parsed = dtparser.parse(raw, fuzzy=True, default=now.replace(
            second=0, microsecond=0))
    except (ValueError, OverflowError) as e:
        raise ValueError(f"Could not understand time: {text!r}") from e

    # Time-only strings ("5pm") may resolve to earlier today; roll forward.
    if parsed <= now and (now - parsed) < timedelta(days=1):
        parsed += timedelta(days=1)
    return parsed


def _extract_time(text: str, default: tuple[int, int]) -> tuple[int, int]:
    # Avoid matching the day number in "tomorrow"; search after 'at' if present.
    frag = text.split("at", 1)[1] if " at " in f" {text} " else text
    m = _TIME.search(frag)
    if not m:
        return default
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return default
    return hour, minute


class ReminderScheduler:
    def __init__(self, memory: Memory, on_fire: Callable[[str], None]):
        from apscheduler.schedulers.background import BackgroundScheduler

        self.memory = memory
        self.on_fire = on_fire
        self.sched = BackgroundScheduler()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self.sched.start()
        self._started = True
        for row in self.memory.active_reminders():
            try:
                self._schedule(row["id"], row["message"],
                               datetime.fromisoformat(row["trigger_at"]),
                               row.get("repeat", "none"))
            except Exception:
                continue

    def add(self, message: str, when: datetime, repeat: str = "none") -> dict:
        rid = self.memory.add_reminder(message, when.isoformat(), repeat)
        self._schedule(rid, message, when, repeat)
        return {"id": rid, "trigger_at": when.isoformat(), "repeat": repeat}

    def _schedule(self, rid: int, message: str, when: datetime,
                  repeat: str) -> None:
        from apscheduler.triggers.date import DateTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        if repeat == "daily":
            trigger = IntervalTrigger(days=1, start_date=when)
        elif repeat == "weekly":
            trigger = IntervalTrigger(weeks=1, start_date=when)
        elif repeat == "monthly":
            trigger = IntervalTrigger(days=30, start_date=when)
        else:
            trigger = DateTrigger(run_date=when)

        self.sched.add_job(
            self._fire, trigger, args=[rid, message, repeat],
            id=f"rem-{rid}", replace_existing=True, misfire_grace_time=3600,
        )

    def _fire(self, rid: int, message: str, repeat: str) -> None:
        try:
            self.on_fire(message)
        finally:
            if repeat == "none":
                self.memory.set_reminder_status(rid, "fired")

    def shutdown(self) -> None:
        if self._started:
            self.sched.shutdown(wait=False)
            self._started = False
