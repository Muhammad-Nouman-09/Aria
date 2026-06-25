# ARIA — Autonomous Responsive Intelligence Assistant

A fully local, voice + text AI assistant for Windows. The reasoning brain is
an LLM accessed via **OpenRouter** (OpenAI-compatible), defaulting to a free,
tool-capable model. A permission gate sits in front of every system action.

This repository implements **Phases 1–5**: config, LLM client + full tool
catalogue, SQLite memory, the async tool-use agent loop, a text CLI, the full
filesystem read/write side, web scraping + downloads, the voice engine (local
STT, TTS, wake word), and a PyQt6 GUI with system tray and a visual
permission-approval dialog. Scheduling and integrations arrive in later phases
(see the build spec in `CLAUDE.md`).

## What works now

- PyQt6 GUI + system tray (`python main.py`) — dark chat UI, tool-call lines,
  visual Approve/Deny dialog for HIGH-risk actions, optional mic + spoken replies
- Text CLI chat with model tool use (`python main.py --cli`)
- LLM via OpenRouter free model (default `openai/gpt-oss-120b:free`, swappable)
- Persistent SQLite memory: conversation history, facts, to-dos, audit log
- Permission gate with risk levels (LOW auto / MEDIUM ask-once / HIGH always-ask / BLOCKED)
- Tools wired up: `run_shell_command`, `read_file`, `write_file`,
  `move_or_copy_file`, `delete_file` (Recycle Bin), `list_directory`,
  `search_files`, `get_system_info`, `web_search`, `scrape_webpage`,
  `download_file`, `clipboard_read/write`, `open_application`,
  `remember_fact`, `recall_memory`, `manage_todo`
- Voice (Phase 4): local STT (faster-whisper), TTS (edge-tts neural voices
  with an offline pyttsx3 fallback), and wake word (openwakeword). Run with
  `python main.py --voice` (push-to-talk) or `--voice --wake`.
- Remaining tools (screenshots, reminders, email) are declared to the model
  but return a "coming in Phase N" message until built.

Notes:
- Phase 2 added the filesystem write side: `write_file` (write/append, text +
  .docx), `move_or_copy_file`, and `delete_file` (Recycle Bin via send2trash;
  permanent deletion disabled by default).
- Phase 3 scraping uses httpx + BeautifulSoup by default. JavaScript rendering
  (`wait_for_js=true`) is optional: `pip install playwright` then
  `playwright install chromium`; without it, ARIA falls back to the static
  fetch and says so.

## Setup

ARIA targets **Python 3.11 / 3.12** (heavy deps in later phases lack 3.14
wheels). From the project root:

```powershell
# Create and activate a venv (example assumes py launcher has 3.12)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Phase 1 dependencies only (fast)
pip install -r requirements-phase1.txt

# Configure
copy .env.example .env
#  ...then edit .env and set OPENROUTER_API_KEY (get one at openrouter.ai)
#  optionally change ARIA_MODEL to any ":free" model that supports tools
```

## Run

```powershell
python main.py --cli
```

Try: *"What's my CPU usage?"*, *"Search the web for the latest Python release"*,
*"Make a folder called Reports on my Desktop"* (will ask for approval),
*"Remember that my projects live in D:\Projects"*, *"Add 'pay invoice' to my todos"*.

## Layout

```
config.py            Pydantic settings (.env)
core/
  agent.py           Async agent loop (OpenAI-format tool-use)
  llm.py             OpenRouter client + tool schemas (+ OpenAI conversion)
  memory.py          SQLite persistence
  permissions.py     Risk-based permission gate
  tools.py           Tool dispatch + audit
  context_builder.py System prompt assembly
modules/
  web/               search (DDG), scraper (httpx+bs4/playwright), download
  system/            shell, sysinfo, apps, clipboard
  filesystem/        reader (read/list/search), writer (write/move/delete)
  voice/             stt (faster-whisper), tts (edge-tts/pyttsx3),
                     wake_word (openwakeword), session
ui/                  main_window, tray, permission_dialog, async_bridge, icon
data/                aria.db, logs/, models/ (created at runtime)
```

## GUI mode

```powershell
pip install PyQt6
python main.py            # default: chat window + tray
```

Qt runs on the main thread; the agent runs on a background asyncio loop
(`ui/async_bridge.py`), with results marshalled back via Qt signals. HIGH-risk
actions raise a modal Approve/Deny dialog on the GUI thread while the tool
worker blocks for the answer.

## Voice mode

```powershell
pip install -r requirements-voice.txt
python main.py --voice          # press Enter, speak, pause to send
python main.py --voice --wake   # always-on wake word ("hey_jarvis" by default)
```

First run downloads the Whisper model (set `WHISPER_MODEL`: tiny/base/small/
medium). The wake word defaults to `hey_jarvis`; a true "hey aria" hotword
needs a custom openwakeword model (point `WAKEWORD_MODEL` at the .onnx/.tflite).

Safety: dangerous shell patterns are blocked outright; file tools are confined
to `ALLOWED_DIRECTORIES` and refuse `BLOCKED_DIRECTORIES`; every action is
written to `data/logs` and the `audit_log` table.
```
