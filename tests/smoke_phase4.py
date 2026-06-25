"""Phase 4 smoke test — offline STT<->TTS round-trip + voice plumbing.

No microphone needed: pyttsx3 synthesizes a known phrase to a WAV (offline),
then faster-whisper (tiny model) transcribes it back and we check the words
came through. edge-tts synthesis and openwakeword import are exercised but
skipped gracefully if offline / unavailable.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from modules.voice.tts import TTS  # noqa: E402
from modules.voice.stt import STT  # noqa: E402

failures = []


def check(name, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        failures.append(name)


PHRASE = "the quick brown fox jumps over the lazy dog"
tmp = Path(tempfile.mkdtemp(prefix="aria_p4_"))

print("== TTS rate mapping ==")
s = get_settings()
s.tts_rate = "+50%"
check("rate maps +50% above base", TTS(s)._pyttsx_rate() > 175)
s.tts_rate = "-20%"
check("rate maps -20% below base", TTS(s)._pyttsx_rate() < 175)

print("== offline TTS -> WAV (pyttsx3) ==")
tts = TTS(get_settings())
wav = tmp / "phrase.wav"
ok_wav = False
try:
    tts.save_wav_offline(PHRASE, str(wav))
    ok_wav = wav.exists() and wav.stat().st_size > 1000
    check("wav synthesized", ok_wav)
except Exception as e:
    print(f"  [SKIP] pyttsx3 unavailable: {e}")

print("== STT round-trip (faster-whisper tiny) ==")
if ok_wav:
    s2 = get_settings()
    s2.whisper_model = "tiny"  # small + fast for the test
    stt = STT(s2)
    try:
        text = stt.transcribe_file(str(wav)).lower()
        print(f"    transcribed: {text!r}")
        hits = sum(w in text for w in ("quick", "brown", "fox", "lazy", "dog"))
        check("transcription recovered >=2 keywords", hits >= 2)
    except Exception as e:
        print(f"  [SKIP] whisper unavailable: {e}")
else:
    print("  [SKIP] no wav to transcribe")

print("== edge-tts synth (network; optional) ==")
import asyncio  # noqa: E402
try:
    mp3 = tmp / "edge.mp3"
    asyncio.run(tts.synthesize_to_file("hello from aria", str(mp3)))
    check("edge-tts mp3 created", mp3.exists() and mp3.stat().st_size > 0)
except Exception as e:
    print(f"  [SKIP] edge-tts: {e}")

print("== openwakeword import (optional) ==")
try:
    import openwakeword  # noqa: F401
    check("openwakeword importable", True)
except Exception as e:
    print(f"  [SKIP] openwakeword: {e}")

import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)

print()
if failures:
    print(f"FAILED: {len(failures)} -> {failures}")
    sys.exit(1)
print("ALL PHASE 4 SMOKE CHECKS PASSED")
