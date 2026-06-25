"""File writing, moving/copying, and deletion.

Phase 2. All callers are gated by the permission manager before reaching
here, but these functions still validate the basics (parent creation,
overwrite checks) and refuse permanent deletion by default — deletes go to
the Recycle Bin via send2trash.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Formats written natively as UTF-8 text. .docx gets special handling.
DOCX_SUFFIX = ".docx"


def write_file(file_path: str, content: str, mode: str = "write",
               encoding: str = "utf-8") -> dict:
    p = Path(file_path).expanduser()
    suffix = p.suffix.lower()

    try:
        p.parent.mkdir(parents=True, exist_ok=True)

        if suffix == DOCX_SUFFIX:
            if mode == "append":
                return {"error": "Append mode is not supported for .docx files."}
            return _write_docx(p, content)

        file_mode = "a" if mode == "append" else "w"
        with open(p, file_mode, encoding=encoding, newline="") as f:
            f.write(content)
        return {
            "status": "appended" if mode == "append" else "written",
            "path": str(p.resolve()),
            "bytes": len(content.encode(encoding, errors="replace")),
        }
    except Exception as e:
        return {"error": f"Failed to write {file_path}: {e}"}


def _write_docx(p: Path, content: str) -> dict:
    import docx  # python-docx
    doc = docx.Document()
    for line in content.split("\n"):
        doc.add_paragraph(line)
    doc.save(str(p))
    return {"status": "written", "path": str(p.resolve()), "format": "docx"}


def move_or_copy_file(source_path: str, destination_path: str,
                      operation: str, overwrite: bool = False) -> dict:
    src = Path(source_path).expanduser()
    dst = Path(destination_path).expanduser()

    if not src.exists():
        return {"error": f"Source not found: {source_path}"}

    # If the destination is an existing directory, drop the source name into it.
    if dst.is_dir():
        dst = dst / src.name

    if dst.exists() and not overwrite:
        return {"error": f"Destination already exists (set overwrite=true): {dst}"}

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if operation == "move":
            if dst.exists() and overwrite:
                _remove_existing(dst)
            shutil.move(str(src), str(dst))
        elif operation == "copy":
            if src.is_dir():
                if dst.exists() and overwrite:
                    _remove_existing(dst)
                shutil.copytree(str(src), str(dst))
            else:
                shutil.copy2(str(src), str(dst))
        else:
            return {"error": f"Unknown operation: {operation}"}
        return {"status": f"{operation}d", "source": str(src.resolve()),
                "destination": str(dst.resolve())}
    except Exception as e:
        return {"error": f"Failed to {operation} {source_path}: {e}"}


def _remove_existing(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def delete_file(path: str, send_to_recycle_bin: bool = True) -> dict:
    p = Path(path).expanduser()
    if not p.exists():
        return {"error": f"Path not found: {path}"}

    if not send_to_recycle_bin:
        # Permanent deletion is a blocked-by-default action.
        return {"error": "Permanent deletion is disabled. Deletes go to the "
                         "Recycle Bin (send_to_recycle_bin=true)."}

    try:
        from send2trash import send2trash
    except ImportError:
        return {"error": "send2trash is not installed (pip install send2trash)."}

    try:
        send2trash(str(p))
        return {"status": "sent to Recycle Bin", "path": str(p.resolve())}
    except Exception as e:
        return {"error": f"Failed to delete {path}: {e}"}
