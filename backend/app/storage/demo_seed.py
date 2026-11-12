"""Synthetic demonstration visits (DEMO DATA) stored in the real application database.

* 24 visits for the 20 fictional beneficiaries: 9 ANC, 5 PNC, 5 newborn, 5 immunisation,
  spread over the last three weeks relative to the day of seeding.
* Follow-ups are produced by the SAME deterministic rules as live visits
  (services/followups.py); some are then marked done to show history.
* 3 referral situations: an open REFER_NOW (bleeding in pregnancy), a closed REFER_NOW
  (newborn fever) and an ANM review. Danger details come from the real rule catalogue.
* Every row is tagged source='seed' so the UI can label it DEMO DATA, retention never
  deletes it, and reset removes only seeded rows (live/demo-mode records are untouched).
* Idempotent: each visit has a fixed idempotency key ("seed-v1:<n>").
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from ..services import danger_rules
from ..services.followups import generate as generate_followups

SEED_VERSION = "seed-v1"

# (n, beneficiary_id, visit_type, days_ago, weight, given, due, ifa, next_in_days, danger, transcript)
_VISITS = [
    (1, "1024", "ANC", 9, 51.0, ["TT/Td-1"], [], True, 0, None,
     "ANC checkup for beneficiary 1024, weight 51 kilo, TT one given, IFA goli di, next visit in nine days"),
    (2, "1031", "ANC", 6, 47.5, [], ["TT/Td-2"], True, 8, None,
     "Sunita Kumari ID 1031 ANC visit, vajan saadhe saintalees kilo, TT 2 due hai, IFA di"),
    (3, "1012", "ANC", 2, 49.0, ["TT/Td-2"], [], True, 12, None,
     "ANC 1012 weight 49 kg TT second dose given IFA tablets given next visit after twelve days"),
    (4, "1015", "ANC", 14, 56.0, [], [], True, -2, None,
     "1015 ka ANC, weight 56 kilo, IFA goli di, agli visit do hafte baad"),
    (5, "1050", "ANC", 1, 61.0, ["TT/Td booster"], [], True, 13, None,
     "ANC checkup beneficiary 1050 weight 61 kilo TT booster given IFA given"),
    (6, "1077", "ANC", 4, 63.5, [], [], False, 10, None,
     "Shilpa Hegde 1077 ANC visit weight 63.5 kg IFA nahi di next visit in ten days"),
    (7, "1090", "ANC", 0, 52.0, [], [], True, 7, "PREG_BLEEDING",
     "ANC visit beneficiary 1090, bleeding ho rahi hai, weight 52 kilo"),
    (8, "1118", "ANC", 3, 58.0, [], [], True, 11, "REVIEW:MATERNAL_HIGH_FEVER",
     "ANC 1118 weight 58 kilo bukhar hai shayad, IFA di"),
    (9, "1130", "ANC", 18, 50.5, ["TT/Td-1"], ["TT/Td-2"], True, -1, None,
     "ANC 1130 vajan pachaas point paanch kilo TT pehla laga TT doosra due"),
    (10, "1007", "PNC", 5, 54.0, [], [], True, 9, None,
     "PNC visit Lakshmi Gowda 1007 weight 54 kg IFA tablets given"),
    (11, "1019", "PNC", 12, 57.0, [], [], True, 2, None,
     "PNC 1019 weight 57 kilo IFA di agli visit do hafte baad"),
    (12, "1063", "PNC", 2, 53.5, [], [], True, 5, None,
     "डिलीवरी के बाद की विज़िट, आईडी 1063, वज़न साढ़े तिरपन किलो, आयरन की गोली दी"),
    (13, "1102", "PNC", 7, 55.0, [], [], False, 0, None,
     "PNC visit 1102 weight 55 kg IFA not given next visit in seven days"),
    (14, "1145", "PNC", 1, 52.0, [], [], True, 6, None,
     "PNC 1145 Asha Kamble weight 52 kilo IFA given"),
    (15, "1042", "NEWBORN", 11, 2.7, ["BCG", "OPV-0", "Hepatitis B"], [], None, -4, None,
     "Newborn visit 1042 weight 2.7 kilo BCG OPV zero hepatitis B given"),
    (16, "1042", "NEWBORN", 4, 2.9, [], ["Pentavalent-1"], None, 3, None,
     "Newborn 1042 weight two point nine kilo Penta 1 due"),
    (17, "1064", "NEWBORN", 8, 3.1, ["BCG", "OPV-0"], [], None, 1, None,
     "नवजात शिशु विज़िट 1064, वज़न तीन दशमलव एक किलो, बीसीजी और ओपीवी ज़ीरो दिया"),
    (18, "1103", "NEWBORN", 6, 2.6, [], [], None, 2, "NB_FEVER_OR_COLD",
     "Newborn visit 1103, baby ko tez bukhar hai, weight 2.6 kilo"),
    (19, "1146", "NEWBORN", 0, 3.0, ["BCG", "OPV-0", "Hepatitis B"], [], None, 7, None,
     "Newborn visit 1146 weight 3 kilo BCG OPV zero hepatitis B diya"),
    (20, "1081", "IMMUNISATION", 16, 6.2, ["Pentavalent-2", "OPV-2", "Rotavirus-2"], ["Pentavalent-3"], None, 12, None,
     "Immunisation 1081 Penta 2 OPV 2 Rota 2 given Penta 3 due weight 6.2 kg"),
    (21, "1081", "IMMUNISATION", 3, 6.6, ["Pentavalent-3", "OPV-3"], ["MR"], None, 25, None,
     "Teekakaran 1081 penta teen aur OPV teen diya MR due vajan 6.6 kilo"),
    (22, "1125", "IMMUNISATION", 13, 8.4, ["MR", "Vitamin A"], [], None, 0, None,
     "Immunisation visit 1125 measles ka tika laga vitamin A diya vajan 8.4 kilo"),
    (23, "1125", "IMMUNISATION", 0, 8.6, [], ["JE"], None, 14, None,
     "Immunisation 1125 weight 8.6 kg JE due next visit in two weeks"),
    (24, "1064", "IMMUNISATION", 1, 3.4, ["Pentavalent-1", "OPV-1", "Rotavirus-1"], [], None, 27, None,
     "Immunisation 1064 Penta 1 OPV 1 Rota 1 given weight 3.4 kilo"),
]
# follow-ups that the demo worker has already completed: (visit n, action_type)
_DONE = {(15, "NEXT_VISIT"), (18, "REFERRAL"), (20, "NEXT_VISIT"), (20, "VACCINE_DUE"), (22, "NEXT_VISIT"),
         (11, "NEXT_VISIT"), (4, "NEXT_VISIT")}


def _danger_entry(sign_id: str, status: str, phrase: str, reason: str) -> dict:
    s = danger_rules.sign_by_id(sign_id)
    return {"id": sign_id, "status": status, "matched_phrase": phrase, "reason": reason, "label": s.label,
            "source_ref": s.source_ref, "subject": s.subject, "rule_id": f"RULE_{sign_id}"}


def build_records(today: date, registry: dict[str, dict]) -> list[tuple[str, dict, list, str]]:
    out = []
    for (n, bid, vt, ago, weight, given, due, ifa, nxt, danger, transcript) in _VISITS:
        vdate = today - timedelta(days=ago)
        next_date = vdate + timedelta(days=ago + nxt) if nxt is not None else None
        rec = {
            "session_id": f"{SEED_VERSION}-{n}", "beneficiary_id": bid,
            "beneficiary_name": registry.get(bid, {}).get("name"), "visit_type": vt,
            "visit_date": vdate.isoformat(), "weight_kg": weight, "vaccinations_given": given,
            "vaccinations_due": due, "ifa_tablets_given": ifa,
            "next_visit_date": next_date.isoformat() if next_date else None,
            "danger_signs": [], "danger_review": [], "danger_details": [], "referral_status": "NONE",
            "field_confidence": {k: "high" for k in ("beneficiary_id", "visit_type", "weight_kg", "next_visit_date")},
            "confirmation_status": "CONFIRMED", "confirmed_via": "seed", "language": "en",
            "transcript": [{"role": "worker", "text": transcript, "source": "seed"}], "demo_data": True,
        }
        if danger and danger.startswith("REVIEW:"):
            sid = danger.split(":", 1)[1]
            rec["danger_review"] = [sid]
            rec["danger_details"] = [_danger_entry(sid, "REVIEW", "bukhar hai shayad",
                                                   "could not be confirmed by voice")]
            rec["referral_status"] = "REVIEW_REQUIRED"
        elif danger:
            phrase = "bleeding ho rahi hai" if danger == "PREG_BLEEDING" else "tez bukhar"
            rec["danger_signs"] = [danger]
            rec["danger_details"] = [_danger_entry(danger, "POSITIVE", phrase, "listed danger sign mentioned")]
            rec["referral_status"] = "REFER_NOW"
        fus = generate_followups(rec, vdate)
        for f in fus:
            if (n, f["action_type"]) in _DONE:
                f["status"] = "DONE"
        created = datetime.combine(vdate, time(9 + n % 8, (n * 7) % 60), tzinfo=timezone.utc)
        # A seeded record must never look newer than a visit recorded right now: keep today's
        # synthetic visits earlier than the moment of seeding, so real visits sort first.
        latest = datetime.now(timezone.utc) - timedelta(minutes=30 + n)
        if created > latest:
            created = latest.replace(second=0, microsecond=0)
        out.append((f"{SEED_VERSION}:{n}", rec, fus, created.isoformat(timespec="seconds")))
    return out


def seed_demo_visits(db, today: date, reset: bool = False) -> dict:
    """Insert the demo visits (idempotent). reset=True first removes previously seeded rows only."""
    removed = db.delete_seeded() if reset else 0
    registry = {r["synthetic_external_id"]: r for r in db.registry()}
    created = 0
    for key, rec, fus, created_at in build_records(today, registry):
        _vid, was_new = db.save_visit(record=rec, idempotency_key=key, session_id=rec["session_id"],
                                      source="seed", followups=fus, created_at=created_at)
        if was_new:
            created += 1
            db.add_event(rec["session_id"], "visit_saved", None, "seed")
    return {"created": created, "removed": removed, "total_seed_visits": len(_VISITS)}
