"""ARIA agent loop — text-in, text-out, with Claude tool use.

Maintains an in-process message history for multi-turn conversation, persists
user/assistant turns to SQLite, recalls relevant memories into the system
prompt, and drives the tool-use loop until Claude returns a final answer.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Callable

from config import CHROMA_DIR, DB_PATH, Settings, get_settings
from core.context_builder import build_system_prompt
from core.llm import LLMClient
from core.memory import Memory
from core.permissions import PermissionManager
from core.tools import ToolContext, execute_tool

# Callback the UI/CLI can supply to observe tool activity.
# Signature: on_tool(phase: str, name: str, info: str)
ToolObserver = Callable[[str, str, str], None]

MAX_TOOL_ITERATIONS = 12


class Agent:
    def __init__(self, settings: Settings | None = None,
                 approver=None, on_tool: ToolObserver | None = None,
                 on_reminder: Callable[[str], None] | None = None):
        self.settings = settings or get_settings()
        self.memory = Memory(
            DB_PATH,
            semantic=self.settings.semantic_memory_enabled,
            chroma_dir=CHROMA_DIR,
        )
        self.permissions = PermissionManager(self.settings, approver=approver)
        self.llm = LLMClient(self.settings)
        self.on_tool = on_tool
        self.session_id = uuid.uuid4().hex

        # Reminder scheduler (Phase 6). Best-effort: if APScheduler is missing
        # the agent still runs, set_reminder just reports it's unavailable.
        self.scheduler = None
        try:
            from modules.tasks.scheduler import ReminderScheduler
            self.scheduler = ReminderScheduler(
                self.memory, on_fire=on_reminder or _default_reminder)
            self.scheduler.start()
        except Exception:
            self.scheduler = None

        self.ctx = ToolContext(self.settings, self.memory, self.permissions,
                               scheduler=self.scheduler)
        # Structured running history for the tool-use loop.
        self.messages: list[dict] = []

    def close(self) -> None:
        if self.scheduler is not None:
            try:
                self.scheduler.shutdown()
            except Exception:
                pass
        self.memory.close()

    def _notify(self, phase: str, name: str, info: str = "") -> None:
        if self.on_tool:
            try:
                self.on_tool(phase, name, info)
            except Exception:
                pass

    async def run(self, user_input: str, source: str = "text") -> str:
        self.memory.add_message(self.session_id, "user", user_input)
        self.messages.append({"role": "user", "content": user_input})

        system_prompt = build_system_prompt(self.memory, user_input)
        final_text = ""

        for _ in range(MAX_TOOL_ITERATIONS):
            message = await self.llm.create(system_prompt, self.messages)
            tool_calls = message.tool_calls or []

            # Record the assistant turn in OpenAI history shape.
            assistant_msg: dict = {"role": "assistant",
                                   "content": message.content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            self.messages.append(assistant_msg)

            if message.content:
                final_text = message.content  # latest assistant text wins

            if not tool_calls:
                break

            # Execute each tool call and append a role:tool result per call.
            for tc in tool_calls:
                name = tc.function.name
                args = _parse_args(tc.function.arguments)
                self._notify("start", name, _short(args))
                result = await asyncio.to_thread(
                    execute_tool, name, args, self.ctx
                )
                self._notify("end", name, _short(result))
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        final_text = (final_text or "").strip() or "(no response)"
        self.memory.add_message(self.session_id, "assistant", final_text)
        return final_text


def _default_reminder(message: str) -> None:
    """Console reminder notifier; the GUI/voice layers can supply their own."""
    print(f"\n\033[1;33m[REMINDER] {message}\033[0m\n")


def _parse_args(raw) -> dict:
    """Tool-call arguments arrive as a JSON string; tolerate junk."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _short(obj, limit: int = 120) -> str:
    s = str(obj)
    return s if len(s) <= limit else s[:limit] + "..."
