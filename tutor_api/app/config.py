"""Settings, read from environment variables so nothing secret lives in code."""
import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Used to sign login tokens. CHANGE THIS on the Pi (see README).
    secret_key: str = field(default_factory=lambda: _env("TUTOR_SECRET_KEY", "dev-only-change-me"))
    # Needed to create accounts and link parents to children (X-Admin-Key header).
    admin_key: str = field(default_factory=lambda: _env("TUTOR_ADMIN_KEY", "dev-admin-key"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))
    model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:3b"))
    db_path: str = field(default_factory=lambda: _env("TUTOR_DB", "tutor.db"))
    token_minutes: int = int(_env("TUTOR_TOKEN_MINUTES", "720"))
    rate_limit_per_min: int = int(_env("TUTOR_RATE_LIMIT", "10"))
    history_turns: int = int(_env("TUTOR_HISTORY_TURNS", "6"))
    # Hours ahead of UTC, used to decide which "day" an activity belongs to.
    # Eswatini (Africa/Mbabane) is UTC+2.
    tz_offset_hours: int = int(_env("TUTOR_TZ_OFFSET_HOURS", "2"))
    # May parents read what their child actually asked and was answered?
    # false = parents only see counts/streaks, never the content.
    parent_sees_chats: bool = field(default_factory=lambda: _env_bool("TUTOR_PARENT_SEES_CHATS", False))
    system_prompt: str = field(default_factory=lambda: _env(
        "TUTOR_SYSTEM_PROMPT",
        "You are a patient, encouraging tutor. Explain step by step and check understanding.",
    ))


settings = Settings()
