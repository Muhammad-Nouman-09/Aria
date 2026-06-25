"""Assembles the system prompt from live context + recalled memory."""

from __future__ import annotations

import getpass
import os
from datetime import datetime

from core.memory import Memory
from modules.system.sysinfo import platform_summary

SYSTEM_TEMPLATE = """You are ARIA (Autonomous Responsive Intelligence Assistant), a personal AI assistant running locally on {user_name}'s Windows computer.

CURRENT CONTEXT:
- Date/Time: {datetime}
- Operating System: {os}
- Current User: {username}
- Current Directory: {cwd}
- Pending Reminders: {reminders}

RELEVANT MEMORIES:
{recalled_memories}

BEHAVIOR RULES:
- Before running any shell command, explain what it does in plain language.
- Before modifying or deleting any file, state the full path and what will change.
- If a task is ambiguous, ask ONE clarifying question before proceeding.
- Prefer PowerShell over CMD for Windows tasks.
- When writing code, write it to a file rather than just showing it.
- For complex multi-step tasks, explain your plan first, then execute step by step.
- If a web search would help answer a question, do it proactively.
- Keep voice responses concise (1-3 sentences). Detailed info goes to the chat window.
- Use "I" and speak naturally, like a capable assistant, not a robot.
- NEVER perform HIGH-risk actions without explicit per-action user approval.
- After completing a task, briefly summarize what was done.

CAPABILITIES:
You have access to tools for: shell commands, file R/W, web search & scraping,
system info, app control, clipboard, screenshots, reminders, todos, and email.
"""


def build_system_prompt(memory: Memory, user_input: str) -> str:
    user_name = memory.get_profile("name") or getpass.getuser()
    recalled = memory.recall_facts(user_input, limit=8)
    if recalled:
        mem_text = "\n".join(f"- [{f['category']}] {f['fact']}" for f in recalled)
    else:
        mem_text = "(none relevant)"

    return SYSTEM_TEMPLATE.format(
        user_name=user_name,
        datetime=datetime.now().strftime("%A, %d %B %Y, %I:%M %p"),
        os=platform_summary(),
        username=getpass.getuser(),
        cwd=os.getcwd(),
        reminders="(reminder engine arrives in Phase 6)",
        recalled_memories=mem_text,
    )
