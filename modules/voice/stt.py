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

# Quiet benign Hugging Face Hub noise during model downloads:
#  - symlink warning on Windows caches
#  - the "unauthenticated requests / set a HF_TOKEN" warning (downloads work
#    fine without a token; a token only raises rate limits).
# Set HF_TOKEN as an environment variable if you want higher download limits.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

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
    def transcribe_file(self, path: str, vad_filter: bool = True) -> str:
        model = self._ensure_model()
        segments, _ = model.transcribe(path, vad_filter=vad_filter)
        return " ".join(s.text.strip() for s in segments).strip()

    def transcribe_array(self, samples: "np.ndarray",
                         vad_filter: bool = False) -> str:
        # vad_filter defaults off here: live capture already trims silence, and
        # the Silero filter tends to drop quiet/short utterances entirely.
        model = self._ensure_model()
        audio = np.asarray(samples, dtype=np.float32).flatten()
        if audio.size == 0:
            return ""
        segments, _ = model.transcribe(audio, vad_filter=vad_filter)
        return " ".join(s.text.strip() for s in segments).strip()

    # ----- capture -----
    def _open_input_stream(self, sd):
        """Open a mono input stream at 16 kHz, falling back to the device's
        native rate (with later resampling) if 16 kHz is unsupported."""
        try:
            stream = sd.InputStream(samplerate=self.sample_rate, channels=1,
                                    dtype="float32")
            stream.start()
            return stream, self.sample_rate
        except Exception:
            try:
                dev = sd.default.device[0]
                native = int(sd.query_devices(dev)["default_samplerate"])
            except Exception:
                native = 44100
            stream = sd.InputStream(samplerate=native, channels=1,
                                    dtype="float32")
            stream.start()
            return stream, native

    def record_until_silence(self, start_timeout: float = 6.0,
                             max_phrase_seconds: float = 12.0,
                             silence_seconds: float = 0.8,
                             min_speech_seconds: float = 0.25) -> "np.ndarray":
        """Record one spoken phrase.

        Calibrates the ambient noise floor, waits up to ``start_timeout`` for
        speech to begin (returns empty if it never does — no long hang), then
        records until ``silence_seconds`` of trailing silence or
        ``max_phrase_seconds``, whichever comes first.
        """
        import sounddevice as sd

        block_dur = 0.03
        stream, in_sr = self._open_input_stream(sd)
        block = int(block_dur * in_sr)

        def rms(frame):
            return float(np.sqrt(np.mean(frame ** 2)) + 1e-9)

        try:
            # Calibrate noise floor over ~0.3 s of ambient audio.
            floor_samples = []
            for _ in range(int(0.3 / block_dur)):
                data, _ = stream.read(block)
                floor_samples.append(rms(data[:, 0]))
            noise = float(np.median(floor_samples)) if floor_samples else 1e-4
            threshold = max(noise * 4.0, 0.01)

            start_blocks = int(start_timeout / block_dur)
            max_blocks = int(max_phrase_seconds / block_dur)
            silence_blocks = int(silence_seconds / block_dur)
            min_speech_blocks = int(min_speech_seconds / block_dur)

            collected: list[np.ndarray] = []
            started = False
            speech = 0
            trailing = 0
            waited = 0

            while True:
                data, _ = stream.read(block)
                frame = data[:, 0]
                level = rms(frame)
                if not started:
                    waited += 1
                    if level >= threshold:
                        started = True
                        collected.append(frame.copy())
                        speech = 1
                    elif waited >= start_blocks:
                        break  # nobody spoke — bail out early
                else:
                    collected.append(frame.copy())
                    if level >= threshold:
                        speech += 1
                        trailing = 0
                    else:
                        trailing += 1
                        if speech >= min_speech_blocks and trailing >= silence_blocks:
                            break
                    if len(collected) >= max_blocks:
                        break
        finally:
            stream.stop()
            stream.close()

        if not collected:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(collected).astype(np.float32)
        if in_sr != self.sample_rate:
            audio = _resample(audio, in_sr, self.sample_rate)
        return audio

    def listen(self, **kwargs) -> str:
        """Record from mic and return the transcription."""
        audio = self.record_until_silence(**kwargs)
        if audio.size == 0:
            return ""
        return self.transcribe_array(audio)


def _resample(x: "np.ndarray", src: int, dst: int) -> "np.ndarray":
    if src == dst or x.size == 0:
        return x
    n = int(round(len(x) * dst / src))
    xp = np.arange(len(x))
    out = np.interp(np.linspace(0, len(x), n, endpoint=False), xp, x)
    return out.astype(np.float32)
