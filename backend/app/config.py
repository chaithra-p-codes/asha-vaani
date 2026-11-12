"""Central configuration for ASHA Vaani.

All secrets come from environment variables (loaded from backend/.env when present).
Nothing in this module ever logs or returns a secret value.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is optional at runtime; .env is the documented way to configure.
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

if load_dotenv is not None:
    load_dotenv(BACKEND_DIR / ".env", override=False)


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return raw.strip() if raw is not None else default


# Languages verified in Gnani docs for BOTH Prisma v3.0 STT and Timbre v3.0 TTS.
# Only these three have full template + lexicon coverage in this build.
SUPPORTED_LANGUAGES = {
    "hi": {"label": "हिन्दी (Hindi + English)", "stt_codes": "hi-IN,en-IN", "tts_code": "hi-IN"},
    "kn": {"label": "ಕನ್ನಡ (Kannada + English)", "stt_codes": "kn-IN,en-IN", "tts_code": "kn-IN"},
    "en": {"label": "English (India)", "stt_codes": "en-IN", "tts_code": "en-IN"},
}


@dataclass
class Settings:
    env: str = field(default_factory=lambda: _str("ASHA_ENV", "dev"))
    host: str = field(default_factory=lambda: _str("ASHA_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("ASHA_PORT", 8000))
    # Comma-separated list of allowed browser origins for REST CORS.
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in _str(
            "ASHA_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173"
        ).split(",") if o.strip()]
    )
    # speech_mode: "live" uses Gnani Prisma/Timbre. "demo" is the clearly-labelled
    # Layer-4 fallback that never calls Gnani and never plays synthetic audio as live.
    speech_mode: str = field(default_factory=lambda: _str("ASHA_SPEECH_MODE", "live"))

    # --- Gnani (Vachana) platform ---------------------------------------------------
    gnani_api_key: str = field(default_factory=lambda: _str("GNANI_API_KEY"))
    gnani_api_key_secondary: str = field(default_factory=lambda: _str("GNANI_API_KEY_SECONDARY"))
    # Must be explicitly set to true, and only after organisers confirm it is allowed.
    gnani_secondary_authorised: bool = field(default_factory=lambda: _bool("GNANI_SECONDARY_AUTHORISED", False))
    stt_url: str = field(default_factory=lambda: _str("GNANI_STT_URL", "wss://api.vachana.ai/stt/v3/stream"))
    tts_url: str = field(default_factory=lambda: _str("GNANI_TTS_URL", "wss://api.vachana.ai/api/v1/tts"))
    stt_model: str = field(default_factory=lambda: _str("GNANI_STT_MODEL", "prisma-v3.0"))
    tts_model: str = field(default_factory=lambda: _str("GNANI_TTS_MODEL", "timbre-v3.0"))
    # verbatim | transcribe | codemix | transliterate  (Prisma v3.0)
    stt_format: str = field(default_factory=lambda: _str("GNANI_STT_FORMAT", "codemix"))
    tts_voice: str = field(default_factory=lambda: _str("GNANI_TTS_VOICE", "Chetana"))
    tts_speed: float = field(default_factory=lambda: _float("GNANI_TTS_SPEED", 1.0))
    tts_sample_rate: int = field(default_factory=lambda: _int("GNANI_TTS_SAMPLE_RATE", 24000))
    stt_vad_threshold: float = field(default_factory=lambda: _float("GNANI_STT_VAD_THRESHOLD", 0.5))
    stt_min_silence_ms: int = field(default_factory=lambda: _int("GNANI_STT_MIN_SILENCE_MS", 600))
    stt_min_speech_ms: int = field(default_factory=lambda: _int("GNANI_STT_MIN_SPEECH_MS", 150))
    stt_idle_timeout_s: int = field(default_factory=lambda: _int("GNANI_STT_IDLE_TIMEOUT_S", 120))
    send_keyterms: bool = field(default_factory=lambda: _bool("GNANI_SEND_KEYTERMS", True))

    # --- Endpointing (turn detection on top of Prisma's own VAD) ---------------------
    endpoint_silence_dictation_ms: int = field(default_factory=lambda: _int("ENDPOINT_SILENCE_DICTATION_MS", 1100))
    endpoint_silence_short_ms: int = field(default_factory=lambda: _int("ENDPOINT_SILENCE_SHORT_MS", 700))
    listen_idle_timeout_s: float = field(default_factory=lambda: _float("LISTEN_IDLE_TIMEOUT_S", 10.0))
    max_turn_s: float = field(default_factory=lambda: _float("MAX_TURN_S", 60.0))
    ack_filler: bool = field(default_factory=lambda: _bool("ACK_FILLER", True))
    max_stt_seconds_per_session: int = field(default_factory=lambda: _int("MAX_STT_SECONDS_PER_SESSION", 600))

    # --- LLM extraction (optional; open choice per hackathon rules) ------------------
    llm_provider: str = field(default_factory=lambda: _str("LLM_PROVIDER", "gemini"))
    gemini_api_key: str = field(default_factory=lambda: _str("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _str("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    gemini_endpoint: str = field(default_factory=lambda: _str(
        "GEMINI_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta/models"))
    llm_timeout_s: float = field(default_factory=lambda: _float("LLM_TIMEOUT_S", 2.5))

    # --- Storage / privacy -------------------------------------------------------------
    db_path: str = field(default_factory=lambda: _str("ASHA_DB_PATH", str(BACKEND_DIR / "data" / "asha_vaani.db")))
    data_key_b64: str = field(default_factory=lambda: _str("ASHA_DATA_KEY"))
    retention_hours: int = field(default_factory=lambda: _int("RETENTION_HOURS", 72))
    # Seed the clearly labelled synthetic DEMO DATA visits at startup (idempotent).
    seed_demo: bool = field(default_factory=lambda: _bool("ASHA_SEED_DEMO", True))
    tts_cache_dir: str = field(default_factory=lambda: _str("TTS_CACHE_DIR", str(BACKEND_DIR / "data" / "tts_cache")))
    max_ws_message_bytes: int = field(default_factory=lambda: _int("MAX_WS_MESSAGE_BYTES", 65536))
    max_http_body_bytes: int = field(default_factory=lambda: _int("MAX_HTTP_BODY_BYTES", 32768))
    session_ttl_minutes: int = field(default_factory=lambda: _int("SESSION_TTL_MINUTES", 120))
    timezone: str = field(default_factory=lambda: _str("ASHA_TIMEZONE", "Asia/Kolkata"))
    frontend_dist: str = field(default_factory=lambda: _str("FRONTEND_DIST", str(PROJECT_DIR / "frontend" / "dist")))

    @property
    def gnani_configured(self) -> bool:
        return bool(self.gnani_api_key)

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider == "gemini" and bool(self.gemini_api_key)

    def public_summary(self) -> dict:
        """Non-secret configuration for the diagnostics screen. Never includes keys."""
        return {
            "env": self.env,
            "speech_mode": self.speech_mode,
            "gnani_configured": self.gnani_configured,
            "secondary_key_present": bool(self.gnani_api_key_secondary),
            "secondary_key_authorised": self.gnani_secondary_authorised,
            "stt_model": self.stt_model,
            "stt_format": self.stt_format,
            "tts_model": self.tts_model,
            "tts_voice": self.tts_voice,
            "tts_sample_rate": self.tts_sample_rate,
            "llm_provider": self.llm_provider if self.llm_configured else "none (rule-based extraction only)",
            "llm_model": self.gemini_model if self.llm_configured else None,
            "retention_hours": self.retention_hours,
            "endpoint_silence_ms": {
                "dictation": self.endpoint_silence_dictation_ms,
                "short_answer": self.endpoint_silence_short_ms,
            },
            "languages": {k: v["label"] for k, v in SUPPORTED_LANGUAGES.items()},
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_for_tests(**overrides) -> Settings:
    global _settings
    s = Settings()
    for k, v in overrides.items():
        setattr(s, k, v)
    _settings = s
    return s
