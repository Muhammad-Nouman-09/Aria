"""Permission manager — gates every tool action ARIA wants to perform.

Risk levels:
  LOW     -> auto-approve (reads, web search, system info, recall)
  MEDIUM  -> ask once per session, then remember the approval for that tool
  HIGH    -> always ask, with a preview of exactly what will happen
  BLOCKED -> never run (dangerous shell patterns, paths outside allow-list)

The actual "ask the user" step is delegated to an *approver* callback so the
same logic works for the CLI (console prompt) and the future PyQt6 dialog.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

from config import Settings


class Risk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


# Tool -> baseline risk. Anything not listed defaults to MEDIUM (ask once).
TOOL_RISK: dict[str, Risk] = {
    # reads / info
    "read_file": Risk.LOW,
    "list_directory": Risk.LOW,
    "search_files": Risk.LOW,
    "get_system_info": Risk.LOW,
    "web_search": Risk.LOW,
    "scrape_webpage": Risk.LOW,
    "clipboard_read": Risk.LOW,
    "recall_memory": Risk.LOW,
    "manage_todo": Risk.LOW,
    "take_screenshot": Risk.LOW,
    # side effects, low stakes
    "remember_fact": Risk.MEDIUM,
    "set_reminder": Risk.MEDIUM,
    "clipboard_write": Risk.MEDIUM,
    "open_application": Risk.MEDIUM,
    "download_file": Risk.MEDIUM,
    # dangerous / irreversible
    "run_shell_command": Risk.HIGH,
    "write_file": Risk.HIGH,
    "move_or_copy_file": Risk.HIGH,
    "delete_file": Risk.HIGH,
    "send_email": Risk.HIGH,
}

# Shell commands matching any of these are refused outright.
DANGEROUS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bformat\b\s+[a-z]:",          # format C:
        r"del\s+/[fsq].*\b[a-z]:\\",      # del /f /s /q C:\
        r"rm\s+-rf?\s+[/~]",              # rm -rf /
        r"\bdrop\s+table\b",
        r"\bdrop\s+database\b",
        r"\bshutdown\b",
        r"\brestart-computer\b",
        r"\bstop-computer\b",
        r"\bmkfs\b",
        r"Remove-Item.*-Recurse.*-Force.*[Cc]:\\(Windows|Program)",
        r"\bcipher\s+/w",
        r"\bdiskpart\b",
    )
]


@dataclass
class Decision:
    allowed: bool
    risk: Risk
    needs_approval: bool
    reason: str = ""
    preview: str = ""


def _console_approver(action: str, preview: str) -> bool:
    """Default CLI approval prompt. Swapped for a GUI dialog later."""
    print("\n" + "=" * 60)
    print(f"  APPROVAL REQUIRED: {action}")
    print("-" * 60)
    print(preview)
    print("=" * 60)
    try:
        answer = input("  Approve? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


class PermissionManager:
    def __init__(self, settings: Settings,
                 approver: Callable[[str, str], bool] | None = None):
        self.settings = settings
        self.approver = approver or _console_approver
        # Tools the user approved this session (for MEDIUM "ask once").
        self._session_approved: set[str] = set()

    # ----- path helpers -----
    def _resolve(self, p: str) -> Path:
        return Path(p).expanduser().resolve()

    def is_path_blocked(self, path: str) -> bool:
        try:
            target = self._resolve(path)
        except Exception:
            return True
        for blocked in self.settings.blocked_directories:
            try:
                if target == self._resolve(blocked) or self._resolve(blocked) in target.parents:
                    return True
            except Exception:
                continue
        return False

    def is_path_allowed(self, path: str) -> bool:
        """A path is allowed if it's not blocked and (when an allow-list is
        configured) sits inside one of the allowed directories.

        Reads are intentionally permissive; write/delete callers should pass
        for_write=True via check_path() to enforce the allow-list strictly.
        """
        if self.is_path_blocked(path):
            return False
        if not self.settings.allowed_directories:
            return True
        try:
            target = self._resolve(path)
        except Exception:
            return False
        for allowed in self.settings.allowed_directories:
            try:
                a = self._resolve(allowed)
                if target == a or a in target.parents:
                    return True
            except Exception:
                continue
        return False

    # ----- core check -----
    def check(self, tool_name: str, tool_input: dict, preview: str = "") -> Decision:
        risk = TOOL_RISK.get(tool_name, Risk.MEDIUM)

        # Shell-specific hard gates.
        if tool_name == "run_shell_command":
            if not self.settings.allow_shell_commands:
                return Decision(False, Risk.BLOCKED, False,
                                "Shell commands are disabled in settings.")
            cmd = str(tool_input.get("command", ""))
            for pat in DANGEROUS_PATTERNS:
                if pat.search(cmd):
                    return Decision(False, Risk.BLOCKED, False,
                                    f"Command matches a blocked pattern: {pat.pattern}")

        # Path gates for file-touching tools.
        path_keys = {
            "write_file": ["file_path"],
            "delete_file": ["path"],
            "move_or_copy_file": ["source_path", "destination_path"],
        }
        for key in path_keys.get(tool_name, []):
            val = tool_input.get(key)
            if val and self.is_path_blocked(str(val)):
                return Decision(False, Risk.BLOCKED, False,
                                f"Path is in a blocked directory: {val}")
            if val and self.settings.allowed_directories and not self.is_path_allowed(str(val)):
                return Decision(False, Risk.BLOCKED, False,
                                f"Path is outside ALLOWED_DIRECTORIES: {val}")

        # Decide whether approval is needed.
        needs = self._needs_approval(tool_name, risk)
        return Decision(allowed=True, risk=risk, needs_approval=needs, preview=preview)

    def _needs_approval(self, tool_name: str, risk: Risk) -> bool:
        if risk == Risk.LOW:
            return False
        if risk == Risk.HIGH:
            # Respect per-category config flags.
            if tool_name == "run_shell_command":
                return self.settings.require_approval_for_shell
            if tool_name in ("write_file", "move_or_copy_file"):
                return self.settings.require_approval_for_file_write
            if tool_name == "delete_file":
                return self.settings.require_approval_for_delete
            return True
        # MEDIUM: ask once per session.
        return tool_name not in self._session_approved

    def request_approval(self, tool_name: str, risk: Risk, preview: str) -> bool:
        ok = self.approver(tool_name, preview)
        if ok and risk == Risk.MEDIUM:
            self._session_approved.add(tool_name)
        return ok
