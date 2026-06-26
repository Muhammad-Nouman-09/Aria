# ARIA — Autonomous Responsive Intelligence Assistant

A fully local, voice + text AI assistant for Windows. The reasoning brain is
an LLM accessed via **OpenRouter** (OpenAI-compatible), defaulting to a free,
tool-capable model. A permission gate sits in front of every system action.

Implements **all 7 phases** of the build spec (`CLAUDE.md`): config, LLM client
+ a 21-tool catalogue, SQLite + ChromaDB semantic memory, the async tool-use
agent loop, a text CLI, filesystem read/write, web search/scrape/download, a
voice engine (local STT, TTS, wake word), a PyQt6 GUI with system tray +
permission dialog + settings + audit viewer, APScheduler reminders, to-dos,
screenshots, optional IMAP/SMTP email, run-at-startup, and PyInstaller packaging.

---

## Quick start (step by step)

All commands are **PowerShell**, run from the project root (`E:\Aria`).

### 0. Prerequisites

- Windows 10/11.
- **Python 3.12** (or 3.11). The system default 3.14 will **not** work — several
  dependencies (chromadb, faster-whisper, PyQt6) have no 3.14 wheels yet.
- An **OpenRouter API key** — free to create at <https://openrouter.ai/keys>.

Check which Python versions are installed:

```powershell
py -0p
```

If you don't see a 3.12 entry, install it from <https://www.python.org/downloads/release/python-3127/>
(the "Windows installer (64-bit)"), then re-check with `py -0p`.

### 1. Go to the project folder

```powershell
cd E:\Aria
```

### 2. Create and activate a virtual environment (Python 3.12)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation is blocked by execution policy, allow it for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

> Tip: you can skip activation and call the venv Python directly anywhere below
> by replacing `python` with `.\.venv\Scripts\python.exe`.

### 3. Upgrade pip

```powershell
python -m pip install --upgrade pip
```

### 4. Install dependencies

Pick **one** of the following, depending on what you want to run.

```powershell
# A) Minimal — text CLI only (fastest install)
pip install -r requirements-phase1.txt

# B) GUI — adds the PyQt6 desktop app
pip install -r requirements-phase1.txt
pip install PyQt6

# C) Voice — adds local STT/TTS/wake word (large download)
pip install -r requirements-phase1.txt
pip install -r requirements-voice.txt

# D) Everything (GUI + voice + scraping + semantic memory + email + scheduler)
pip install -r requirements.txt
```

Optional extras:

```powershell
# JavaScript-rendered scraping (otherwise ARIA uses a static fetch)
pip install playwright
playwright install chromium

# OCR for screenshots — also install the Tesseract binary and put it on PATH
pip install pytesseract
```

### 5. Configure `.env`

```powershell
copy .env.example .env
notepad .env
```

In `.env`, set at minimum:

```env
OPENROUTER_API_KEY=sk-or-...your key...
ARIA_MODEL=openai/gpt-oss-120b:free          # any ":free" model that supports tools
ALLOWED_DIRECTORIES=C:\Users\<you>\Documents,C:\Users\<you>\Desktop
```

Optional sections in the same file: voice (`WHISPER_MODEL`, `TTS_VOICE`,
`WAKEWORD_MODEL`), email (`EMAIL_ENABLED=true` + `EMAIL_ADDRESS` /
`EMAIL_PASSWORD` (app password) / `IMAP_HOST` / `SMTP_HOST`), and permission
toggles (`REQUIRE_APPROVAL_FOR_SHELL`, etc.).

### 6. Run ARIA

```powershell
# GUI chat window + system tray (default)
python main.py

# Text CLI
python main.py --cli

# Voice, push-to-talk (press Enter, speak, pause to send)
python main.py --voice

# Voice with always-on wake word (default "hey_jarvis")
python main.py --voice --wake
```

> If you didn't activate the venv: `\.venv\Scripts\python.exe main.py`

**First run downloads models** (one time, cached afterward): the Whisper model
for `--voice`, the ChromaDB embedding model for semantic memory, and the
openwakeword models for `--wake`. These can take a while on a slow connection.

### 7. Try it

Type or say:

- "What's my CPU usage?"
- "Search the web for the latest Python release"
- "Make a folder called Reports on my Desktop"  *(asks for approval first)*
- "Remember that my projects live in D:\Projects"
- "Add 'pay invoice' to my todos"
- "Remind me in 10 minutes to take a break"

---

## Verify the install (optional)

Run the smoke-test suites — they pass **without** an API key:

```powershell
# GUI suites need the offscreen Qt platform
$env:QT_QPA_PLATFORM = "offscreen"

python tests\smoke_phase1.py
python tests\smoke_phase2.py
python tests\smoke_phase3.py
python tests\smoke_agent_loop.py
python tests\smoke_phase4.py     # downloads the tiny Whisper model once
python tests\smoke_phase5.py
python tests\smoke_phase6.py
python tests\smoke_phase7.py
```

Each ends with `ALL ... SMOKE CHECKS PASSED`.

---

## Build a standalone Windows app (optional)

Produces `dist\ARIA\ARIA.exe` (one-folder build) via PyInstaller:

```powershell
.\build.ps1
```

Then copy your `.env` next to `ARIA.exe` before the first launch. (The build is
large and may need network access for first-run model downloads, same as above.)

---

## Modes & architecture

- **GUI** (`python main.py`): dark chat window, collapsible tool-call lines, a
  status indicator, optional mic + spoken replies, a **Tools** menu (Settings,
  Audit log), and a system tray icon. Qt runs on the main thread; the agent runs
  on a background asyncio loop (`ui/async_bridge.py`), results marshalled back via
  Qt signals. HIGH-risk actions raise a modal **Approve/Deny** dialog on the GUI
  thread while the tool worker blocks for the answer.
- **CLI** (`--cli`): same agent, console approval prompts.
- **Voice** (`--voice` / `--voice --wake`): faster-whisper STT, edge-tts neural
  TTS (offline pyttsx3 fallback), openwakeword hotword.

### Permission model

Every tool call is risk-classified and gated:

| Risk | Behaviour | Examples |
|------|-----------|----------|
| LOW | auto-approve | read file, list dir, web search, system info, recall |
| MEDIUM | ask once per session | open app, clipboard write, remember fact, set reminder |
| HIGH | always ask, with preview | shell commands, write/move/delete file, send email |
| BLOCKED | refused | dangerous shell patterns, paths outside `ALLOWED_DIRECTORIES` |

Dangerous shell patterns (`format c:`, `rm -rf /`, `shutdown`, …) are blocked
outright; file tools are confined to `ALLOWED_DIRECTORIES` and refuse
`BLOCKED_DIRECTORIES`; permanent deletion is disabled (deletes go to the Recycle
Bin); every action is written to `data/logs` and the `audit_log` table.

---

## Project layout

```
main.py              Entry point (--gui default, --cli, --voice, --wake)
config.py            Pydantic settings (.env) + .env upsert helper
core/
  agent.py           Async agent loop (OpenAI-format tool-use)
  llm.py             OpenRouter client + tool schemas (+ OpenAI conversion)
  memory.py          SQLite persistence (+ semantic recall hook)
  semantic.py        ChromaDB semantic store (injectable embedder)
  permissions.py     Risk-based permission gate
  tools.py           Tool dispatch + audit
  context_builder.py System prompt assembly
modules/
  web/               search (DDG), scraper (httpx+bs4/playwright), download
  system/            shell, sysinfo, apps, clipboard, screen, startup
  filesystem/        reader (read/list/search), writer (write/move/delete)
  voice/             stt (faster-whisper), tts (edge-tts/pyttsx3),
                     wake_word (openwakeword), session
  tasks/             scheduler (APScheduler reminders), todo
  integrations/      email (IMAP/SMTP)
ui/                  main_window, tray, permission_dialog, settings_dialog,
                     audit_dialog, async_bridge, icon
tests/               smoke_phase1..7 + smoke_agent_loop
data/                aria.db, logs/, models/, chroma/ (created at runtime)
aria.spec, build.ps1 PyInstaller packaging
```

---

## Troubleshooting

- **`OPENROUTER_API_KEY is not set`** — edit `.env` and set a real key (the
  placeholder `your_key_here` counts as unset).
- **`py -3.12` not found** — install Python 3.12 (see step 0); the default 3.14
  is missing wheels for chromadb / faster-whisper / PyQt6.
- **Activation blocked** — run the `Set-ExecutionPolicy` line in step 2.
- **Voice does nothing / no mic** — confirm a default recording device exists;
  `--voice` needs a microphone. STT/TTS still work for file round-trips.
- **Wake word never triggers** — the bundled model is `hey_jarvis`, not "hey
  aria"; say that, lower `WAKEWORD_THRESHOLD`, or train a custom model and point
  `WAKEWORD_MODEL` at its `.onnx`/`.tflite`.
- **Slow first run** — model downloads (Whisper, Chroma embedder, wake word) are
  one-time and cached under `data/models` and your user cache.
```
