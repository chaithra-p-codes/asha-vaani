"""Thin outbound WebSocket transport used by the Gnani adapters.

Production uses the `websockets` library (>=13.1, asyncio client). The adapters only
depend on the small `WSConnection` protocol below, so tests can inject a fake server
that speaks the documented Gnani protocol without network access.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol, Union

Message = Union[bytes, str]


class TransportError(Exception):
    """Connection could not be opened or failed. `status` is the HTTP status if known."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class ConnectionClosed(TransportError):
    def __init__(self, code: int | None = None, reason: str = ""):
        super().__init__(f"connection closed (code={code}, reason={reason!r})")
        self.code = code
        self.reason = reason


class WSConnection(Protocol):
    async def send(self, data: Message) -> None: ...
    async def recv(self) -> Message: ...
    async def close(self) -> None: ...


ConnectFn = Callable[[str, dict], Awaitable[WSConnection]]


class _WebsocketsConnection:
    def __init__(self, ws):
        self._ws = ws

    async def send(self, data: Message) -> None:
        from websockets.exceptions import ConnectionClosed as _WSClosed
        try:
            await self._ws.send(data)
        except _WSClosed as exc:  # pragma: no cover - needs network
            rcvd = getattr(exc, "rcvd", None)
            raise ConnectionClosed(getattr(rcvd, "code", None), getattr(rcvd, "reason", "")) from exc

    async def recv(self) -> Message:
        from websockets.exceptions import ConnectionClosed as _WSClosed
        try:
            return await self._ws.recv()
        except _WSClosed as exc:  # pragma: no cover - needs network
            rcvd = getattr(exc, "rcvd", None)
            raise ConnectionClosed(getattr(rcvd, "code", None), getattr(rcvd, "reason", "")) from exc

    async def close(self) -> None:
        try:
            await self._ws.close()
        except Exception:  # pragma: no cover
            pass


async def websockets_connect(url: str, headers: dict, open_timeout: float = 8.0) -> WSConnection:
    """Open a client WebSocket with custom upgrade headers (Gnani auth is header-based)."""
    try:
        from websockets.asyncio.client import connect  # websockets >= 13.1
    except ImportError as exc:  # pragma: no cover
        raise TransportError(
            "The 'websockets' package (>=13.1) is required for live Gnani streaming. "
            "Run: pip install -r backend/requirements.txt"
        ) from exc
    try:
        ws = await connect(
            url,
            additional_headers=headers,
            open_timeout=open_timeout,
            max_size=4 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=2,
        )
    except Exception as exc:  # pragma: no cover - needs network
        status = None
        resp = getattr(exc, "response", None)
        if resp is not None:
            status = getattr(resp, "status_code", None)
        if status is None:
            status = getattr(exc, "status_code", None)
        raise TransportError(f"{type(exc).__name__}: {exc}", status=status) from exc
    return _WebsocketsConnection(ws)
