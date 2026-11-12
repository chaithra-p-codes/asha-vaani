"""Gnani Timbre v3.0 realtime TTS adapter (WebSocket).

Protocol verified against https://docs.gnani.ai/api/TTS/tts-websocket and
https://docs.gnani.ai/api/TTS/available-voices (Nov 2026):
  * URL wss://api.vachana.ai/api/v1/tts, auth header `X-API-Key-ID`
  * one JSON synthesis request at a time: {text, model, voice, language, speed, audio_config}
  * server replies: start -> audio{data:{chunk_index, audio(base64), is_final}} ... -> complete
  * cancellation is NOT documented, so cancelling = stop forwarding + drop the socket
    (a fresh socket is opened for the next request so stale chunks can never leak).
  * timbre-v3.0 voices are model-specific; default "Chetana" (warm, healthcare persona).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator

from ..config import SUPPORTED_LANGUAGES, Settings
from ..services.credential_manager import CredentialManager, looks_like_quota_error
from .transport import ConnectFn, ConnectionClosed, TransportError, websockets_connect

log = logging.getLogger("asha.tts")


class TTSError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def build_tts_request(settings: Settings, text: str, language: str, speed: float | None = None) -> dict:
    lang = SUPPORTED_LANGUAGES.get(language, SUPPORTED_LANGUAGES["hi"])
    return {
        "text": text,
        "model": settings.tts_model,
        "voice": settings.tts_voice,
        "language": lang["tts_code"],
        "speed": round(max(0.85, min(1.15, speed if speed is not None else settings.tts_speed)), 2),
        "audio_config": {
            "sample_rate": settings.tts_sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",
        },
    }


def _strip_wav_header(chunk: bytes) -> bytes:
    """Defensive: if a WAV container arrives despite container=raw, drop the header."""
    if chunk[:4] == b"RIFF" and b"data" in chunk[:200]:
        idx = chunk.index(b"data", 0, 200)
        return chunk[idx + 8:]
    return chunk


class TTSCache:
    """Cache for FIXED prompts only (disclosure, acknowledgements, generic questions).
    Dynamic read-backs that contain beneficiary details are never written to disk."""

    def __init__(self, directory: str | None):
        self.mem: dict[str, bytes] = {}
        self.dir = Path(directory) if directory else None
        if self.dir:
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.dir = None

    @staticmethod
    def key(req: dict) -> str:
        blob = json.dumps(req, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(blob).hexdigest()[:32]

    def get(self, key: str) -> bytes | None:
        if key in self.mem:
            return self.mem[key]
        if self.dir:
            p = self.dir / f"{key}.pcm"
            if p.exists():
                data = p.read_bytes()
                self.mem[key] = data
                return data
        return None

    def put(self, key: str, pcm: bytes) -> None:
        self.mem[key] = pcm
        if self.dir:
            tmp = self.dir / f"{key}.tmp"
            tmp.write_bytes(pcm)
            os.replace(tmp, self.dir / f"{key}.pcm")

    def clear(self) -> int:
        n = len(self.mem)
        self.mem.clear()
        if self.dir and self.dir.exists():
            for p in self.dir.glob("*.pcm"):
                p.unlink(missing_ok=True)
                n += 1
        return n


class TimbreTTSClient:
    """Persistent Timbre socket per visit session; strictly one request in flight."""

    def __init__(self, *, settings: Settings, credentials: CredentialManager,
                 cache: TTSCache | None = None, connect_fn: ConnectFn | None = None):
        self.settings = settings
        self.credentials = credentials
        self.cache = cache
        self.connect_fn = connect_fn or websockets_connect
        self._conn = None
        self._alias = None
        self._lock = asyncio.Lock()
        self.last_first_chunk_ms: float | None = None
        self.last_from_cache = False

    async def _ensure_conn(self):
        if self._conn is not None:
            return self._conn
        alias, key = self.credentials.active()
        headers = {"X-API-Key-ID": key, "Content-Type": "application/json"}
        try:
            self._conn = await asyncio.wait_for(self.connect_fn(self.settings.tts_url, headers), 8.0)
        except asyncio.TimeoutError as exc:
            raise TTSError("timeout", "Timed out connecting to Gnani Timbre") from exc
        except TransportError as exc:
            if exc.status == 401:
                raise TTSError("auth", "Gnani rejected the API key (HTTP 401)") from exc
            if exc.status == 429:
                raise TTSError("rate_limited", "Gnani rate limit (HTTP 429)") from exc
            if looks_like_quota_error(str(exc), exc.status):
                self.credentials.mark_exhausted(alias, str(exc))
                raise TTSError("quota", "Gnani credit/quota exhausted for active key") from exc
            raise TTSError("connect_failed", f"Could not connect to Gnani Timbre: {exc}") from exc
        self._alias = alias
        return self._conn

    async def drop(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

    async def prewarm(self) -> None:
        """Open the socket ahead of the first request to cut first-audio latency."""
        try:
            async with self._lock:
                await self._ensure_conn()
        except Exception:
            pass

    async def synthesize(self, text: str, language: str, *, speed: float | None = None,
                         cacheable: bool = False, chunk_timeout: float = 10.0) -> AsyncIterator[bytes]:
        """Yield raw PCM16 mono chunks at settings.tts_sample_rate.

        The consumer MUST close the generator (use contextlib.aclosing). Closing early
        (barge-in) drops the socket so unread chunks cannot leak into the next request."""
        req = build_tts_request(self.settings, text, language, speed)
        key = TTSCache.key(req) if (cacheable and self.cache is not None) else None
        if key:
            cached = self.cache.get(key)
            if cached:
                self.last_from_cache = True
                self.last_first_chunk_ms = 0.0
                step = max(2, (self.settings.tts_sample_rate // 10) * 2)  # 100 ms slices
                for i in range(0, len(cached), step):
                    yield cached[i:i + step]
                return
        self.last_from_cache = False
        async with self._lock:
            completed = False
            collected = bytearray() if key else None
            carry = b""
            t0 = time.monotonic()
            first = True
            try:
                for attempt in (1, 2):
                    conn = await self._ensure_conn()
                    try:
                        await conn.send(json.dumps(req, ensure_ascii=False))
                        break
                    except ConnectionClosed:
                        # stale persistent socket: reconnect once, nothing was yielded yet
                        await self.drop()
                        if attempt == 2:
                            raise TTSError("closed", "Timbre socket closed before request")
                while True:
                    try:
                        raw = await asyncio.wait_for(conn.recv(), chunk_timeout)
                    except asyncio.TimeoutError as exc:
                        raise TTSError("timeout", "Timbre stopped sending audio") from exc
                    except ConnectionClosed as exc:
                        raise TTSError("closed", f"Timbre closed the stream ({exc.code})") from exc
                    msg = _parse(raw)
                    mtype = msg.get("type")
                    if mtype == "start":
                        continue
                    if mtype == "audio":
                        data = msg.get("data") or {}
                        b64 = data.get("audio") or ""
                        if b64:
                            chunk = base64.b64decode(b64)
                            if first:
                                chunk = _strip_wav_header(chunk)
                                self.last_first_chunk_ms = (time.monotonic() - t0) * 1000
                                first = False
                            chunk = carry + chunk
                            if len(chunk) % 2:
                                carry, chunk = chunk[-1:], chunk[:-1]
                            else:
                                carry = b""
                            if chunk:
                                if collected is not None:
                                    collected.extend(chunk)
                                yield chunk
                        if data.get("is_final"):
                            completed = True
                            break
                        continue
                    if mtype == "complete":
                        completed = True
                        break
                    if mtype == "error":
                        text_msg = str(msg.get("message", ""))
                        if looks_like_quota_error(text_msg) and self._alias:
                            self.credentials.mark_exhausted(self._alias, text_msg)
                            raise TTSError("quota", text_msg)
                        raise TTSError("server_error", text_msg[:300] or "Timbre error")
                if completed and self._alias:
                    self.credentials.record(self._alias, "tts", len(text), "characters")
                if completed and collected and key:
                    self.cache.put(key, bytes(collected))
            finally:
                if not completed:
                    await self.drop()


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
