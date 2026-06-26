"""Run-at-startup control via the Windows registry (HKCU Run key).

Per-user, no admin required, fully reversible. Used by the settings screen to
toggle whether ARIA launches when the user logs in.
"""

from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_NAME = "ARIA"


def _default_command() -> str:
    # Launch the GUI with the current interpreter and main.py.
    from config import ROOT_DIR
    py = sys.executable
    return f'"{py}" "{ROOT_DIR / "main.py"}"'


def set_startup(enabled: bool, app_name: str = DEFAULT_NAME,
                command: str | None = None) -> dict:
    try:
        import winreg
    except ImportError:
        return {"error": "winreg unavailable (not on Windows)."}

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                             winreg.KEY_SET_VALUE)
    except FileNotFoundError:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY)

    try:
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ,
                              command or _default_command())
            return {"status": "enabled", "app": app_name}
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
            return {"status": "disabled", "app": app_name}
    finally:
        winreg.CloseKey(key)


def is_startup_enabled(app_name: str = DEFAULT_NAME) -> bool:
    try:
        import winreg
    except ImportError:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                             winreg.KEY_QUERY_VALUE)
    except FileNotFoundError:
        return False
    try:
        winreg.QueryValueEx(key, app_name)
        return True
    except FileNotFoundError:
        return False
    finally:
        winreg.CloseKey(key)
