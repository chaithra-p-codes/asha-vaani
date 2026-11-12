"""Test doubles that speak the DOCUMENTED Gnani protocols (no network).

FakePrisma  - Prisma v3.0 streaming STT: validates 1024-byte PCM frames, emits
              connected / speech_start / processing / transcript(is_final) and honours
              {"type": "commit"}. Transcript TEXT is scripted (no real recognition), so these
              fakes verify the plumbing, framing, endpointing and pipeline - not accuracy.
FakeTimbre  - Timbre v3.0 TTS: validates the JSON request and replies start / audio
              (base64 PCM) / complete.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import struct

from app.speech.audio_utils import FRAME_BYTES, frame_rms
from app.speech.transport import ConnectionClosed, TransportError


def tone_frames(n_frames: int, amp: float = 0.3, freq: float = 220.0) -> list[bytes]:
    out = []
    k = 0
    for _ in range(n_frames):
        samples = []
        for _ in range(512):
            samples.append(int(amp * 32767 * math.sin(2 * math.pi * freq * k / 16000)))
            k += 1
        out.append(struct.pack("<512h", *samples))
    return out


def silence_frames(n_frames: int) -> list[bytes]:
    return [bytes(FRAME_BYTES)] * n_frames


class _Conn:
    def __init__(self):
        self.out: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def recv(self):
        if self.closed and self.out.empty():
            raise ConnectionClosed(1000, "closed")
        item = await self.out.get()
        if item is None:
            raise ConnectionClosed(1000, "closed")
        return item

    async def close(self):
        if not self.closed:
            self.closed = True
            await self.out.put(None)


class FakePrismaConn(_Conn):
    def __init__(self, server: "FakePrisma"):
        super().__init__()
        self.server = server
        self.in_speech = False
        self.silent = 0
        self.frames = 0
        self.seg = 0
        self.out.put_nowait(json.dumps({"type": "connected", "message": "STT service ready", "timestamp": "t",
                                        "config": {"sample_rate": 16000, "chunk_size": 512}}))

    async def _finalise(self):
        self.in_speech = False
        self.seg += 1
        await self.out.put(json.dumps({"type": "processing", "timestamp": "t"}))
        text = self.server.script.pop(0) if self.server.script else ""
        await self.out.put(json.dumps({"type": "transcript", "timestamp": "t", "text": text, "is_final": True,
                                       "segment_index": self.seg, "latency": self.server.latency_ms,
                                       "audio_duration_ms": 1000, "detected_language_code": "hi-IN"}))

    async def send(self, data):
        if self.closed:
            raise ConnectionClosed(1000, "closed")
        if isinstance(data, (bytes, bytearray)):
            if len(data) != FRAME_BYTES:
                self.server.bad_frames += 1
            self.frames += 1
            self.server.frames += 1
            loud = frame_rms(bytes(data)) > 800
            if loud and not self.in_speech:
                self.in_speech = True
                self.silent = 0
                await self.out.put(json.dumps({"type": "speech_start", "timestamp": "t", "utterance_id": "u"}))
            elif self.in_speech and not loud:
                self.silent += 1
                if self.silent >= self.server.min_silence_frames:
                    await self._finalise()
            elif loud:
                self.silent = 0
        else:
            msg = json.loads(data)
            self.server.control.append(msg)
            if msg.get("type") == "commit" and self.in_speech:
                await self._finalise()


class FakePrisma:
    def __init__(self, script=None, *, reject_status: int | None = None, latency_ms: int = 180,
                 min_silence_frames: int = 15):
        self.script = list(script or [])
        self.reject_status = reject_status
        self.latency_ms = latency_ms
        self.min_silence_frames = min_silence_frames
        self.headers_seen: list[dict] = []
        self.urls: list[str] = []
        self.frames = 0
        self.bad_frames = 0
        self.control: list[dict] = []
        self.conns: list[FakePrismaConn] = []

    async def connect(self, url, headers):
        self.urls.append(url)
        self.headers_seen.append(dict(headers))
        if self.reject_status:
            raise TransportError("server rejected WebSocket connection: HTTP %d" % self.reject_status,
                                 status=self.reject_status)
        c = FakePrismaConn(self)
        self.conns.append(c)
        return c


class FakeTimbreConn(_Conn):
    def __init__(self, server: "FakeTimbre"):
        super().__init__()
        self.server = server

    async def send(self, data):
        if self.closed:
            raise ConnectionClosed(1000, "closed")
        req = json.loads(data)
        self.server.requests.append(req)
        for k in ("text", "model", "voice", "language"):
            assert k in req, f"missing {k}"
        if self.server.fail_with:
            await self.out.put(json.dumps({"type": "error", "message": self.server.fail_with}))
            return
        sr = req.get("audio_config", {}).get("sample_rate", 48000)
        n_samples = int(sr * min(3.0, 0.02 * len(req["text"])))
        pcm = struct.pack(f"<{n_samples}h", *([1000] * n_samples))
        await self.out.put(json.dumps({"type": "start", "message": "Streaming started", "request_id": "req_1"}))
        step = sr // 5 * 2
        idx = 0
        for i in range(0, len(pcm), step):
            idx += 1
            await self.out.put(json.dumps({"type": "audio", "data": {
                "chunk_index": idx, "audio": base64.b64encode(pcm[i:i + step]).decode(), "is_final": False}}))
        await self.out.put(json.dumps({"type": "complete", "data": {"chunk_index": idx + 1, "audio": "",
                                                                      "is_final": True}}))


class FakeTimbre:
    def __init__(self, fail_with: str | None = None, reject_status: int | None = None):
        self.requests: list[dict] = []
        self.headers_seen: list[dict] = []
        self.fail_with = fail_with
        self.reject_status = reject_status
        self.connects = 0

    async def connect(self, url, headers):
        self.connects += 1
        self.headers_seen.append(dict(headers))
        if self.reject_status:
            raise TransportError("rejected", status=self.reject_status)
        return FakeTimbreConn(self)
