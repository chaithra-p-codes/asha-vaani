"""Gnani credential selection and usage accounting.

Rules (from the build plan, section 8.1):
* keys live only on the backend (env vars), never sent to the browser or logged;
* a secondary key is used ONLY if GNANI_SECONDARY_AUTHORISED=true (organiser-approved);
* keys are never rotated to evade limits; when no authorised credit remains, live calls stop
  and the session moves to a clearly labelled pending/recovery state.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from ..config import Settings


class NoAuthorisedCredential(Exception):
    pass


@dataclass
class _Account:
    alias: str
    key: str = field(repr=False)
    exhausted: bool = False
    exhausted_reason: str = ""
    stt_seconds: float = 0.0
    tts_chars: int = 0
    tts_requests: int = 0
    stt_sessions: int = 0


QUOTA_MARKERS = ("credit", "quota", "insufficient", "balance", "exhaust", "payment required")


def looks_like_quota_error(message: str | None, status: int | None = None) -> bool:
    if status in (402,):
        return True
    text = (message or "").lower()
    return any(m in text for m in QUOTA_MARKERS)


class CredentialManager:
    def __init__(self, settings: Settings, usage_sink=None):
        self._lock = threading.Lock()
        self._accounts: list[_Account] = []
        if settings.gnani_api_key:
            self._accounts.append(_Account("primary", settings.gnani_api_key))
        if settings.gnani_api_key_secondary and settings.gnani_secondary_authorised:
            self._accounts.append(_Account("secondary", settings.gnani_api_key_secondary))
        self._usage_sink = usage_sink  # callable(alias, service, units, unit)

    @property
    def configured(self) -> bool:
        return bool(self._accounts)

    def active(self) -> tuple[str, str]:
        """Return (alias, key) of the first non-exhausted authorised account."""
        with self._lock:
            for acc in self._accounts:
                if not acc.exhausted:
                    return acc.alias, acc.key
        if not self._accounts:
            raise NoAuthorisedCredential("No Gnani API key configured (set GNANI_API_KEY in backend/.env)")
        raise NoAuthorisedCredential("All authorised Gnani credentials report exhausted credit/quota")

    def mark_exhausted(self, alias: str, reason: str) -> None:
        with self._lock:
            for acc in self._accounts:
                if acc.alias == alias:
                    acc.exhausted = True
                    acc.exhausted_reason = reason[:200]

    def record(self, alias: str, service: str, units: float, unit: str) -> None:
        with self._lock:
            for acc in self._accounts:
                if acc.alias == alias:
                    if service == "stt":
                        acc.stt_seconds += units
                    elif service == "tts":
                        acc.tts_chars += int(units)
                        acc.tts_requests += 1
        if self._usage_sink is not None and units:
            try:
                self._usage_sink(alias, service, float(units), unit)
            except Exception:
                pass

    def status(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "alias": a.alias,
                    "exhausted": a.exhausted,
                    "exhausted_reason": a.exhausted_reason,
                    "stt_seconds_this_process": round(a.stt_seconds, 1),
                    "tts_chars_this_process": a.tts_chars,
                    "tts_requests_this_process": a.tts_requests,
                }
                for a in self._accounts
            ]


def now_ms() -> float:
    return time.monotonic() * 1000.0
