"""Open applications by friendly name."""

from __future__ import annotations

import subprocess

# Friendly aliases -> launch target. Anything not listed is launched as-is
# through the shell's `start`, which resolves PATH and registered app paths.
ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "chrome": "chrome",
    "edge": "msedge",
    "firefox": "firefox",
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "excel": "excel",
    "word": "winword",
    "powerpoint": "powerpnt",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "paint": "mspaint.exe",
    "settings": "ms-settings:",
}


def open_application(app_name: str, arguments: str = "") -> dict:
    target = ALIASES.get(app_name.strip().lower(), app_name)
    # `start "" <target> <args>` works for exes, registered names, and URIs.
    cmd = ["cmd", "/c", "start", "", target]
    if arguments:
        cmd.append(arguments)
    try:
        subprocess.Popen(cmd, close_fds=True)
        return {"launched": target, "arguments": arguments}
    except Exception as e:
        return {"error": f"Failed to open '{app_name}': {e}"}
