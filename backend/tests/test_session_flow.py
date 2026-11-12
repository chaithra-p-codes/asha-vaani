"""End-to-end visit flows over the real WebSocket handler, session state machine, Gnani
adapters (against protocol fakes), rule engine and encrypted SQLite store."""
import asyncio
import json
import sqlite3

from asgi_driver import WSClient, as_json, http
from conftest import make_app, run
from fakes import FakePrisma, FakeTimbre, silence_frames, tone_frames

ANC_NOTE = ("ANC checkup for beneficiary 1024. Weight is 52 kilos. TT injection recorded. "
            "IFA goli given. Next visit is on 20 November.")


async def start(app, language="en", mode="live"):
    status, _, body = await http(app, "POST", "/api/sessions", {"language": language, "consent": True, "mode": mode})
    assert status == 200, body
    s = as_json(body)
    ws = await WSClient(app, f"/ws/visit/{s['session_id']}?token={s['token']}").connect()
    assert ws.accepted
    await ws.send_json({"type": "hello", "client": "test"})
    return s, ws


async def speak(ws, seconds_voice=0.6, seconds_silence=0.7):
    """Stream synthetic 'speech' (tone) then silence, roughly in real time."""
    for f in tone_frames(int(seconds_voice / 0.032)):
        await ws.send_bytes(f)
        await asyncio.sleep(0.004)
    for f in silence_frames(int(seconds_silence / 0.032)):
        await ws.send_bytes(f)
        await asyncio.sleep(0.01)


def listening(evt, awaiting=None):
    return evt["type"] == "listen" and evt.get("on") and (awaiting is None or evt.get("awaiting") == awaiting)


def test_full_anc_visit_readback_correction_confirm_save(settings):
    prisma = FakePrisma([ANC_NOTE, "No, weight is 54 kilos", "haan"], min_silence_frames=6)

    async def go():
        app, prisma_, timbre = make_app(settings, prisma=prisma)
        s, ws = await start(app)
        # 1) first agent turn is the AI disclosure, spoken via Timbre
        say = await ws.wait_for(lambda e: e["type"] == "agent_say")
        assert say["kind"] == "disclosure" and "AI assistant" in say["text"] and say["audio"] is True
        await ws.wait_for(lambda e: listening(e, "dictation"))
        # 2) dictate
        await speak(ws)
        draft = await ws.wait_for(lambda e: e["type"] == "draft" and e["record"]["beneficiary_id"] == "1024", 8)
        rec = draft["record"]
        assert rec["visit_type"] == "ANC" and rec["weight_kg"] == 52.0
        assert rec["vaccinations_given"] == ["TT/Td"] and rec["ifa_tablets_given"] is True
        assert rec["next_visit_date"].endswith("-11-20")
        assert rec["beneficiary_name"] == "Sunita Devi"
        rb = await ws.wait_for(lambda e: e["type"] == "agent_say" and e["kind"] == "readback")
        assert "one zero two four" in rb["text"] and "fifty two" in rb["text"]
        await ws.wait_for(lambda e: listening(e, "confirmation"), 6)
        # 3) voice correction patches ONLY weight
        await speak(ws)
        d2 = await ws.wait_for(lambda e: e["type"] == "draft" and "weight_kg" in e.get("changed_fields", []), 8)
        assert d2["record"]["weight_kg"] == 54.0
        assert d2["record"]["beneficiary_id"] == "1024" and d2["record"]["next_visit_date"] == rec["next_visit_date"]
        assert d2["can_undo"] is True
        ack = await ws.wait_for(lambda e: e["type"] == "agent_say" and e["kind"] == "correction_ack")
        assert "fifty four" in ack["text"]
        await ws.wait_for(lambda e: listening(e, "confirmation"), 6)
        # 4) explicit yes -> idempotent save -> follow-ups
        await speak(ws)
        saved = await ws.wait_for(lambda e: e["type"] == "saved", 8)
        assert saved["created"] is True and saved["referral_status"] == "NONE"
        kinds = [f["action_type"] for f in saved["followups"]]
        assert "NEXT_VISIT" in kinds
        # 5) duplicate confirmation (button) never creates a second record
        await ws.send_json({"type": "action", "action": "confirm"})
        dup = await ws.wait_for(lambda e: e["type"] == "saved" and e.get("duplicate"), 4)
        assert dup["visit_id"] == saved["visit_id"]
        await ws.close()
        # protocol checks on what reached "Gnani"
        h = prisma_.headers_seen[0]
        assert h["model"] == "prisma-v3.0" and h["x-sample-rate"] == "16000" and h["x-api-key-id"]
        assert h["language_code"] == "en-IN" and json.loads(h["keyterms"])
        assert prisma_.bad_frames == 0 and prisma_.frames > 50
        assert all(r["model"] == "timbre-v3.0" and r["voice"] == "Chetana" for r in timbre.requests)
        assert all(r["audio_config"]["container"] == "raw" for r in timbre.requests)
        assert not any(ch.isdigit() for ch in "".join(r["text"] for r in timbre.requests if "check" in r["text"]))
        # stored encrypted, exactly once
        status, _, body = await http(app, "GET", "/api/visits")
        visits = as_json(body)["visits"]
        assert len(visits) == 1 and visits[0]["weight_kg"] == 54.0
        con = sqlite3.connect(settings.db_path)
        blob = con.execute("SELECT payload_enc FROM visits").fetchone()[0]
        assert b"Sunita" not in blob and b"54" not in blob[:2]
        assert con.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 1
        fu = as_json((await http(app, "GET", "/api/followups"))[2])["followups"]
        assert any(f["action_type"] == "NEXT_VISIT" for f in fu)
        dash = as_json((await http(app, "GET", "/api/dashboard"))[2])
        assert dash["visits_total"] == 1
        m = as_json((await http(app, "GET", "/api/metrics"))[2])["metrics"]
        assert "tts_first_chunk_ms" in m and "server_end_of_speech_to_first_audio_ms" in m

    run(go())


def test_newborn_danger_sign_alert_precedes_readback(settings):
    prisma = FakePrisma(["Newborn visit for beneficiary 1042, baby ko tez bukhar hai, weight 2.8 kilo, "
                         "next visit 14 November"], min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app, language="hi")
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        alert = await ws.wait_for(lambda e: e["type"] == "danger_alert", 8)
        assert alert["referral_status"] == "REFER_NOW"
        assert alert["signs"][0]["id"] == "NB_FEVER_OR_COLD"
        assert "पी एच सी" in alert["message"] and "रेफ़र" in alert["message"]
        kinds = []
        await ws.wait_for(lambda e: (e["type"] == "agent_say" and kinds.append(e["kind"]) is None
                                     and e["kind"] == "readback"), 8)
        assert kinds.index("alert") < kinds.index("readback")
        assert any(e["type"] == "draft" and e["referral_status"] == "REFER_NOW" for e in ws.events)
        await ws.close()

    run(go())


def test_negated_danger_sign_is_not_flagged(settings):
    prisma = FakePrisma(["ANC visit beneficiary 1024, bleeding nahi hai, weight 50 kilo, next visit 20 November"],
                        min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app, language="hi")
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        await ws.wait_for(lambda e: e["type"] == "agent_say" and e["kind"] == "readback", 8)
        assert not any(e["type"] == "danger_alert" for e in ws.events)
        draft = [e for e in ws.events if e["type"] == "draft"][-1]
        assert draft["referral_status"] == "NONE"
        await ws.close()

    run(go())


def test_uncertain_sign_asks_then_alerts_on_yes(settings):
    prisma = FakePrisma(["ANC visit beneficiary 1024 bukhar hai weight 50 kilo next visit 20 November", "haan"],
                        min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app, language="hi")
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        ask = await ws.wait_for(lambda e: e["type"] == "ask", 8)
        assert ask["awaiting"] == "danger:MATERNAL_HIGH_FEVER"
        await ws.wait_for(lambda e: listening(e, "danger:MATERNAL_HIGH_FEVER"), 6)
        await speak(ws)
        alert = await ws.wait_for(lambda e: e["type"] == "danger_alert", 8)
        assert alert["signs"][0]["id"] == "MATERNAL_HIGH_FEVER"
        await ws.close()

    run(go())


def test_missing_fields_asked_one_at_a_time_and_skip(settings):
    prisma = FakePrisma(["weight 50 kilo", "1024", "ANC", "skip"], min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app)
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        a1 = await ws.wait_for(lambda e: e["type"] == "ask", 8)
        assert a1["awaiting"] == "field:beneficiary_id"
        await ws.wait_for(lambda e: listening(e, "field:beneficiary_id"), 6)
        await speak(ws)
        a2 = await ws.wait_for(lambda e: e["type"] == "ask", 8)
        assert a2["awaiting"] == "field:visit_type"
        await ws.wait_for(lambda e: listening(e), 6)
        await speak(ws)
        a3 = await ws.wait_for(lambda e: e["type"] == "ask", 8)
        assert a3["awaiting"] == "field:next_visit_date"
        await ws.wait_for(lambda e: listening(e), 6)
        await speak(ws)
        rb = await ws.wait_for(lambda e: e["type"] == "agent_say" and e["kind"] == "readback", 8)
        assert "Next visit not heard" in rb["text"]
        d = [e for e in ws.events if e["type"] == "draft"][-1]["record"]
        assert d["beneficiary_id"] == "1024" and d["visit_type"] == "ANC" and d["next_visit_date"] is None
        await ws.close()

    run(go())


def test_undo_restores_previous_value(settings):
    prisma = FakePrisma([ANC_NOTE, "weight 54 kilo", "undo"], min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app)
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        await ws.wait_for(lambda e: listening(e, "confirmation"), 8)
        await speak(ws)
        await ws.wait_for(lambda e: e["type"] == "draft" and e["record"]["weight_kg"] == 54.0, 8)
        await ws.wait_for(lambda e: listening(e, "confirmation"), 8)
        await speak(ws)
        d = await ws.wait_for(lambda e: e["type"] == "draft" and e["record"]["weight_kg"] == 52.0, 8)
        assert "weight_kg" in d["changed_fields"]
        await ws.close()

    run(go())


def test_tts_failure_is_reported_truthfully_and_flow_continues(settings):
    prisma = FakePrisma([ANC_NOTE], min_silence_frames=6)
    timbre = FakeTimbre(fail_with="synthesis backend unavailable")

    async def go():
        app, _, _ = make_app(settings, prisma=prisma, timbre=timbre)
        s, ws = await start(app)
        un = await ws.wait_for(lambda e: e["type"] == "tts_unavailable")
        assert un["reason"] == "server_error"
        assert not any(e["type"] == "tts_start" for e in ws.events)
        await ws.wait_for(lambda e: listening(e, "dictation"), 6)
        await speak(ws)
        await ws.wait_for(lambda e: e["type"] == "readback", 8)
        await ws.close()

    run(go())


def test_quota_exhausted_moves_to_recovery_without_fake_success(settings):
    prisma = FakePrisma([], reject_status=402)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app)
        rec = await ws.wait_for(lambda e: e["type"] == "recovery", 8)
        assert rec["code"] == "quota" and "NOT saved" in rec["message"]
        st = await http(app, "GET", "/api/session/status")
        creds = as_json(st[2])["credentials"]
        assert creds[0]["exhausted"] is True and "key" not in json.dumps(creds).lower().replace("exhausted", "")
        await ws.close()

    run(go())


def test_secondary_key_only_used_when_authorised(settings):
    settings.gnani_api_key_secondary = "test-secondary"
    settings.gnani_secondary_authorised = False

    async def go():
        prisma = FakePrisma([], reject_status=402)
        app, _, _ = make_app(settings, prisma=prisma)
        s, ws = await start(app)
        await ws.wait_for(lambda e: e["type"] == "recovery", 8)
        assert all(h["x-api-key-id"] == "test-primary-key-not-real" for h in prisma.headers_seen)
        await ws.close()

    run(go())


def test_wrong_token_rejected_and_resume_requires_confirmation(settings):
    prisma = FakePrisma([ANC_NOTE], min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        bad = await WSClient(app, "/ws/visit/does-not-exist?token=nope").connect()
        assert not bad.accepted and bad.close_code == 4401
        s, ws = await start(app)
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        await ws.wait_for(lambda e: e["type"] == "readback", 8)
        await ws.close()
        # simulate a backend restart: drop in-memory session, restore from encrypted DB
        app.app.state.manager.sessions.clear() if hasattr(app, "app") else None
        ws2 = await WSClient(app, f"/ws/visit/{s['session_id']}?token={s['token']}").connect()
        await ws2.send_json({"type": "hello", "resume": True})
        d = await ws2.wait_for(lambda e: e["type"] == "draft", 5)
        assert d["record"]["beneficiary_id"] == "1024" and d["saved_visit_id"] is None
        q = await ws2.wait_for(lambda e: e["type"] == "agent_say", 5)
        assert q["kind"] == "confirm_prompt"
        assert not any(e["type"] == "saved" for e in ws2.events)
        await ws2.close()
        status, _, body = await http(app, "GET", "/api/visits")
        assert as_json(body)["visits"] == []

    run(go())


def test_demo_mode_is_labelled_and_never_calls_gnani(settings):
    prisma = FakePrisma([])
    timbre = FakeTimbre()

    async def go():
        app, _, _ = make_app(settings, prisma=prisma, timbre=timbre)
        s, ws = await start(app, mode="demo")
        sess = await ws.wait_for(lambda e: e["type"] == "session")
        assert sess["demo"] is True and sess["mode"] == "demo"
        say = await ws.wait_for(lambda e: e["type"] == "agent_say")
        assert say["audio"] is False and say["mode"] == "demo"
        await ws.send_json({"type": "demo_utterance", "text": ANC_NOTE})
        await ws.wait_for(lambda e: e["type"] == "readback", 6)
        await ws.send_json({"type": "demo_utterance", "text": "haan sahi hai"})
        saved = await ws.wait_for(lambda e: e["type"] == "saved", 6)
        assert saved["mode"] == "demo"
        await ws.close()
        assert prisma.headers_seen == [] and timbre.requests == []
        v = as_json((await http(app, "GET", "/api/visits"))[2])["visits"][0]
        assert v["source"] == "demo"

    run(go())


def test_live_text_injection_rejected(settings):
    async def go():
        app, _, _ = make_app(settings)
        s, ws = await start(app)
        await ws.send_json({"type": "demo_utterance", "text": "ANC 1024"})
        err = await ws.wait_for(lambda e: e["type"] == "error" and e.get("code") == "demo_only", 5)
        assert err
        await ws.close()

    run(go())


def test_failed_save_stays_pending_and_is_never_reported_saved(settings):
    prisma = FakePrisma([ANC_NOTE, "haan"], min_silence_frames=6)

    async def go():
        app, _, _ = make_app(settings, prisma=prisma)
        db = app.app.state.db
        real = db.save_visit
        calls = {"n": 0}

        def broken(**kw):
            calls["n"] += 1
            raise RuntimeError("disk full")
        db.save_visit = broken
        s, ws = await start(app)
        await ws.wait_for(lambda e: listening(e, "dictation"))
        await speak(ws)
        await ws.wait_for(lambda e: listening(e, "confirmation"), 8)
        await speak(ws)
        fail = await ws.wait_for(lambda e: e["type"] == "save_failed", 8)
        assert fail["draft"]["record"]["beneficiary_id"] == "1024"
        st = await ws.wait_for(lambda e: e["type"] == "state" and e["state"] == "PENDING", 4) \
            if not any(e["type"] == "state" and e["state"] == "PENDING" for e in ws.events) else True
        assert st and not any(e["type"] == "saved" for e in ws.events)
        # recovery: storage back, worker taps retry -> saved exactly once
        db.save_visit = real
        await ws.send_json({"type": "action", "action": "retry_save"})
        saved = await ws.wait_for(lambda e: e["type"] == "saved", 6)
        assert saved["created"] is True and calls["n"] == 1
        await ws.close()

    run(go())
