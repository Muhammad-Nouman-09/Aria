"""Persistent local memory for ARIA, backed by SQLite.

Phase 1 covers: conversation history, long-term facts (keyword search),
to-dos, reminders, an append-only audit log, and a user profile key/value
store. ChromaDB semantic search is layered on top in Phase 6 — the facts
table here is the source of truth either way.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    tool_calls TEXT
);

CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    category TEXT DEFAULT 'other',
    source TEXT DEFAULT 'user',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    trigger_at DATETIME NOT NULL,
    repeat TEXT DEFAULT 'none',
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    details TEXT,
    approved_by TEXT DEFAULT 'auto',
    result TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profile (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class Memory:
    """Thread-safe SQLite wrapper. One connection guarded by a lock."""

    def __init__(self, db_path: str | Path, semantic: bool = False,
                 chroma_dir: str | Path | None = None,
                 embedding_function=None):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

        # Optional ChromaDB semantic index. Falls back to keyword recall if
        # unavailable for any reason.
        self.semantic = None
        if semantic and chroma_dir is not None:
            try:
                from core.semantic import SemanticStore
                self.semantic = SemanticStore(chroma_dir, embedding_function)
                self._backfill_semantic()
            except Exception:
                self.semantic = None

    def _backfill_semantic(self) -> None:
        """Index any facts that predate the semantic store."""
        if self.semantic is None or self.semantic.count() > 0:
            return
        for row in self.all_facts(limit=1000):
            try:
                self.semantic.add(row["id"], row["fact"], row["category"])
            except Exception:
                break

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ----- Conversation history -----
    def add_message(self, session_id: str, role: str, content: str,
                    tool_calls: Any | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content,
                 json.dumps(tool_calls) if tool_calls is not None else None),
            )
            self._conn.commit()

    def recent_messages(self, limit: int = 50) -> list[dict]:
        """Most recent messages across all sessions, oldest-first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, timestamp FROM messages "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ----- Facts (long-term memory) -----
    def add_fact(self, fact: str, category: str = "other",
                 source: str = "user") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO facts (fact, category, source) VALUES (?, ?, ?)",
                (fact, category, source),
            )
            self._conn.commit()
            fact_id = int(cur.lastrowid)
        if self.semantic is not None:
            try:
                self.semantic.add(fact_id, fact, category)
            except Exception:
                pass
        return fact_id

    def recall_facts(self, query: str, limit: int = 10) -> list[dict]:
        """Recall relevant facts: semantic (ChromaDB) when available, else
        keyword matching."""
        if self.semantic is not None:
            try:
                results = self.semantic.query(query, k=limit)
                if results:
                    self._touch_facts([r["id"] for r in results])
                    return results
            except Exception:
                pass
        return self._recall_keyword(query, limit)

    def _touch_facts(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._conn.execute(
                f"UPDATE facts SET last_accessed = ? "
                f"WHERE id IN ({','.join('?' * len(ids))})",
                [datetime.now().isoformat(), *ids],
            )
            self._conn.commit()

    def _recall_keyword(self, query: str, limit: int = 10) -> list[dict]:
        """Keyword recall. Splits query into terms and OR-matches them."""
        terms = [t for t in query.lower().split() if len(t) > 2]
        with self._lock:
            if not terms:
                rows = self._conn.execute(
                    "SELECT id, fact, category FROM facts "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                clause = " OR ".join(["LOWER(fact) LIKE ?"] * len(terms))
                params = [f"%{t}%" for t in terms] + [limit]
                rows = self._conn.execute(
                    f"SELECT id, fact, category FROM facts WHERE {clause} "
                    f"ORDER BY id DESC LIMIT ?",
                    params,
                ).fetchall()
            if rows:
                ids = [r["id"] for r in rows]
                self._conn.execute(
                    f"UPDATE facts SET last_accessed = ? "
                    f"WHERE id IN ({','.join('?' * len(ids))})",
                    [datetime.now().isoformat(), *ids],
                )
                self._conn.commit()
        return [dict(r) for r in rows]

    def all_facts(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, fact, category FROM facts ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ----- To-dos -----
    def add_todo(self, task: str, priority: str = "medium") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO todos (task, priority) VALUES (?, ?)",
                (task, priority),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def list_todos(self, include_done: bool = False) -> list[dict]:
        with self._lock:
            if include_done:
                rows = self._conn.execute(
                    "SELECT * FROM todos ORDER BY status, id"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM todos WHERE status = 'pending' ORDER BY id"
                ).fetchall()
        return [dict(r) for r in rows]

    def complete_todo(self, task_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE todos SET status = 'done', completed_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (datetime.now().isoformat(), task_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_todo(self, task_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM todos WHERE id = ?", (task_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def clear_completed_todos(self) -> int:
        with self._lock:
            cur = self._conn.execute("DELETE FROM todos WHERE status = 'done'")
            self._conn.commit()
            return cur.rowcount

    # ----- Reminders -----
    def add_reminder(self, message: str, trigger_at: str,
                     repeat: str = "none") -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO reminders (message, trigger_at, repeat) "
                "VALUES (?, ?, ?)",
                (message, trigger_at, repeat),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def active_reminders(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM reminders WHERE status = 'active' "
                "ORDER BY trigger_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def set_reminder_status(self, reminder_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE reminders SET status = ? WHERE id = ?",
                (status, reminder_id),
            )
            self._conn.commit()

    # ----- Audit log -----
    def log_audit(self, action: str, details: dict | None = None,
                  approved_by: str = "auto", result: str = "success") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log (action, details, approved_by, result) "
                "VALUES (?, ?, ?, ?)",
                (action, json.dumps(details or {}), approved_by, result),
            )
            self._conn.commit()

    def recent_audit(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT timestamp, action, approved_by, result, details "
                "FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ----- User profile -----
    def set_profile(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO user_profile (key, value, updated_at) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, datetime.now().isoformat()),
            )
            self._conn.commit()

    def get_profile(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM user_profile WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default
