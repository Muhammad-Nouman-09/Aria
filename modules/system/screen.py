"""Screenshots (Pillow ImageGrab) with optional OCR (pytesseract).

OCR needs the Tesseract binary installed on the system; if it's missing we
still return the saved image path and a clear note instead of failing.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path


def take_screenshot(save_path: str | None = None, ocr: bool = False) -> dict:
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"error": "Pillow is not installed (pip install Pillow)."}

    try:
        img = ImageGrab.grab()
    except Exception as e:
        return {"error": f"Could not capture screen: {e}"}

    if not save_path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = str(Path(tempfile.gettempdir()) / f"aria_screen_{stamp}.png")
    try:
        img.save(save_path)
    except Exception as e:
        return {"error": f"Could not save screenshot: {e}"}

    out = {"path": save_path, "size": list(img.size)}

    if ocr:
        try:
            import pytesseract
            text = pytesseract.image_to_string(img)
            out["text"] = text.strip()
        except ImportError:
            out["ocr_note"] = "pytesseract not installed."
        except Exception as e:
            out["ocr_note"] = (f"OCR unavailable ({e}). Install the Tesseract "
                               f"binary and ensure it's on PATH.")
    return out
