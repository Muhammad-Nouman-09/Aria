"""Always-on wake-word detection via openwakeword (no API key).

Runs a blocking listen loop in a background thread, feeding 80 ms mic frames
to the model and firing a callback when the configured wake word scores above
threshold.

Note on "hey aria": openwakeword ships pretrained models such as
`hey_jarvis`, `alexa`, and `hey_mycroft`, but NOT "hey aria". A true
"hey aria" hotword requires training a custom model (see the openwakeword
docs) and pointing `WAKEWORD_MODEL` at the resulting .onnx/.tflite file. Until
then ARIA defaults to `hey_jarvis`.
"""

from __future__ import annotations

import threading
from typing import Callable

from config import Settings

FRAME = 1280  # 80 ms at 16 kHz, as openwakeword expects
SAMPLE_RATE = 16_000


class WakeWordListener:
    def __init__(self, settings: Settings, on_detect: Callable[[], None],
                 threshold: float = 0.5):
        self.model_name = settings.wakeword_model
        self.on_detect = on_detect
        self.threshold = threshold
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            import openwakeword
            from openwakeword.model import Model
            # Download the bundled pretrained models on first run.
            try:
                openwakeword.utils.download_models()
            except Exception:
                pass
            self._model = Model(wakeword_models=[self.model_name])
        return self._model

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        import numpy as np
        import sounddevice as sd

        model = self._ensure_model()
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="int16", blocksize=FRAME) as stream:
            while not self._stop.is_set():
                data, _ = stream.read(FRAME)
                scores = model.predict(np.asarray(data).flatten())
                score = scores.get(self.model_name)
                if score is None and scores:
                    score = max(scores.values())
                if score is not None and score >= self.threshold:
                    try:
                        self.on_detect()
                    except Exception:
                        pass
                    # brief debounce so one utterance fires once
                    for _ in range(int(0.8 * SAMPLE_RATE / FRAME)):
                        if self._stop.is_set():
                            break
                        stream.read(FRAME)
