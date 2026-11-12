"""Gnani Prisma v3.0 realtime STT adapter (WebSocket).

Protocol verified against https://docs.gnani.ai/api/STT/stt-websocket (Nov 2026):
  * URL  wss://api.vachana.ai/stt/v3/stream, auth header `x-api-key-id`
  * config as upgrade headers: model=prisma-v3.0, language_code (1-4 codes on v3.0),
    format, x-sample-rate, VAD headers, keyterms (v3.0, <=200, JSON array)
  * client sends binary PCM s16le mono frames of exactly 1024 bytes (512 samples) at
    real-time cadence, plus JSON text {"type":"commit"} to close the open utterance
  * server sends JSON: connected, speech_start, processing, transcript (always final),
    error, settings_updated. No interim transcripts exist, so none are invented here.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

from ..config import SUPPORTED_LANGUAGES, Settings
from ..services.credential_manager import CredentialManager, looks_like_quota_error
from .audio_utils import FRAME_BYTES, FRAME_MS, Rechunker
from .transport import ConnectFn, ConnectionClosed, TransportError, websockets_connect

log = logging.getLogger("asha.stt")

EventCallback = Callable[[dict], Awaitable[None]]
_COMMIT = object()
_CLOSE = object()


def build_stt_headers(settings: Settings, api_key: str, language: str, keyterms: list[str],
                      request_id: str) -> dict:
    lang = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES["hi"])
    headers = {
        "x-api-key-id": api_key,
        "model": settings.stt_model,
        "language_code": lang["stt_codes"],
        "format": settings.stt_format,
        "x-sample-rate": "16000",
        "x-vad-threshold": f"{settings.stt_vad_threshold:.2f}",
        "x-min-silence-ms": str(settings.stt_min_silence_ms),
        "x-min-speech-ms": str(settings.stt_min_speech_ms),
        "x-idle-timeout-sec": str(settings.stt_idle_timeout_s),
        "x-api-request-id": request_id,
    }
    if settings.send_keyterms and keyterms:
        # JSON array; non-ASCII escaped as \uXXXX so the header stays ASCII-safe (per docs).
        headers["keyterms"] = json.dumps(keyterms[:200], ensure_ascii=True)
    return headers


class STTError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PrismaSTTStream:
    """One Prisma streaming session. Audio is pushed as it arrives from the browser;
    a sender task forwards exact 1024-byte frames at (at most) 2x real-time pace."""

    def __init__(self, *, settings: Settings, credentials: CredentialManager, language: str,
                 keyterms: list[str], on_event: EventCallback, request_id: str,
                 connect_fn: ConnectFn | None = None, max_queue_frames: int = 250):
        self.settings = settings
        self.credentials = credentials
        self.language = language
        self.keyterms = keyterms
        self.on_event = on_event
        self.request_id = request_id
        self.connect_fn = connect_fn or websockets_connect
        self._queue: asyncio.Queue = asyncio.Queue()
        self._max_queue = max_queue_frames
        self._rechunker = Rechunker()
        self._conn = None
        self._alias = None
        self._tasks: list[asyncio.Task] = []
        self.state = "idle"
        self.frames_sent = 0
        self.frames_dropped = 0
        self.connected_info: dict = {}
        self.open_latency_ms: float | None = None

    # ------------------------------------------------------------------ lifecycle
    async def open(self, timeout: float = 8.0) -> None:
        self.state = "connecting"
        alias, key = self.credentials.active()
        self._alias = alias
        headers = build_stt_headers(self.settings, key, self.language, self.keyterms, self.request_id)
        t0 = time.monotonic()
        try:
            self._conn = await asyncio.wait_for(self.connect_fn(self.settings.stt_url, headers), timeout)
        except asyncio.TimeoutError as exc:
            self.state = "error"
            raise STTError("timeout", "Timed out connecting to Gnani Prisma") from exc
        except TransportError as exc:
            self.state = "error"
            if exc.status == 401:
                raise STTError("auth", "Gnani rejected the API key (HTTP 401)") from exc
            if exc.status == 429:
                raise STTError("rate_limited", "Gnani rate limit (HTTP 429); retry with backoff") from exc
            if looks_like_quota_error(str(exc), exc.status):
                self.credentials.mark_exhausted(alias, str(exc))
                raise STTError("quota", "Gnani credit/quota exhausted for active key") from exc
            raise STTError("connect_failed", f"Could not connect to Gnani Prisma: {exc}") from exc
        # First server message must be `connected` (or an `error`).
        try:
            first = await asyncio.wait_for(self._conn.recv(), timeout)
        except (asyncio.TimeoutError, ConnectionClosed) as exc:
            self.state = "error"
            await self._safe_close_conn()
            raise STTError("handshake", "Gnani Prisma did not send 'connected'") from exc
        msg = _parse(first)
        if msg.get("type") == "error":
            self.state = "error"
            await self._safe_close_conn()
            text = str(msg.get("message", ""))
            if looks_like_quota_error(text):
                self.credentials.mark_exhausted(alias, text)
                raise STTError("quota", text)
            raise STTError("server_error", text or "Prisma error at handshake")
        self.connected_info = msg
        self.open_latency_ms = (time.monotonic() - t0) * 1000
        self.state = "open"
        await self.on_event({"type": "connected", "config": msg.get("config", {}),
                             "open_latency_ms": round(self.open_latency_ms)})
        self._tasks = [asyncio.create_task(self._send_loop()), asyncio.create_task(self._recv_loop())]

    @property
    def is_open(self) -> bool:
        return self.state == "open"

    def push_audio(self, data: bytes) -> None:
        if self.state != "open":
            return
        for frame in self._rechunker.push(data):
            if self._queue.qsize() >= self._max_queue:
                # Backpressure: drop the oldest frame rather than buffering without bound.
                try:
                    self._queue.get_nowait()
                    self.frames_dropped += 1
                except asyncio.QueueEmpty:
                    pass
            self._queue.put_nowait(frame)

    async def commit(self) -> None:
        """Flush buffered audio then ask Prisma to close the open utterance now."""
        if self.state != "open":
            return
        tail = self._rechunker.flush()
        if tail:
            self._queue.put_nowait(tail)
        self._queue.put_nowait(_COMMIT)

    async def close(self) -> None:
        if self.state in ("closed", "idle"):
            self.state = "closed"
            return
        self.state = "closed"
        self._queue.put_nowait(_CLOSE)
        for t in self._tasks:
            if not t.done():
                t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        await self._safe_close_conn()
        if self._alias:
            self.credentials.record(self._alias, "stt", self.frames_sent * FRAME_MS / 1000.0, "audio_seconds")
            self._alias = None

    # ------------------------------------------------------------------ internals
    async def _safe_close_conn(self) -> None:
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None

    async def _send_loop(self) -> None:
        min_gap = (FRAME_MS / 2.0) / 1000.0  # never faster than 2x real time
        last = 0.0
        try:
            while True:
                item = await self._queue.get()
                if item is _CLOSE:
                    return
                if item is _COMMIT:
                    await self._conn.send(json.dumps({"type": "commit"}))
                    continue
                now = time.monotonic()
                wait = last + min_gap - now
                if wait > 0:
                    await asyncio.sleep(wait)
                await self._conn.send(item)
                last = time.monotonic()
                self.frames_sent += 1
        except asyncio.CancelledError:
            raise
        except ConnectionClosed as exc:
            await self._on_closed(exc.code, exc.reason)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("stt send loop error: %s", type(exc).__name__)
            await self._on_closed(None, type(exc).__name__)

    async def _recv_loop(self) -> None:
        try:
            while True:
                raw = await self._conn.recv()
                msg = _parse(raw)
                mtype = msg.get("type")
                if mtype == "transcript":
                    await self.on_event({
                        "type": "transcript",
                        "text": str(msg.get("text") or "").strip(),
                        "segment_index": msg.get("segment_index"),
                        "segment_id": msg.get("segment_id"),
                        "latency_ms": msg.get("latency"),
                        "audio_duration_ms": msg.get("audio_duration_ms"),
                        "utterance_id": msg.get("utterance_id"),
                        "detected_language": msg.get("detected_language_code"),
                        "is_final": True,
                    })
                elif mtype in ("speech_start", "processing", "settings_updated"):
                    await self.on_event({"type": mtype, "utterance_id": msg.get("utterance_id")})
                elif mtype == "error":
                    text = str(msg.get("message", ""))
                    quota = looks_like_quota_error(text)
                    if quota and self._alias:
                        self.credentials.mark_exhausted(self._alias, text)
                    await self.on_event({"type": "error", "message": text[:300], "quota": quota})
                elif mtype == "connected":
                    pass
                # unknown types are ignored deliberately
        except asyncio.CancelledError:
            raise
        except ConnectionClosed as exc:
            await self._on_closed(exc.code, exc.reason)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("stt recv loop error: %s", type(exc).__name__)
            await self._on_closed(None, type(exc).__name__)

    async def _on_closed(self, code, reason) -> None:
        if self.state == "closed":
            return
        self.state = "closed"
        if self._alias:
            self.credentials.record(self._alias, "stt", self.frames_sent * FRAME_MS / 1000.0, "audio_seconds")
            self._alias = None
        await self.on_event({"type": "closed", "code": code, "reason": str(reason or "")[:200]})


def _parse(raw) -> dict:
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {}
    try:
        msg = json.loads(raw)
        return msg if isinstance(msg, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


__all__ = ["PrismaSTTStream", "STTError", "build_stt_headers", "FRAME_BYTES"]
