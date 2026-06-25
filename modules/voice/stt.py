"""Speech-to-text with faster-whisper, plus mic capture via sounddevice.

The Whisper model is lazy-loaded on first use and cached under data/models.
`record_until_silence()` captures from the default mic and stops after a
short trailing silence (simple energy-based VAD), so the user can just speak
and pause. CPU int8 inference keeps it light (no GPU / PyTorch required).
"""

from __future__ import annotations

import os

import numpy as np

from config import MODELS_DIR, Settings

# Quiet the benign Windows symlink warning from the HF model cache.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

SAMPLE_RATE = 16_000


class STT:
    def __init__(self, settings: Settings):
        self.model_size = settings.whisper_model
        self.sample_rate = SAMPLE_RATE
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size, device="cpu", compute_type="int8",
                download_root=str(MODELS_DIR),
            )
        return self._model

    # ----- transcription -----
    def transcribe_file(self, path: str) -> str:
        model = self._ensure_model()
        segments, _ = model.transcribe(path, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe_array(self, samples: "np.ndarray") -> str:
        model = self._ensure_model()
        audio = np.asarray(samples, dtype=np.float32).flatten()
        segments, _ = model.transcribe(audio, vad_filter=True)
        return " ".join(s.text.strip() for s in segments).strip()

    # ----- capture -----
    def record_until_silence(self, max_seconds: float = 15.0,
                             silence_seconds: float = 1.0,
                             threshold: float = 0.012,
                             min_speech_seconds: float = 0.3) -> "np.ndarray":
        """Record mono 16 kHz audio until the user stops speaking."""
        import sounddevice as sd

        block = int(0.03 * self.sample_rate)  # 30 ms blocks
        max_blocks = int(max_seconds / 0.03)
        silence_blocks_needed = int(silence_seconds / 0.03)
        min_speech_blocks = int(min_speech_seconds / 0.03)

        collected: list[np.ndarray] = []
        speech_blocks = 0
        trailing_silence = 0
        started = False

        with sd.InputStream(samplerate=self.sample_rate, channels=1,
                            dtype="float32") as stream:
            for _ in range(max_blocks):
                data, _overflow = stream.read(block)
                frame = data[:, 0]
                collected.append(frame.copy())
                rms = float(np.sqrt(np.mean(frame ** 2)) + 1e-9)

                if rms >= threshold:
                    started = True
                    speech_blocks += 1
                    trailing_silence = 0
                elif started:
                    trailing_silence += 1
                    if (speech_blocks >= min_speech_blocks
                            and trailing_silence >= silence_blocks_needed):
                        break

        if not collected:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(collected).astype(np.float32)

    def listen(self, **kwargs) -> str:
        """Record from mic and return the transcription."""
        audio = self.record_until_silence(**kwargs)
        if audio.size == 0:
            return ""
        return self.transcribe_array(audio)
