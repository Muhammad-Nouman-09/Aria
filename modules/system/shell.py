"""Shell command executor (PowerShell / CMD).

Runs commands with a timeout and captures combined output. Output is
truncated before it is handed back to Claude so a noisy command can't blow
the context budget. Safety screening (blocklist) lives in the permission
manager, which gates this call before it ever runs.
"""

from __future__ import annotations

import subprocess

MAX_OUTPUT_CHARS = 10_000


def run_shell_command(command: str, shell: str = "powershell",
                      working_directory: str | None = None,
                      timeout_seconds: int = 30) -> dict:
    """Execute a command and return {exit_code, stdout, stderr, truncated}."""
    if shell == "cmd":
        args = ["cmd", "/c", command]
    else:
        args = [
            "powershell", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-Command", command,
        ]

    try:
        proc = subprocess.run(
            args,
            cwd=working_directory or None,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout, t1 = _truncate(proc.stdout or "")
        stderr, t2 = _truncate(proc.stderr or "")
        return {
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": t1 or t2,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": f"Command timed out after {timeout_seconds}s.",
            "truncated": False,
        }
    except FileNotFoundError as e:
        return {
            "exit_code": None,
            "stdout": "",
            "stderr": f"Shell not available: {e}",
            "truncated": False,
        }


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[:MAX_OUTPUT_CHARS] + "\n...[output truncated]", True
