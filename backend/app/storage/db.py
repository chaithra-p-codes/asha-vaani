"""SQLite persistence (prototype). Sensitive payloads are AES-GCM encrypted; only the
columns needed for filtering/indexing (visit type, dates, referral status) are plaintext,
and all beneficiaries are synthetic. Calls are synchronous and short; async code runs them
via asyncio.to_thread. A process-wide lock serialises writes."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .crypto import Cipher
from .seed import SYNTHETIC_BENEFICIARIES

SCHEMA = """
CREATE TABLE IF NOT EXISTS beneficiaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    synthetic_external_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    beneficiary_id TEXT,
    visit_type TEXT,
    visit_date TEXT,
    payload_enc BLOB NOT NULL,
    confirmation_status TEXT NOT NULL,
    referral_status TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'live',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_visits_created ON visits(created_at);
CREATE TABLE IF NOT EXISTS followups (
    id TEXT PRIMARY KEY,
    visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
    beneficiary_id TEXT,
    action_type TEXT NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    priority TEXT NOT NULL DEFAULT 'NORMAL',
    payload_enc BLOB NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    field_name TEXT,
    reason_code TEXT,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_account_alias TEXT NOT NULL,
    service TEXT NOT NULL,
    estimated_units REAL NOT NULL,
    unit TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    language TEXT NOT NULL,
    mode TEXT NOT NULL,
    state TEXT NOT NULL,
    draft_enc BLOB,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    name TEXT NOT NULL,
    value_ms REAL NOT NULL,
    timestamp TEXT NOT NULL
);
"""

PRIORITY_ORDER = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Database:
    def __init__(self, path: str, cipher: Cipher):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.cipher = cipher
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)

    def close(self):
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ register
    def seed_beneficiaries(self) -> int:
        n = 0
        with self._lock:
            for b in SYNTHETIC_BENEFICIARIES:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO beneficiaries(synthetic_external_id, name, category, aliases_json, created_at)"
                    " VALUES (?,?,?,?,?)",
                    (b["synthetic_external_id"], b["name"], b.get("category"), json.dumps(b.get("aliases", []),
                                                                                         ensure_ascii=False), utcnow()))
                n += cur.rowcount
        return n

    def registry(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM beneficiaries ORDER BY synthetic_external_id").fetchall()
        return [{"synthetic_external_id": r["synthetic_external_id"], "name": r["name"], "category": r["category"],
                 "aliases": json.loads(r["aliases_json"])} for r in rows]

    # ------------------------------------------------------------------ visits
    def save_visit(self, *, record: dict, idempotency_key: str, session_id: str, source: str,
                   followups: list[dict], created_at: str | None = None) -> tuple[str, bool]:
        """Insert visit + follow-ups atomically. Returns (visit_id, created). A repeated
        idempotency key returns the original visit and creates nothing."""
        with self._lock:
            row = self._conn.execute("SELECT id FROM visits WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if row:
                return row["id"], False
            visit_id = str(uuid.uuid4())
            now = created_at or utcnow()
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    "INSERT INTO visits(id, session_id, idempotency_key, beneficiary_id, visit_type, visit_date,"
                    " payload_enc, confirmation_status, referral_status, source, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (visit_id, session_id, idempotency_key, record.get("beneficiary_id"), record.get("visit_type"),
                     record.get("visit_date"), self.cipher.encrypt(record), "CONFIRMED",
                     record.get("referral_status", "NONE"), source, now))
                for f in followups:
                    self._conn.execute(
                        "INSERT INTO followups(id, visit_id, beneficiary_id, action_type, due_date, status, priority,"
                        " payload_enc, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (str(uuid.uuid4()), visit_id, record.get("beneficiary_id"), f["action_type"], f.get("due_date"),
                         f.get("status", "PENDING"), f.get("priority", "NORMAL"),
                         self.cipher.encrypt({"title": f["title"], "title_i18n": f.get("title_i18n", {})}), now))
                self._conn.execute("COMMIT")
            except sqlite3.IntegrityError:
                self._conn.execute("ROLLBACK")
                row = self._conn.execute("SELECT id FROM visits WHERE idempotency_key = ?",
                                         (idempotency_key,)).fetchone()
                if row:
                    return row["id"], False
                raise
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            return visit_id, True

    def _visit_row(self, r) -> dict:
        payload = self.cipher.decrypt(r["payload_enc"])
        return {**payload, "id": r["id"], "saved_at": r["created_at"], "source": r["source"],
                "confirmation_status": r["confirmation_status"], "referral_status": r["referral_status"]}

    def list_visits(self, *, q: str | None = None, visit_type: str | None = None, referral: str | None = None,
                    limit: int = 100, date_from: str | None = None, date_to: str | None = None,
                    beneficiary_id: str | None = None, source: str | None = None) -> list[dict]:
        sql = "SELECT * FROM visits WHERE 1=1"
        args: list = []
        if visit_type:
            sql += " AND visit_type = ?"
            args.append(visit_type)
        if referral == "ANY":
            sql += " AND referral_status != 'NONE'"
        elif referral:
            sql += " AND referral_status = ?"
            args.append(referral)
        if date_from:
            sql += " AND visit_date >= ?"
            args.append(date_from)
        if date_to:
            sql += " AND visit_date <= ?"
            args.append(date_to)
        if beneficiary_id:
            sql += " AND beneficiary_id = ?"
            args.append(beneficiary_id)
        if source:
            sql += " AND source = ?"
            args.append(source)
        sql += " ORDER BY visit_date DESC, created_at DESC LIMIT ?"
        args.append(max(1, min(limit, 500)))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        out = [self._visit_row(r) for r in rows]
        if q:
            ql = q.lower()
            out = [v for v in out if ql in str(v.get("beneficiary_id", "")).lower()
                   or ql in str(v.get("beneficiary_name") or "").lower()]
        return out

    def get_visit(self, visit_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM visits WHERE id = ?", (visit_id,)).fetchone()
            if not r:
                return None
            fus = self._conn.execute("SELECT * FROM followups WHERE visit_id = ?", (visit_id,)).fetchall()
            events = self._conn.execute(
                "SELECT event_type, field_name, reason_code, timestamp FROM session_events WHERE session_id = ?"
                " ORDER BY id", (r["session_id"],)).fetchall()
        v = self._visit_row(r)
        v["followups"] = [self._fu_row(f) for f in fus]
        v["audit"] = [dict(e) for e in events]
        return v

    # ------------------------------------------------------------------ follow-ups
    def _fu_row(self, f) -> dict:
        payload = self.cipher.decrypt(f["payload_enc"])
        return {"id": f["id"], "visit_id": f["visit_id"], "beneficiary_id": f["beneficiary_id"],
                "action_type": f["action_type"], "due_date": f["due_date"], "status": f["status"],
                "priority": f["priority"], "title": payload.get("title"), "title_i18n": payload.get("title_i18n", {}),
                "created_at": f["created_at"]}

    def list_followups(self, status: str | None = "PENDING", beneficiary_id: str | None = None) -> list[dict]:
        sql = ("SELECT f.*, v.visit_type AS v_type, v.visit_date AS v_date, v.source AS v_source, "
               "b.name AS b_name FROM followups f JOIN visits v ON v.id = f.visit_id "
               "LEFT JOIN beneficiaries b ON b.synthetic_external_id = f.beneficiary_id WHERE 1=1")
        args = []
        if status:
            sql += " AND f.status = ?"
            args.append(status)
        if beneficiary_id:
            sql += " AND f.beneficiary_id = ?"
            args.append(beneficiary_id)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        out = []
        for r in rows:
            f = self._fu_row(r)
            f.update({"visit_type": r["v_type"], "visit_date": r["v_date"], "source": r["v_source"],
                      "beneficiary_name": r["b_name"]})
            out.append(f)
        out.sort(key=lambda f: (PRIORITY_ORDER.get(f["priority"], 9), f["due_date"] or "9999", f["created_at"]))
        return out

    def set_followup_status(self, fid: str, status: str) -> bool:
        if status not in ("PENDING", "DONE"):
            raise ValueError("invalid status")
        with self._lock:
            cur = self._conn.execute("UPDATE followups SET status = ? WHERE id = ?", (status, fid))
        return cur.rowcount == 1

    # ------------------------------------------------------------------ dashboard
    def dashboard(self, today_iso: str) -> dict:
        with self._lock:
            today_count = self._conn.execute(
                "SELECT COUNT(*) c FROM visits WHERE visit_date = ?", (today_iso,)).fetchone()["c"]
            beneficiaries = self._conn.execute("SELECT COUNT(*) c FROM beneficiaries").fetchone()["c"]
            overdue = self._conn.execute("SELECT COUNT(*) c FROM followups WHERE status='PENDING' AND due_date < ?",
                                         (today_iso,)).fetchone()["c"]
            due_today = self._conn.execute("SELECT COUNT(*) c FROM followups WHERE status='PENDING' AND due_date = ?",
                                           (today_iso,)).fetchone()["c"]
            done_today = self._conn.execute(
                "SELECT COUNT(*) c FROM visits WHERE visit_date = ? AND referral_status != 'NONE'",
                (today_iso,)).fetchone()["c"]
            seeded = self._conn.execute("SELECT COUNT(*) c FROM visits WHERE source='seed'").fetchone()["c"]
            total = self._conn.execute("SELECT COUNT(*) c FROM visits").fetchone()["c"]
            pending = self._conn.execute("SELECT COUNT(*) c FROM followups WHERE status='PENDING'").fetchone()["c"]
            urgent = self._conn.execute(
                "SELECT COUNT(*) c FROM followups WHERE status='PENDING' AND priority='URGENT'").fetchone()["c"]
            rows = self._conn.execute(
                "SELECT * FROM visits ORDER BY visit_date DESC, created_at DESC LIMIT 6").fetchall()
        recent = []
        for r in rows:
            v = self._visit_row(r)
            recent.append({k: v.get(k) for k in ("id", "beneficiary_id", "beneficiary_name", "visit_type", "visit_date",
                                                  "referral_status", "saved_at", "source", "danger_signs",
                                                  "confirmation_status")})
        upcoming = [f for f in self.list_followups("PENDING")][:6]
        return {"visits_today": today_count, "visits_total": total, "pending_followups": pending,
                "urgent_referrals": urgent, "total_beneficiaries": beneficiaries, "overdue_followups": overdue,
                "due_today_followups": due_today, "referrals_today": done_today, "recent": recent,
                "upcoming_followups": upcoming, "demo_visits": seeded}

    # ------------------------------------------------------------------ beneficiaries / referrals / reports
    def beneficiaries_summary(self, today_iso: str) -> list[dict]:
        reg = self.registry()
        with self._lock:
            vrows = self._conn.execute(
                "SELECT beneficiary_id, COUNT(*) n, MAX(visit_date) last_date FROM visits GROUP BY beneficiary_id"
            ).fetchall()
            last_type = {r["beneficiary_id"]: r["visit_type"] for r in self._conn.execute(
                "SELECT v.beneficiary_id, v.visit_type FROM visits v JOIN (SELECT beneficiary_id, MAX(visit_date) d "
                "FROM visits GROUP BY beneficiary_id) m ON m.beneficiary_id = v.beneficiary_id AND m.d = v.visit_date")}
            frows = self._conn.execute(
                "SELECT beneficiary_id, action_type, due_date, priority FROM followups WHERE status='PENDING'"
            ).fetchall()
        visits = {r["beneficiary_id"]: (r["n"], r["last_date"]) for r in vrows}
        out = []
        for b in reg:
            bid = b["synthetic_external_id"]
            mine = [f for f in frows if f["beneficiary_id"] == bid]
            dated = sorted(f["due_date"] for f in mine if f["due_date"])
            referred = any(f["action_type"] in ("REFERRAL", "DANGER_REVIEW") for f in mine)
            n, last = visits.get(bid, (0, None))
            if referred:
                status = "REFERRED"
            elif any(d <= today_iso for d in dated):
                status = "FOLLOWUP_DUE"
            elif mine:
                status = "ACTIVE"
            elif n:
                status = "COMPLETED"
            else:
                status = "NO_VISITS"
            out.append({**{k: b[k] for k in ("synthetic_external_id", "name", "category")}, "visits": n,
                        "last_visit_date": last, "last_visit_type": last_type.get(bid),
                        "pending_followups": len(mine), "next_due_date": dated[0] if dated else None,
                        "status": status})
        return out

    def beneficiary_profile(self, bid: str, today_iso: str) -> dict | None:
        b = next((x for x in self.beneficiaries_summary(today_iso) if x["synthetic_external_id"] == bid), None)
        if not b:
            return None
        reg = next(x for x in self.registry() if x["synthetic_external_id"] == bid)
        visits = self.list_visits(beneficiary_id=bid, limit=200)
        fus = self.list_followups(None, beneficiary_id=bid)
        for v in visits:
            v.pop("transcript", None)
            v.pop("field_evidence", None)
        referrals = [v for v in visits if v.get("referral_status") != "NONE"]
        timeline = []
        for v in visits:
            timeline.append({"date": v.get("visit_date"), "kind": "visit", "visit_id": v["id"],
                             "visit_type": v.get("visit_type"), "referral_status": v.get("referral_status"),
                             "weight_kg": v.get("weight_kg"), "source": v.get("source")})
            for d in v.get("danger_details") or []:
                if d.get("status") in ("POSITIVE", "REVIEW"):
                    timeline.append({"date": v.get("visit_date"), "kind": "referral" if d["status"] == "POSITIVE"
                                     else "review", "visit_id": v["id"], "sign": d.get("id"), "label": d.get("label")})
        for f in fus:
            timeline.append({"date": f.get("due_date"), "kind": "followup", "followup_id": f["id"],
                             "action_type": f["action_type"], "status": f["status"], "priority": f["priority"],
                             "title_i18n": f.get("title_i18n"), "visit_id": f["visit_id"]})
        timeline.sort(key=lambda e: (e["date"] or "0000"), reverse=True)
        latest = visits[0] if visits else None
        return {**b, "aliases": reg.get("aliases", []), "visits_list": visits, "followups": fus,
                "referrals": referrals, "latest": latest, "timeline": timeline}

    def referrals(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM visits WHERE referral_status != 'NONE' ORDER BY visit_date DESC, created_at DESC"
            ).fetchall()
            frows = self._conn.execute(
                "SELECT id, visit_id, status, action_type FROM followups WHERE action_type IN ('REFERRAL','DANGER_REVIEW')"
            ).fetchall()
        fu_by_visit = {r["visit_id"]: dict(r) for r in frows}
        out = []
        for r in rows:
            v = self._visit_row(r)
            fu = fu_by_visit.get(v["id"])
            out.append({"visit_id": v["id"], "beneficiary_id": v.get("beneficiary_id"),
                        "beneficiary_name": v.get("beneficiary_name"), "visit_type": v.get("visit_type"),
                        "visit_date": v.get("visit_date"), "referral_status": v.get("referral_status"),
                        "signs": [d for d in (v.get("danger_details") or []) if d.get("status") in ("POSITIVE", "REVIEW")],
                        "followup_id": fu["id"] if fu else None,
                        "state": ("CLOSED" if fu and fu["status"] == "DONE" else "OPEN"), "source": v.get("source"),
                        "saved_at": v.get("saved_at")})
        return out

    def reports(self, date_from: str, date_to: str) -> dict:
        with self._lock:
            by_type = {r["visit_type"]: r["n"] for r in self._conn.execute(
                "SELECT visit_type, COUNT(*) n FROM visits WHERE visit_date BETWEEN ? AND ? GROUP BY visit_type",
                (date_from, date_to))}
            by_day = {r["visit_date"]: r["n"] for r in self._conn.execute(
                "SELECT visit_date, COUNT(*) n FROM visits WHERE visit_date BETWEEN ? AND ? GROUP BY visit_date",
                (date_from, date_to))}
            fstat = {r["status"]: r["n"] for r in self._conn.execute(
                "SELECT f.status, COUNT(*) n FROM followups f JOIN visits v ON v.id = f.visit_id "
                "WHERE v.visit_date BETWEEN ? AND ? GROUP BY f.status", (date_from, date_to))}
            refs = {r["referral_status"]: r["n"] for r in self._conn.execute(
                "SELECT referral_status, COUNT(*) n FROM visits WHERE visit_date BETWEEN ? AND ? "
                "AND referral_status != 'NONE' GROUP BY referral_status", (date_from, date_to))}
            sources = {r["source"]: r["n"] for r in self._conn.execute(
                "SELECT source, COUNT(*) n FROM visits WHERE visit_date BETWEEN ? AND ? GROUP BY source",
                (date_from, date_to))}
        days = []
        d0 = datetime.fromisoformat(date_from).date()
        d1 = datetime.fromisoformat(date_to).date()
        while d0 <= d1 and len(days) < 400:
            days.append({"date": d0.isoformat(), "visits": by_day.get(d0.isoformat(), 0)})
            d0 += timedelta(days=1)
        return {"from": date_from, "to": date_to,
                "visits_by_type": {k: by_type.get(k, 0) for k in ("ANC", "PNC", "NEWBORN", "IMMUNISATION")},
                "visits_by_day": days, "total_visits": sum(by_type.values()),
                "followups": {"pending": fstat.get("PENDING", 0), "done": fstat.get("DONE", 0)},
                "referrals": {"refer_now": refs.get("REFER_NOW", 0), "review": refs.get("REVIEW_REQUIRED", 0)},
                "sources": sources}

    def delete_seeded(self) -> int:
        with self._lock:
            self._conn.execute("DELETE FROM followups WHERE visit_id IN (SELECT id FROM visits WHERE source='seed')")
            n = self._conn.execute("DELETE FROM visits WHERE source='seed'").rowcount
            self._conn.execute("DELETE FROM session_events WHERE session_id LIKE 'seed-%'")
        return n

    # ------------------------------------------------------------------ audit / usage / metrics
    def add_event(self, session_id: str, event_type: str, field_name: str | None = None,
                  reason_code: str | None = None) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO session_events(session_id, event_type, field_name, reason_code, timestamp)"
                               " VALUES (?,?,?,?,?)", (session_id, event_type, field_name, reason_code, utcnow()))

    def add_usage(self, alias: str, service: str, units: float, unit: str) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO service_usage(provider_account_alias, service, estimated_units, unit,"
                               " timestamp) VALUES (?,?,?,?,?)", (alias, service, units, unit, utcnow()))

    def usage_summary(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT provider_account_alias alias, service, unit, SUM(estimated_units) total, COUNT(*) n"
                " FROM service_usage GROUP BY provider_account_alias, service, unit").fetchall()
        return [dict(r) for r in rows]

    def add_metric(self, session_id: str | None, name: str, value_ms: float) -> None:
        with self._lock:
            self._conn.execute("INSERT INTO metrics(session_id, name, value_ms, timestamp) VALUES (?,?,?,?)",
                               (session_id, name, float(value_ms), utcnow()))

    def metrics_summary(self) -> dict:
        with self._lock:
            rows = self._conn.execute("SELECT name, value_ms FROM metrics").fetchall()
        by: dict[str, list[float]] = {}
        for r in rows:
            by.setdefault(r["name"], []).append(r["value_ms"])
        out = {}
        for name, vals in sorted(by.items()):
            vals.sort()
            p95 = vals[min(len(vals) - 1, max(0, int(round(0.95 * len(vals) + 0.5)) - 1))]
            out[name] = {"n": len(vals), "median_ms": round(statistics.median(vals), 1), "p95_ms": round(p95, 1)}
        return out

    # ------------------------------------------------------------------ sessions
    def save_session(self, session_id: str, token: str | None, language: str, mode: str, state: str,
                     draft: dict, ttl_minutes: int) -> None:
        now = datetime.now(timezone.utc)
        with self._lock:
            row = self._conn.execute("SELECT token_hash FROM sessions WHERE id = ?", (session_id,)).fetchone()
            enc = self.cipher.encrypt(draft)
            if row:
                self._conn.execute("UPDATE sessions SET state=?, draft_enc=?, updated_at=?, expires_at=? WHERE id=?",
                                   (state, enc, now.isoformat(timespec="seconds"),
                                    (now + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds"), session_id))
            else:
                self._conn.execute(
                    "INSERT INTO sessions(id, token_hash, language, mode, state, draft_enc, created_at, updated_at,"
                    " expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (session_id, token_hash(token or ""), language, mode, state, enc,
                     now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
                     (now + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")))

    def load_session(self, session_id: str) -> dict | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not r:
            return None
        if r["expires_at"] < utcnow():
            return None
        return {"id": r["id"], "token_hash": r["token_hash"], "language": r["language"], "mode": r["mode"],
                "state": r["state"], "draft": self.cipher.decrypt(r["draft_enc"]) if r["draft_enc"] else {}}

    def delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

    # ------------------------------------------------------------------ retention
    def purge_older_than(self, hours: int) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
        with self._lock:
            counts = {}
            counts["followups"] = self._conn.execute(
                "DELETE FROM followups WHERE visit_id IN (SELECT id FROM visits WHERE created_at < ? AND source != 'seed')",
                (cutoff,)).rowcount
            counts["visits"] = self._conn.execute("DELETE FROM visits WHERE created_at < ? AND source != 'seed'",
                                                  (cutoff,)).rowcount
            counts["sessions"] = self._conn.execute("DELETE FROM sessions WHERE updated_at < ? OR expires_at < ?",
                                                    (cutoff, utcnow())).rowcount
            counts["session_events"] = self._conn.execute("DELETE FROM session_events WHERE timestamp < ?",
                                                          (cutoff,)).rowcount
            counts["metrics"] = self._conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,)).rowcount
        return counts

    def delete_all_demo_data(self) -> dict:
        """Delete every visit, follow-up, session, audit event, metric and usage row.
        The synthetic beneficiary register is kept (it contains no collected data)."""
        with self._lock:
            counts = {t: self._conn.execute(f"DELETE FROM {t}").rowcount
                      for t in ("followups", "visits", "sessions", "session_events", "metrics", "service_usage")}
            self._conn.execute("VACUUM")
        return counts
