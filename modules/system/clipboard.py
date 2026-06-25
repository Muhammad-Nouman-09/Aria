"""Clipboard read/write via pyperclip."""

from __future__ import annotations

try:
    import pyperclip
except ImportError:  # pragma: no cover
    pyperclip = None  # type: ignore


def clipboard_read() -> str:
    if pyperclip is None:
        raise RuntimeError("pyperclip is not installed.")
    return pyperclip.paste()


def clipboard_write(content: str) -> None:
    if pyperclip is None:
        raise RuntimeError("pyperclip is not installed.")
    pyperclip.copy(content)
