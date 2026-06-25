"""ARIA entry point.

  python main.py            GUI chat window + system tray (default)
  python main.py --cli      text CLI
  python main.py --voice    voice mode (push-to-talk: Enter, then speak)
  python main.py --voice --wake   voice mode with always-on wake word
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from config import get_settings
from core.agent import Agent

BANNER = r"""
   _   ___ ___    _
  /_\ | _ \_ _|  /_\    ARIA — local AI assistant
 / _ \|   /| |  / _ \   text + voice
/_/ \_\_|_\___|/_/ \_\  type 'exit' or Ctrl+C to quit
"""


def _on_tool(phase: str, name: str, info: str) -> None:
    arrow = ">" if phase == "start" else "<"
    print(f"  \033[2m{arrow} {name}  {info}\033[0m")


def _require_key(settings) -> bool:
    if not settings.has_api_key:
        print("ERROR: OPENROUTER_API_KEY is not set.")
        print("Copy .env.example to .env and add your key, then retry.")
        return False
    return True


async def cli_loop() -> int:
    settings = get_settings()
    if not _require_key(settings):
        return 1

    print(BANNER)
    print(f"Model: {settings.model}\n")

    agent = Agent(settings=settings, on_tool=_on_tool)
    try:
        while True:
            try:
                user_input = await asyncio.to_thread(input, "you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", ":q"):
                break
            try:
                reply = await agent.run(user_input)
            except Exception as e:
                print(f"\n[agent error] {e}\n")
                continue
            print(f"\nARIA> {reply}\n")
    finally:
        agent.close()
    print("Goodbye.")
    return 0


async def voice_loop(use_wake: bool) -> int:
    settings = get_settings()
    if not _require_key(settings):
        return 1

    from modules.voice.session import VoiceSession

    print(BANNER)
    print(f"Model: {settings.model}  |  Whisper: {settings.whisper_model}  |  Voice: {settings.tts_voice}")
    print("Loading speech model (first run downloads it)...")

    agent = Agent(settings=settings, on_tool=_on_tool)
    voice = VoiceSession(settings)
    try:
        await asyncio.to_thread(voice.warm_up)
    except Exception as e:
        print(f"[voice] Could not load the STT model: {e}")
        agent.close()
        return 1

    wake_q = None
    if use_wake:
        try:
            wake_q = await asyncio.to_thread(voice.make_wake_queue)
            print(f"Wake word active ('{settings.wakeword_model}'). Say it to talk.\n")
        except Exception as e:
            print(f"[voice] Wake word unavailable ({e}); falling back to push-to-talk.\n")
            use_wake = False

    try:
        while True:
            try:
                if use_wake and wake_q is not None:
                    print("(listening for wake word... Ctrl+C to quit)")
                    await asyncio.to_thread(wake_q.get)
                    print("Wake word detected — listening...")
                else:
                    cmd = await asyncio.to_thread(
                        input, "[Enter]=talk, 'q'=quit > ")
                    if cmd.strip().lower() in ("q", "quit", "exit"):
                        break

                text = await asyncio.to_thread(voice.listen_once)
            except (EOFError, KeyboardInterrupt):
                print()
                break

            text = (text or "").strip()
            if not text:
                print("(heard nothing)\n")
                continue
            print(f"\nyou (voice)> {text}")
            try:
                reply = await agent.run(text, source="voice")
            except Exception as e:
                print(f"\n[agent error] {e}\n")
                continue
            print(f"ARIA> {reply}\n")
            await asyncio.to_thread(voice.speak, reply)
    finally:
        voice.stop_wake()
        agent.close()
    print("Goodbye.")
    return 0


def run_gui() -> int:
    settings = get_settings()
    if not _require_key(settings):
        return 1

    from PyQt6.QtWidgets import QApplication

    from ui.async_bridge import AsyncBridge
    from ui.main_window import MainWindow
    from ui.tray import Tray

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # keep running in tray

    bridge = AsyncBridge()
    window = MainWindow(settings, bridge=bridge)
    tray = Tray(window, app)
    tray.show()
    window.show()
    return app.exec()


def main() -> int:
    parser = argparse.ArgumentParser(description="ARIA assistant")
    parser.add_argument("--gui", action="store_true",
                        help="Run the PyQt6 GUI + tray (default).")
    parser.add_argument("--cli", action="store_true",
                        help="Run the text CLI.")
    parser.add_argument("--voice", action="store_true",
                        help="Run in voice mode (push-to-talk).")
    parser.add_argument("--wake", action="store_true",
                        help="With --voice, use always-on wake word.")
    args = parser.parse_args()

    if args.voice:
        return asyncio.run(voice_loop(use_wake=args.wake))
    if args.cli:
        return asyncio.run(cli_loop())
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
