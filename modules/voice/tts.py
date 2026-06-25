"""Text-to-speech: edge-tts (online neural) primary, pyttsx3 (offline) fallback.

`speak()` is synchronous and best-effort: it tries edge-tts (synthesize an
mp3 and play it), and on any failure falls back to pyttsx3, which uses the
Windows SAPI5 voices and always works offline. `synthesize_to_file()` and
`save_wav_offline()` are provided for testing and for saving audio.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

from config import Settings


class TTS:
    def __init__(self, settings: Settings):
        self.voice = settings.tts_voice
        self.rate = settings.tts_rate or "+0%"
        self._pyttsx_engine = None

    # ----- public -----
    def speak(self, text: str) -> str:
        """Speak text aloud. Returns the backend used ('edge'|'pyttsx3'|'none')."""
        text = (text or "").strip()
        if not text:
            return "none"
        if self._speak_edge(text):
            return "edge"
        if self._speak_pyttsx(text):
            return "pyttsx3"
        return "none"

    async def synthesize_to_file(self, text: str, out_path: str) -> str:
        """edge-tts -> mp3 file (async). Raises if edge-tts unavailable."""
        import edge_tts
        comm = edge_tts.Communicate(text, self.voice, rate=self.rate)
        await comm.save(out_path)
        return out_path

    def save_wav_offline(self, text: str, out_path: str) -> str:
        """pyttsx3 -> wav file, fully offline. Useful for tests."""
        engine = self._get_pyttsx()
        engine.save_to_file(text, out_path)
        engine.runAndWait()
        return out_path

    # ----- backends -----
    def _speak_edge(self, text: str) -> bool:
        try:
            tmp = Path(tempfile.gettempdir()) / "aria_tts.mp3"
            asyncio.run(self.synthesize_to_file(text, str(tmp)))
            if not tmp.exists() or tmp.stat().st_size == 0:
                return False
            from playsound3 import playsound
            playsound(str(tmp))
            return True
        except Exception:
            return False

    def _speak_pyttsx(self, text: str) -> bool:
        try:
            engine = self._get_pyttsx()
            engine.setProperty("rate", self._pyttsx_rate())
            engine.say(text)
            engine.runAndWait()
            return True
        except Exception:
            return False

    def _get_pyttsx(self):
        if self._pyttsx_engine is None:
            import pyttsx3
            self._pyttsx_engine = pyttsx3.init()
        return self._pyttsx_engine

    def _pyttsx_rate(self) -> int:
        """Map an edge-style '+10%' string to pyttsx3 words-per-minute."""
        base = 175
        m = re.match(r"([+-]?\d+)%", self.rate.strip())
        if not m:
            return base
        return int(base * (1 + int(m.group(1)) / 100))
