"""Voice session: bundles STT + TTS (+ optional wake word) for the CLI.

Keeps the heavy objects in one place and exposes simple blocking helpers the
async CLI calls via asyncio.to_thread.
"""

from __future__ import annotations

import queue
from typing import Optional

from config import Settings
from modules.voice.stt import STT
from modules.voice.tts import TTS


class VoiceSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.stt = STT(settings)
        self.tts = TTS(settings)
        self._wake = None

    def warm_up(self) -> None:
        """Load the Whisper model up front so the first utterance isn't slow."""
        self.stt._ensure_model()

    def listen_once(self) -> str:
        return self.stt.listen()

    def speak(self, text: str) -> str:
        return self.tts.speak(text)

    # ----- wake word -----
    def make_wake_queue(self) -> "queue.Queue":
        """Start the wake-word listener; returns a queue that gets an item
        each time the wake word fires. Raises if openwakeword is unavailable.
        """
        from modules.voice.wake_word import WakeWordListener

        q: "queue.Queue" = queue.Queue()
        self._wake = WakeWordListener(
            self.settings,
            on_detect=lambda: q.put_nowait("wake"),
            threshold=self.settings.wakeword_threshold,
        )
        self._wake.start()
        return q

    def stop_wake(self) -> None:
        if self._wake:
            self._wake.stop()
            self._wake = None
