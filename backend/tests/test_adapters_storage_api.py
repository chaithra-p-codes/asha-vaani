import asyncio
import base64
import json
from datetime import date

import pytest

from app.config import reset_settings_for_tests
from app.services.credential_manager import CredentialManager
from app.services.followups import generate, spoken_summary
from app.speech.audio_utils import FRAME_BYTES, Rechunker, silence
from app.speech.gnani_stt import PrismaSTTStream, build_stt_headers
from app.speech.gnani_tts import TimbreTTSClient, TTSCache, TTSError, build_tts_request
from app.storage.crypto import Cipher
from app.storage.db import Database
from asgi_driver import as_json, http
from conftest import make_app, run
from fakes import FakePrisma, FakeTimbre, silence_frames, tone_frames


def test_stt_headers_follow_gnani_v3_docs(settings):
    h = build_stt_headers(settings, "KEY", "hi", ["ANC", "आयरन"], "req-1")
    assert h["x-api-key-id"] == "KEY" and h["model"] == "prisma-v3.0"
    assert h["language_code"] == "hi-IN,en-IN" and h["x-sample-rate"] == "16000"
    assert h["format"] == "codemix"
    assert json.loads(h["keyterms"]) == ["ANC", "आयरन"] and h["keyterms"].isascii()
    assert all(isinstance(v, str) for v in h.values())


def test_tts_request_follow_gnani_v3_docs(settings):
    r = build_tts_request(settings, "नमस्ते", "kn", speed=2.0)
    assert r["model"] == "timbre-v3.0" and r["voice"] == "Chetana" and r["language"] == "kn-IN"
    assert r["speed"] == 1.15  # clamped to documented 0.85-1.15
    assert r["audio_config"] == {"sample_rate": 24000, "num_channels": 1, "sample_width": 2,
                                 "encoding": "linear_pcm", "container": "raw"}


def test_rechunker_emits_exact_prisma_frames():
    rc = Rechunker()
    frames = rc.push(b"\x01" * 3000)
    assert [len(f) for f in frames] == [FRAME_BYTES, FRAME_BYTES]
    tail = rc.flush()
    assert len(tail) == FRAME_BYTES and len(silence(100)) % FRAME_BYTES == 0


def test_stt_stream_frames_commit_and_transcript(settings):
    async def go():
        prisma = FakePrisma(["ANC 1024"], min_silence_frames=50)
        events = []

        async def on_event(e):
            events.append(e)

        st = PrismaSTTStream(settings=settings, credentials=CredentialManager(settings), language="hi",
                             keyterms=["ANC"], on_event=on_event, request_id="r", connect_fn=prisma.connect)
        await st.open()
        for f in tone_frames(10):
            st.push_audio(f[:700])
            st.push_audio(f[700:])
        await st.commit()
        for _ in range(100):
            await asyncio.sleep(0.02)
            if any(e["type"] == "transcript" for e in events):
                break
        await st.close()
        assert prisma.bad_frames == 0 and prisma.frames >= 10
        assert {"type": "commit"} in prisma.control
        tr = next(e for e in events if e["type"] == "transcript")
        assert tr["text"] == "ANC 1024" and tr["is_final"] is True
        assert events[0]["type"] == "connected"

    run(go())


def test_tts_client_decodes_chunks_caches_fixed_prompts_and_reports_errors(settings, tmp_path):
    async def go():
        timbre = FakeTimbre()
        cm = CredentialManager(settings)
        client = TimbreTTSClient(settings=settings, credentials=cm, cache=TTSCache(str(tmp_path / "c")),
                                 connect_fn=timbre.connect)
        pcm = b"".join([c async for c in client.synthesize("Okay, one moment.", "en", cacheable=True)])
        assert len(pcm) > 0 and len(pcm) % 2 == 0 and client.last_first_chunk_ms is not None
        again = b"".join([c async for c in client.synthesize("Okay, one moment.", "en", cacheable=True)])
        assert again == pcm and client.last_from_cache and len(timbre.requests) == 1  # credit saved
        bad = TimbreTTSClient(settings=settings, credentials=cm, connect_fn=FakeTimbre(fail_with="boom").connect)
        with pytest.raises(TTSError):
            async for _ in bad.synthesize("x", "en"):
                pass
        quota = TimbreTTSClient(settings=settings, credentials=cm,
                                connect_fn=FakeTimbre(fail_with="insufficient credits").connect)
        with pytest.raises(TTSError) as ei:
            async for _ in quota.synthesize("x", "en"):
                pass
        assert ei.value.code == "quota" and cm.status()[0]["exhausted"]

    run(go())


def test_tts_cancel_mid_stream_drops_socket(settings):
    async def go():
        timbre = FakeTimbre()
        client = TimbreTTSClient(settings=settings, credentials=CredentialManager(settings), connect_fn=timbre.connect)
        gen = client.synthesize("a long readback " * 20, "en")
        await gen.__anext__()
        await gen.aclose()
        assert client._conn is None  # next request uses a fresh socket: no stale chunks
        pcm = b"".join([c async for c in client.synthesize("next", "en")])
        assert pcm and timbre.connects == 2

    run(go())


def test_credential_manager_never_exposes_keys(settings):
    settings.gnani_api_key_secondary = "SECRET-2"
    settings.gnani_secondary_authorised = True
    cm = CredentialManager(settings)
    assert cm.active()[0] == "primary"
    cm.mark_exhausted("primary", "credit exhausted")
    assert cm.active()[0] == "secondary"
    assert "SECRET" not in json.dumps(cm.status()) and settings.gnani_api_key not in json.dumps(cm.status())
    assert "test-primary" not in json.dumps(settings.public_summary())


# ---------------------------------------------------------------- storage
def test_encryption_roundtrip_and_tamper_detection():
    c = Cipher(b"x" * 32)
    blob = c.encrypt({"name": "Sunita Devi"})
    assert b"Sunita" not in blob and c.decrypt(blob) == {"name": "Sunita Devi"}
    with pytest.raises(Exception):
        c.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]))


def test_idempotent_save_and_deletion(tmp_path):
    db = Database(str(tmp_path / "d.db"), Cipher(b"y" * 32))
    db.seed_beneficiaries()
    rec = {"beneficiary_id": "1024", "visit_type": "ANC", "visit_date": "2026-11-11", "referral_status": "NONE"}
    fus = generate({**rec, "next_visit_date": "2026-11-20"}, date(2026, 11, 11))
    v1, c1 = db.save_visit(record=rec, idempotency_key="s1:3", session_id="s1", source="live", followups=fus)
    v2, c2 = db.save_visit(record=rec, idempotency_key="s1:3", session_id="s1", source="live", followups=fus)
    assert c1 and not c2 and v1 == v2
    assert len(db.list_visits()) == 1 and len(db.list_followups()) == len(fus)
    counts = db.delete_all_demo_data()
    assert counts["visits"] == 1 and db.list_visits() == [] and db.registry()


def test_followups_are_deterministic_and_never_invent_dates():
    today = date(2026, 11, 11)
    f = generate({"visit_type": "ANC", "referral_status": "REFER_NOW", "weight_kg": 50,
                  "vaccinations_due": ["TT/Td-2"]}, today)
    kinds = [x["action_type"] for x in f]
    assert kinds[0] == "REFERRAL" and f[0]["priority"] == "URGENT" and f[0]["due_date"] == "2026-11-11"
    assert "SCHEDULE_VISIT" in kinds
    vac = next(x for x in f if x["action_type"] == "VACCINE_DUE")
    assert vac["due_date"] is None  # no next visit date stated -> no invented due date
    f2 = generate({"visit_type": "NEWBORN", "next_visit_date": "2026-11-14", "referral_status": "NONE"}, today)
    assert any(x["action_type"] == "NEXT_VISIT" and x["due_date"] == "2026-11-14" for x in f2)
    assert "RECORD_WEIGHT" in [x["action_type"] for x in f2]
    s = spoken_summary(f2, "hi", {"visit_type": "NEWBORN", "next_visit_date": "2026-11-14"})
    assert not any(c.isdigit() for c in s)


# ---------------------------------------------------------------- REST API
def test_api_consent_language_cors_limits_headers(settings):
    async def go():
        app, _, _ = make_app(settings)
        st, _, body = await http(app, "POST", "/api/sessions", {"language": "hi"})
        assert st == 400 and as_json(body)["error"] == "consent_required"
        st, _, _ = await http(app, "POST", "/api/sessions", {"language": "ta", "consent": True})
        assert st == 400
        st, h, _ = await http(app, "GET", "/api/health")
        assert st == 200 and h["x-content-type-options"] == "nosniff" and "content-security-policy" in h
        st, _, _ = await http(app, "POST", "/api/sessions", b"x" * (settings.max_http_body_bytes + 10))
        assert st == 413
        st, h, _ = await http(app, "GET", "/api/health", headers={"origin": "https://evil.example"})
        assert "access-control-allow-origin" not in h
        st, h, _ = await http(app, "GET", "/api/health", headers={"origin": "http://localhost:8000"})
        assert h.get("access-control-allow-origin") == "http://localhost:8000"
        st, _, body = await http(app, "GET", "/api/config")
        cfg = as_json(body)
        assert cfg["stt_model"] == "prisma-v3.0" and cfg["tts_model"] == "timbre-v3.0"
        assert "key" not in json.dumps(cfg).replace("key_present", "").replace("key_authorised", "").lower()
        st, _, body = await http(app, "GET", "/api/danger-signs")
        assert "nhm.gov.in" in json.dumps(as_json(body))
        st, _, _ = await http(app, "POST", "/api/demo-data/delete", {})
        assert st == 400
        st, _, body = await http(app, "POST", "/api/demo-data/delete", {"confirm": "DELETE"})
        assert st == 200 and "visits" in as_json(body)["deleted"]
        st, _, body = await http(app, "POST", "/api/visits/confirm", {"session_id": "nope"})
        assert st == 404

    run(go())


def test_live_session_refused_without_gnani_key(settings):
    settings.gnani_api_key = ""

    async def go():
        app, _, _ = make_app(settings)
        st, _, body = await http(app, "POST", "/api/sessions", {"language": "hi", "consent": True, "mode": "live"})
        assert st == 503 and as_json(body)["error"] == "gnani_not_configured"
        st, _, _ = await http(app, "POST", "/api/sessions", {"language": "hi", "consent": True, "mode": "demo"})
        assert st == 200

    run(go())


def test_tts_diagnostic_returns_wav(settings):
    async def go():
        app, _, timbre = make_app(settings)
        st, h, body = await http(app, "GET", "/api/diagnostics/tts?lang=kn")
        assert st == 200 and body[:4] == b"RIFF" and h["content-type"] == "audio/wav"
        assert timbre.requests[0]["language"] == "kn-IN"

    run(go())
