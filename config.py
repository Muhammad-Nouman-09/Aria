"""ARIA configuration — Pydantic settings loaded from .env.

All runtime knobs live here. Defaults are sane for a Windows desktop so the
app can boot even with a minimal .env (only ANTHROPIC_API_KEY is required).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Project root = directory containing this file.
ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
CHROMA_DIR = DATA_DIR / "chroma"
MODELS_DIR = DATA_DIR / "models"
DB_PATH = DATA_DIR / "aria.db"
AUDIT_LOG_PATH = LOGS_DIR / "aria_audit.log"


def _split_csv(value) -> list[str]:
    """Accept either a comma-separated string or an already-parsed list."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- LLM provider (OpenRouter, OpenAI-compatible) -----
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    # Optional attribution headers OpenRouter shows on its dashboard.
    openrouter_site_url: str = Field(default="", alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str = Field(default="ARIA", alias="OPENROUTER_APP_NAME")
    # Kept for optional future use; not required.
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    # ----- Model (free, tool-capable OpenRouter model) -----
    model: str = Field(default="openai/gpt-oss-120b:free", alias="ARIA_MODEL")
    max_tokens: int = Field(default=4096, alias="MAX_TOKENS")

    # ----- Voice (used in later phases) -----
    wake_word: str = Field(default="hey aria", alias="WAKE_WORD")
    # openwakeword pretrained model (or path to a custom .onnx/.tflite).
    # "hey aria" needs a custom-trained model; default to a bundled one.
    wakeword_model: str = Field(default="hey_jarvis", alias="WAKEWORD_MODEL")
    wakeword_threshold: float = Field(default=0.5, alias="WAKEWORD_THRESHOLD")
    whisper_model: str = Field(default="medium", alias="WHISPER_MODEL")
    tts_voice: str = Field(default="en-US-AriaNeural", alias="TTS_VOICE")
    tts_rate: str = Field(default="+0%", alias="TTS_RATE")
    voice_enabled: bool = Field(default=False, alias="VOICE_ENABLED")

    # ----- Permissions -----
    allow_shell_commands: bool = Field(default=True, alias="ALLOW_SHELL_COMMANDS")
    require_approval_for_shell: bool = Field(default=True, alias="REQUIRE_APPROVAL_FOR_SHELL")
    require_approval_for_file_write: bool = Field(default=True, alias="REQUIRE_APPROVAL_FOR_FILE_WRITE")
    require_approval_for_delete: bool = Field(default=True, alias="REQUIRE_APPROVAL_FOR_DELETE")
    allowed_directories: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_DIRECTORIES")
    blocked_directories: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [r"C:\Windows", r"C:\Program Files", r"C:\Program Files (x86)"],
        alias="BLOCKED_DIRECTORIES",
    )

    # ----- Web -----
    web_search_enabled: bool = Field(default=True, alias="WEB_SEARCH_ENABLED")
    scraping_enabled: bool = Field(default=True, alias="SCRAPING_ENABLED")
    max_search_results: int = Field(default=5, alias="MAX_SEARCH_RESULTS")

    # ----- Memory -----
    conversation_history_limit: int = Field(default=50, alias="CONVERSATION_HISTORY_LIMIT")
    semantic_memory_enabled: bool = Field(default=True, alias="SEMANTIC_MEMORY_ENABLED")

    # ----- UI -----
    hotkey: str = Field(default="ctrl+shift+a", alias="HOTKEY")
    startup_with_windows: bool = Field(default=False, alias="STARTUP_WITH_WINDOWS")
    minimize_to_tray: bool = Field(default=True, alias="MINIMIZE_TO_TRAY")

    # ----- Scheduling -----
    reminder_check_interval_seconds: int = Field(default=30, alias="REMINDER_CHECK_INTERVAL_SECONDS")

    # ----- Email (optional, Phase 7) -----
    email_enabled: bool = Field(default=False, alias="EMAIL_ENABLED")
    email_address: str = Field(default="", alias="EMAIL_ADDRESS")
    email_password: str = Field(default="", alias="EMAIL_PASSWORD")
    imap_host: str = Field(default="", alias="IMAP_HOST")
    imap_port: int = Field(default=993, alias="IMAP_PORT")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")

    @field_validator("allowed_directories", "blocked_directories", mode="before")
    @classmethod
    def _parse_dir_lists(cls, v):
        return _split_csv(v)

    @property
    def has_api_key(self) -> bool:
        key = (self.openrouter_api_key or "").strip()
        return bool(key) and key != "your_key_here"

    @property
    def has_email(self) -> bool:
        return bool(self.email_enabled and self.email_address
                    and self.email_password and self.imap_host)

    def ensure_dirs(self) -> None:
        """Create the data/log/model directories if they do not exist."""
        for d in (DATA_DIR, LOGS_DIR, CHROMA_DIR, MODELS_DIR):
            d.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def update_env_value(key: str, value: str, env_path: Path | None = None) -> None:
    """Insert or update a KEY=value line in the .env file, preserving the rest."""
    path = Path(env_path) if env_path is not None else ENV_PATH
    line = f"{key}={value}"
    if not path.exists():
        path.write_text(line + "\n", encoding="utf-8")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    replaced = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith(prefix):
            lines[i] = line
            replaced = True
            break
    if not replaced:
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_settings() -> Settings:
    """Return a cached Settings instance, creating data dirs on first load."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings
