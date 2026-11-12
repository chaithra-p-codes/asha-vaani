"""Minimal in-process ASGI client (HTTP + WebSocket) so tests run without httpx/network."""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit


async def http(app, method: str, url: str, body=None, headers: dict | None = None):
    parts = urlsplit(url)
    raw = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    hdrs = [(b"host", b"testserver")]
    for k, v in (headers or {}).items():
        hdrs.append((k.lower().encode(), str(v).encode()))
    if raw:
        hdrs.append((b"content-type", b"application/json"))
        hdrs.append((b"content-length", str(len(raw)).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(), "query_string": parts.query.encode(),
             "root_path": "", "headers": hdrs, "client": ("127.0.0.1", 5000), "server": ("testserver", 80)}
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}
        await asyncio.sleep(3600)

    status = None
    out_headers = {}
    chunks = []

    async def send(msg):
        nonlocal status
        if msg["type"] == "http.response.start":
            status = msg["status"]
            for k, v in msg.get("headers", []):
                out_headers[k.decode().lower()] = v.decode()
        elif msg["type"] == "http.response.body":
            chunks.append(msg.get("body", b""))

    await app(scope, receive, send)
    data = b"".join(chunks)
    return status, out_headers, data


def as_json(data: bytes):
    return json.loads(data.decode())


class WSClient:
    def __init__(self, app, url: str):
        parts = urlsplit(url)
        self.to_app: asyncio.Queue = asyncio.Queue()
        self.from_app: asyncio.Queue = asyncio.Queue()
        self.scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": parts.path,
                      "raw_path": parts.path.encode(), "query_string": parts.query.encode(), "root_path": "",
                      "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 5001),
                      "server": ("testserver", 80), "subprotocols": []}
        self.app = app
        self.task = None
        self.events: list[dict] = []
        self.audio: dict[int, int] = {}
        self.accepted = False
        self.close_code = None

    async def connect(self):
        self.task = asyncio.create_task(self.app(self.scope, self.to_app.get, self.from_app.put))
        await self.to_app.put({"type": "websocket.connect"})
        msg = await asyncio.wait_for(self.from_app.get(), 5)
        if msg["type"] == "websocket.accept":
            self.accepted = True
        else:
            self.close_code = msg.get("code")
        return self

    async def send_json(self, obj):
        await self.to_app.put({"type": "websocket.receive", "text": json.dumps(obj)})

    async def send_bytes(self, data: bytes):
        await self.to_app.put({"type": "websocket.receive", "bytes": data})

    async def _pump_one(self, timeout):
        msg = await asyncio.wait_for(self.from_app.get(), timeout)
        if msg["type"] == "websocket.send":
            if msg.get("text") is not None:
                evt = json.loads(msg["text"])
                self.events.append(evt)
                return evt
            b = msg.get("bytes") or b""
            if b and b[0] == 1:
                uid = int.from_bytes(b[1:5], "little")
                self.audio[uid] = self.audio.get(uid, 0) + len(b) - 5
            return {"type": "_audio", "len": len(b)}
        if msg["type"] == "websocket.close":
            self.close_code = msg.get("code")
            return {"type": "_closed"}
        return {"type": msg["type"]}

    async def wait_for(self, predicate, timeout: float = 5.0, auto_ack_audio: bool = True):
        """Pump messages until predicate(evt) is true. Simulates the browser by reporting
        playback_ended for every utterance once its tts_end (or agent_say w/o audio) arrives."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"timeout; last events: {[e.get('type') for e in self.events[-12:]]}")
            try:
                evt = await self._pump_one(remaining)
            except (asyncio.TimeoutError, TimeoutError):
                raise TimeoutError("timeout; last events: " + str([(e.get('type'), e.get('kind') or e.get('state')
                                   or e.get('status') or e.get('awaiting')) for e in self.events[-15:]])) from None
            if auto_ack_audio and evt.get("type") in ("tts_end", "tts_unavailable"):
                await self.send_json({"type": "playback_ended", "utterance_id": evt["utterance_id"]})
            if auto_ack_audio and evt.get("type") == "agent_say" and not evt.get("audio"):
                await self.send_json({"type": "playback_ended", "utterance_id": evt["utterance_id"]})
            if predicate(evt):
                return evt

    async def close(self):
        await self.to_app.put({"type": "websocket.disconnect", "code": 1000})
        if self.task:
            try:
                await asyncio.wait_for(self.task, 5)
            except Exception:
                pass
