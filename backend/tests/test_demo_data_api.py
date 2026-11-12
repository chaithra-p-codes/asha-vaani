"""Seeded DEMO DATA + new read APIs (beneficiaries, referrals, reports, export, dashboard)."""
from datetime import date

from asgi_driver import as_json, http
from conftest import make_app, run
from app.storage.demo_seed import seed_demo_visits


def test_seed_is_idempotent_resettable_and_labelled(settings):
    settings.seed_demo = True

    async def go():
        app, _, _ = make_app(settings)
        db = app.app.state.db
        visits = as_json((await http(app, "GET", "/api/visits"))[2])["visits"]
        assert len(visits) == 24 and all(v["source"] == "seed" for v in visits)
        types = {}
        for v in visits:
            types[v["visit_type"]] = types.get(v["visit_type"], 0) + 1
        assert types == {"ANC": 9, "PNC": 5, "NEWBORN": 5, "IMMUNISATION": 5}
        again = seed_demo_visits(db, date.today())
        assert again["created"] == 0                          # idempotent
        r = as_json((await http(app, "POST", "/api/demo-data/seed", {"reset": True}))[2])
        assert r["removed"] == 24 and r["created"] == 24
        assert len(as_json((await http(app, "GET", "/api/visits"))[2])["visits"]) == 24
        # retention never deletes seeded synthetic data
        db.purge_older_than(0)
        assert len(db.list_visits()) == 24

    run(go())


def test_dashboard_beneficiaries_profile_referrals_reports(settings):
    settings.seed_demo = True

    async def go():
        app, _, _ = make_app(settings)
        d = as_json((await http(app, "GET", "/api/dashboard"))[2])
        assert d["total_beneficiaries"] == 20 and d["visits_total"] == 24 and d["demo_visits"] == 24
        assert d["urgent_referrals"] == 1 and d["upcoming_followups"] and d["overdue_followups"] >= 1
        b = as_json((await http(app, "GET", "/api/beneficiaries"))[2])["beneficiaries"]
        assert len(b) == 20
        by = {x["synthetic_external_id"]: x for x in b}
        assert by["1090"]["status"] == "REFERRED" and by["1042"]["visits"] == 2
        assert as_json((await http(app, "GET", "/api/beneficiaries?q=sunita"))[2])["beneficiaries"][0]["name"].startswith("Sunita")
        p = as_json((await http(app, "GET", "/api/beneficiaries/1042"))[2])
        assert len(p["visits_list"]) == 2 and p["timeline"] and p["latest"]["weight_kg"] == 2.9
        assert (await http(app, "GET", "/api/beneficiaries/9999"))[0] == 404
        refs = as_json((await http(app, "GET", "/api/referrals"))[2])["referrals"]
        states = {r["beneficiary_id"]: r["state"] for r in refs}
        assert states == {"1090": "OPEN", "1103": "CLOSED", "1118": "OPEN"}
        assert refs[0]["signs"][0]["rule_id"].startswith("RULE_")
        rep = as_json((await http(app, "GET", "/api/reports"))[2])
        assert rep["total_visits"] == 24 and rep["visits_by_type"]["ANC"] == 9 and len(rep["visits_by_day"]) == 30
        assert rep["referrals"] == {"refer_now": 2, "review": 1}
        assert sum(x["visits"] for x in rep["visits_by_day"]) == 24
        assert (await http(app, "GET", "/api/reports?from=2026-12-01&to=2026-11-01"))[0] == 400
        fu = as_json((await http(app, "GET", "/api/followups?status=ALL"))[2])["followups"]
        assert any(f["status"] == "DONE" for f in fu) and all(f["beneficiary_name"] for f in fu)
        st, h, body = await http(app, "GET", "/api/visits/export.csv?visit_type=ANC")
        assert st == 200 and h["content-type"].startswith("text/csv")
        lines = body.decode().strip().splitlines()
        assert len(lines) == 10 and "DEMO DATA" in lines[1]
        filt = as_json((await http(app, "GET", "/api/visits?referral=ANY"))[2])["visits"]
        assert len(filt) == 3
        today = date.today().isoformat()
        only_today = as_json((await http(app, "GET", f"/api/visits?from={today}&to={today}"))[2])["visits"]
        assert all(v["visit_date"] == today for v in only_today)

    run(go())


def test_seeded_visits_never_sort_above_a_visit_recorded_now(tmp_path):
    """Seeded 'today' records must carry timestamps earlier than now, so a live visit saved
    after seeding is listed first (regression: seeds used fixed clock times later in the day)."""
    from datetime import date, datetime, timezone
    from app.storage.crypto import load_cipher
    from app.storage.db import Database
    from app.storage.demo_seed import seed_demo_visits

    db = Database(str(tmp_path / "s.db"), load_cipher(None, "dev", tmp_path / "k"))
    db.seed_beneficiaries()
    seed_demo_visits(db, date.today())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assert all(v["saved_at"] <= now for v in db.list_visits(limit=500))
    db.save_visit(record={"beneficiary_id": "1024", "visit_type": "ANC", "visit_date": date.today().isoformat()},
                  idempotency_key="live-1", session_id="s-live", source="live", followups=[])
    assert db.list_visits(limit=1)[0]["source"] == "live"
