"""ASHA Vaani backend: ASGI app (Starlette, the toolkit FastAPI is built on) serving the
REST API, the visit WebSocket and the built PWA.

Run:  cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from . import __version__
from .config import BACKEND_DIR, SUPPORTED_LANGUAGES, Settings, get_settings
from .services import danger_rules
from .session_manager import ClientSender, SessionManager
from .speech.audio_utils import wav_bytes
from .speech.gnani_tts import TimbreTTSClient, TTSError
from .speech.transport import ConnectFn
from .storage.crypto import load_cipher
from .storage.db import Database
from .websocket.events import parse_client_event
from .services.readback import t

log = logging.getLogger("asha")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Content-Security-Policy": ("default-src 'self'; connect-src 'self' ws: wss:; media-src 'self' blob: data:; "
                                "img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
                                "worker-src 'self'; frame-ancestors 'none'"),
}


class BodyLimitAndHeaders:
    """Pure ASGI middleware: rejects oversized HTTP bodies and adds security headers."""

    def __init__(self, app, max_body: int):
        self.app = app
        self.max_body = max_body

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        try:
            clen = int(headers.get(b"content-length", b"0") or 0)
        except ValueError:
            clen = 0
        if clen > self.max_body:
            resp = JSONResponse({"error": "payload_too_large"}, status_code=413)
            return await resp(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                hdrs = list(message.get("headers") or [])
                existing = {k.lower() for k, _ in hdrs}
                for k, v in SECURITY_HEADERS.items():
                    if k.lower().encode() not in existing:
                        hdrs.append((k.lower().encode(), v.encode()))
                message["headers"] = hdrs
            await send(message)

        return await self.app(scope, receive, send_wrapper)


def _iso_or_none(v: str | None) -> str | None:
    """Accept only YYYY-MM-DD dates from query strings."""
    if not v:
        return None
    try:
        from datetime import date as _d
        return _d.fromisoformat(v[:10]).isoformat()
    except ValueError:
        return None


def _json_error(code: str, status: int, message: str = "") -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


async def _read_json(request: Request, max_bytes: int) -> dict:
    body = await request.body()
    if len(body) > max_bytes:
        raise ValueError("payload too large")
    if not body:
        return {}
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("JSON object expected")
    return data


def create_app(settings: Settings | None = None, *, stt_connect: ConnectFn | None = None,
               tts_connect: ConnectFn | None = None) -> Starlette:
    settings = settings or get_settings()
    cipher = load_cipher(settings.data_key_b64, settings.env, BACKEND_DIR / "data" / ".dev_data_key")
    db = Database(settings.db_path, cipher)
    db.seed_beneficiaries()
    if settings.seed_demo:
        from .storage.demo_seed import seed_demo_visits
        seed_demo_visits(db, datetime.now(ZoneInfo(settings.timezone)).date())
    manager = SessionManager(settings, db, stt_connect=stt_connect, tts_connect=tts_connect)

    def today_iso() -> str:
        return datetime.now(ZoneInfo(settings.timezone)).date().isoformat()

    def session_from(request: Request, session_id: str):
        token = request.headers.get("x-session-token", "")
        return manager.get(session_id, token)

    # ------------------------------------------------------------------ REST
    async def health(request: Request):
        return JSONResponse({"status": "ok", "version": __version__, "time": datetime.now().isoformat(timespec="seconds")})

    async def config_ep(request: Request):
        return JSONResponse(settings.public_summary())

    async def service_status(request: Request):
        return JSONResponse({
            "gnani_configured": manager.credentials.configured,
            "speech_mode": settings.speech_mode,
            "credentials": manager.credentials.status(),
            "active_sessions": len(manager.sessions),
            "llm": {"enabled": manager.llm.enabled, "model": settings.gemini_model if manager.llm.enabled else None,
                    "last_error": manager.llm.last_error, "last_latency_ms": manager.llm.last_latency_ms},
            "usage_recorded": await asyncio.to_thread(db.usage_summary),
            "tts_cache_entries": len(manager.tts_cache.mem),
        })

    async def create_session(request: Request):
        try:
            data = await _read_json(request, settings.max_http_body_bytes)
        except (ValueError, json.JSONDecodeError):
            return _json_error("bad_request", 400, "invalid JSON")
        language = str(data.get("language", "hi"))
        if language not in SUPPORTED_LANGUAGES:
            return _json_error("unsupported_language", 400, "language must be one of hi, kn, en")
        if data.get("consent") is not True:
            return _json_error("consent_required", 400, "recording consent is required before a session starts")
        mode = str(data.get("mode") or settings.speech_mode)
        if mode not in ("live", "demo", "diag"):
            return _json_error("bad_mode", 400)
        if mode in ("live", "diag") and not manager.credentials.configured:
            return _json_error("gnani_not_configured", 503,
                               "GNANI_API_KEY is not set on the server. Live speech cannot start. "
                               "Use the clearly labelled demo mode or configure the key.")
        sess, token = await asyncio.to_thread(manager.create, language, mode)
        await asyncio.to_thread(db.add_event, sess.id, "consent_given", None, f"lang={language};mode={mode}")
        return JSONResponse({"session_id": sess.id, "token": token, "ws_path": f"/ws/visit/{sess.id}",
                             "mode": mode, "language": language})

    async def get_session(request: Request):
        sess = session_from(request, request.path_params["session_id"])
        if not sess:
            return _json_error("not_found", 404)
        return JSONResponse({"session_id": sess.id, "mode": sess.mode, **sess.snapshot()})

    async def confirm_visit(request: Request):
        try:
            data = await _read_json(request, settings.max_http_body_bytes)
        except (ValueError, json.JSONDecodeError):
            return _json_error("bad_request", 400)
        sid = str(data.get("session_id", ""))
        sess = session_from(request, sid)
        if not sess:
            return _json_error("not_found", 404, "unknown session or token")
        if sess.saved_visit_id:
            return JSONResponse({"visit_id": sess.saved_visit_id, "created": False})
        if sess.state not in ("CONFIRMING", "PENDING") or sess.awaiting not in ("confirmation", "correction"):
            return _json_error("not_ready", 409, "record must be read back before it can be confirmed")
        if data.get("draft_version") is not None and int(data["draft_version"]) != sess.draft_version:
            return _json_error("stale_draft", 409, "the draft changed; review it again before confirming")
        await sess.save(via="rest")
        if sess.saved_visit_id:
            return JSONResponse({"visit_id": sess.saved_visit_id, "created": True})
        return _json_error("save_failed", 503, "not saved; draft kept as pending")

    async def list_visits(request: Request):
        qp = request.query_params
        try:
            limit = max(1, min(500, int(qp.get("limit", 200))))
        except ValueError:
            limit = 200
        visits = await asyncio.to_thread(db.list_visits, q=qp.get("q") or None, visit_type=qp.get("visit_type") or None,
                                         referral=qp.get("referral") or None, limit=limit,
                                         date_from=_iso_or_none(qp.get("from")), date_to=_iso_or_none(qp.get("to")),
                                         source=qp.get("source") or None)
        for v in visits:
            v.pop("transcript", None)
            v.pop("field_evidence", None)
        return JSONResponse({"visits": visits})

    async def get_visit(request: Request):
        v = await asyncio.to_thread(db.get_visit, request.path_params["visit_id"])
        if not v:
            return _json_error("not_found", 404)
        return JSONResponse(v)

    async def list_followups(request: Request):
        status = request.query_params.get("status", "PENDING")
        if status not in ("PENDING", "DONE", "ALL"):
            return _json_error("bad_status", 400)
        return JSONResponse({"followups": await asyncio.to_thread(db.list_followups, None if status == "ALL" else status),
                             "today": today_iso()})

    async def beneficiaries(request: Request):
        rows = await asyncio.to_thread(db.beneficiaries_summary, today_iso())
        q = (request.query_params.get("q") or "").strip().lower()
        cat = request.query_params.get("category") or ""
        st = request.query_params.get("status") or ""
        if q:
            rows = [r for r in rows if q in r["synthetic_external_id"] or q in r["name"].lower()]
        if cat:
            rows = [r for r in rows if r["category"] == cat]
        if st:
            rows = [r for r in rows if r["status"] == st]
        return JSONResponse({"beneficiaries": rows, "today": today_iso(), "synthetic": True})

    async def beneficiary(request: Request):
        prof = await asyncio.to_thread(db.beneficiary_profile, request.path_params["bid"], today_iso())
        if not prof:
            return _json_error("not_found", 404)
        return JSONResponse(prof)

    async def referrals(request: Request):
        rows = await asyncio.to_thread(db.referrals)
        st = request.query_params.get("state") or ""
        if st in ("OPEN", "CLOSED"):
            rows = [r for r in rows if r["state"] == st]
        return JSONResponse({"referrals": rows})

    async def reports(request: Request):
        from datetime import date as _date, timedelta as _td
        qp = request.query_params
        to = _iso_or_none(qp.get("to")) or today_iso()
        frm = _iso_or_none(qp.get("from")) or (_date.fromisoformat(to) - _td(days=29)).isoformat()
        if frm > to:
            return _json_error("bad_range", 400, "'from' must not be after 'to'")
        if (_date.fromisoformat(to) - _date.fromisoformat(frm)).days > 366:
            return _json_error("range_too_long", 400, "report range is limited to 366 days")
        return JSONResponse(await asyncio.to_thread(db.reports, frm, to))

    async def export_visits_csv(request: Request):
        import csv
        import io
        qp = request.query_params
        visits = await asyncio.to_thread(db.list_visits, q=qp.get("q") or None, visit_type=qp.get("visit_type") or None,
                                         referral=qp.get("referral") or None, limit=500,
                                         date_from=_iso_or_none(qp.get("from")), date_to=_iso_or_none(qp.get("to")),
                                         source=qp.get("source") or None)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["visit_id", "data_source", "beneficiary_id", "beneficiary_name", "visit_type", "visit_date",
                    "weight_kg", "vaccinations_given", "vaccinations_due", "ifa_tablets_given", "next_visit_date",
                    "referral_status", "danger_signs", "confirmation_status", "saved_at"])
        for v in visits:
            w.writerow([v["id"], "DEMO DATA (synthetic)" if v.get("source") == "seed" else v.get("source"),
                        v.get("beneficiary_id"), v.get("beneficiary_name"), v.get("visit_type"), v.get("visit_date"),
                        v.get("weight_kg"), "; ".join(v.get("vaccinations_given") or []),
                        "; ".join(v.get("vaccinations_due") or []), v.get("ifa_tablets_given"), v.get("next_visit_date"),
                        v.get("referral_status"), "; ".join(v.get("danger_signs") or []), v.get("confirmation_status"),
                        v.get("saved_at")])
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="asha_vaani_synthetic_visits.csv"'})

    async def seed_demo(request: Request):
        try:
            data = await _read_json(request, settings.max_http_body_bytes)
        except (ValueError, json.JSONDecodeError):
            return _json_error("bad_request", 400)
        from .storage.demo_seed import seed_demo_visits
        result = await asyncio.to_thread(seed_demo_visits, db, datetime.now(ZoneInfo(settings.timezone)).date(),
                                         bool(data.get("reset")))
        return JSONResponse(result)

    async def set_followup(request: Request):
        try:
            data = await _read_json(request, settings.max_http_body_bytes)
            ok = await asyncio.to_thread(db.set_followup_status, request.path_params["fid"], str(data.get("status")))
        except (ValueError, json.JSONDecodeError):
            return _json_error("bad_request", 400)
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    async def dashboard(request: Request):
        return JSONResponse(await asyncio.to_thread(db.dashboard, today_iso()))

    async def metrics(request: Request):
        return JSONResponse({"metrics": await asyncio.to_thread(db.metrics_summary),
                             "note": "Measured on this deployment only. Empty until live sessions run."})

    async def register(request: Request):
        return JSONResponse({"beneficiaries": manager.registry_cache, "synthetic": True})

    async def danger_catalogue(request: Request):
        return JSONResponse({"signs": danger_rules.catalogue(), "sources": [
            {"title": "Mother and Child Protection Card (2018 version)",
             "authority": "Ministry of Health & Family Welfare and Ministry of Women & Child Development, Government of India",
             "url": "https://nhm.gov.in/New_Updates_2018/NHM_Components/Immunization/Guildelines_for_immunization/MCP_Card_English_version.pdf"},
            {"title": "Guidebook for Mother-Child Protection Card 2018 for ANM | ASHA | AWW",
             "authority": "MoHFW & MoWCD, Government of India", "pages": "pp. 14-15 (pregnancy), p. 19 (newborn)",
             "url": "https://iec.unicef.in/public/uploads/documents/222758bf054a1620a8bc64fe41f4ace2.pdf"}],
            "disclaimer": "Prototype rule set for a hackathon. Not clinically validated."})

    async def delete_demo_data(request: Request):
        try:
            data = await _read_json(request, settings.max_http_body_bytes)
        except (ValueError, json.JSONDecodeError):
            return _json_error("bad_request", 400)
        if data.get("confirm") != "DELETE":
            return _json_error("confirmation_required", 400, 'send {"confirm": "DELETE"}')
        counts = await asyncio.to_thread(db.delete_all_demo_data)
        cache = manager.tts_cache.clear()
        manager.sessions.clear()
        return JSONResponse({"deleted": counts, "tts_cache_entries_deleted": cache})

    async def tts_test(request: Request):
        lang = request.query_params.get("lang", "hi")
        if lang not in SUPPORTED_LANGUAGES:
            return _json_error("unsupported_language", 400)
        if not manager.credentials.configured:
            return _json_error("gnani_not_configured", 503, "GNANI_API_KEY is not set")
        client = TimbreTTSClient(settings=settings, credentials=manager.credentials, cache=manager.tts_cache,
                                 connect_fn=manager.tts_connect)
        pcm = bytearray()
        try:
            async with contextlib.aclosing(client.synthesize(t("ack", lang), lang, cacheable=True)) as gen:
                async for chunk in gen:
                    pcm.extend(chunk)
        except TTSError as exc:
            return _json_error(f"tts_{exc.code}", 502, str(exc))
        finally:
            await client.drop()
        return Response(wav_bytes(bytes(pcm), settings.tts_sample_rate), media_type="audio/wav",
                        headers={"X-First-Chunk-Ms": str(round(client.last_first_chunk_ms or 0)),
                                 "X-From-Cache": str(client.last_from_cache).lower()})

    # ------------------------------------------------------------------ WebSocket
    async def visit_ws(websocket: WebSocket):
        sid = websocket.path_params["session_id"]
        token = websocket.query_params.get("token", "")
        sess = manager.get(sid, token)
        if sess is None:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        sender = ClientSender(websocket)
        attached = False
        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                data_b = msg.get("bytes")
                data_t = msg.get("text")
                if data_b is not None:
                    if len(data_b) > settings.max_ws_message_bytes:
                        await sender.send_json({"type": "error", "code": "frame_too_large", "recoverable": True})
                        continue
                    if attached:
                        await sess.on_audio(data_b)
                    continue
                if data_t is None:
                    continue
                if len(data_t) > settings.max_ws_message_bytes:
                    await sender.send_json({"type": "error", "code": "message_too_large", "recoverable": True})
                    continue
                try:
                    evt = parse_client_event(json.loads(data_t))
                except (ValueError, json.JSONDecodeError) as exc:
                    await sender.send_json({"type": "error", "code": "bad_event", "message": str(exc)[:200],
                                            "recoverable": True})
                    continue
                if evt.type == "hello":
                    if not attached:
                        attached = True
                        await sess.attach(sender, resume=evt.resume)
                    continue
                if not attached:
                    await sender.send_json({"type": "error", "code": "hello_required", "recoverable": True})
                    continue
                await sess.on_control(evt)
        except WebSocketDisconnect:
            pass
        finally:
            sender.closed = True
            if attached and sess.sender is sender:
                await sess.detach()

    # ------------------------------------------------------------------ static PWA
    dist = Path(settings.frontend_dist)

    async def spa(request: Request):
        index = dist / "index.html"
        if index.exists():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"error": "frontend_not_built",
                             "message": "Build the frontend (cd frontend && npm run build) or use the prebuilt dist/."},
                            status_code=404)

    async def sw(request: Request):
        p = dist / "sw.js"
        if not p.exists():
            return Response(status_code=404)
        return FileResponse(p, media_type="text/javascript", headers={"Cache-Control": "no-cache",
                                                                       "Service-Worker-Allowed": "/"})

    routes = [
        Route("/api/health", health),
        Route("/api/config", config_ep),
        Route("/api/session/status", service_status),
        Route("/api/sessions", create_session, methods=["POST"]),
        Route("/api/sessions/{session_id}", get_session),
        Route("/api/visits/confirm", confirm_visit, methods=["POST"]),
        Route("/api/visits", list_visits),
        Route("/api/visits/export.csv", export_visits_csv),
        Route("/api/visits/{visit_id}", get_visit),
        Route("/api/followups", list_followups),
        Route("/api/beneficiaries", beneficiaries),
        Route("/api/beneficiaries/{bid}", beneficiary),
        Route("/api/referrals", referrals),
        Route("/api/reports", reports),
        Route("/api/demo-data/seed", seed_demo, methods=["POST"]),
        Route("/api/followups/{fid}/status", set_followup, methods=["POST"]),
        Route("/api/dashboard", dashboard),
        Route("/api/metrics", metrics),
        Route("/api/register", register),
        Route("/api/danger-signs", danger_catalogue),
        Route("/api/demo-data/delete", delete_demo_data, methods=["POST"]),
        Route("/api/diagnostics/tts", tts_test),
        WebSocketRoute("/ws/visit/{session_id}", visit_ws),
        Route("/sw.js", sw),
    ]
    if dist.exists():
        for sub in ("assets", "audio", "icons"):
            if (dist / sub).exists():
                routes.append(Mount(f"/{sub}", app=StaticFiles(directory=dist / sub), name=sub))
        for name in ("manifest.webmanifest", "styles.css", "favicon.svg"):
            if (dist / name).exists():
                routes.append(Route(f"/{name}", (lambda p: (lambda r: FileResponse(p)))(dist / name)))
    routes.append(Route("/{path:path}", spa))

    async def retention_loop():
        while True:
            try:
                counts = await asyncio.to_thread(db.purge_older_than, settings.retention_hours)
                if any(counts.values()):
                    log.info("retention purge: %s", counts)
            except Exception:
                log.warning("retention purge failed")
            await asyncio.sleep(3600)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(retention_loop())
        log.info("ASHA Vaani %s | mode=%s | gnani=%s | llm=%s", __version__, settings.speech_mode,
                 "configured" if manager.credentials.configured else "NOT configured",
                 settings.gemini_model if manager.llm.enabled else "off")
        try:
            yield
        finally:
            task.cancel()

    app = Starlette(routes=routes, lifespan=lifespan, middleware=[
        Middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "X-Session-Token"], allow_credentials=False),
    ])
    app.state.manager = manager
    app.state.db = db
    app.state.settings = settings
    return BodyLimitAndHeaders(app, settings.max_http_body_bytes)


def _app_factory():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()


app = None
try:  # module-level app for `uvicorn app.main:app`
    import os
    if os.getenv("ASHA_NO_AUTOAPP") != "1":
        app = _app_factory()
except Exception as _exc:  # pragma: no cover
    logging.getLogger("asha").error("failed to create app: %s", _exc)
    raise
