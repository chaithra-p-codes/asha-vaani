"""Deterministic follow-up generation from a CONFIRMED record.

Rules (documented in docs/architecture.md). No vaccination schedule, interval or clinical
advice is invented: dates come only from what the worker said.
  R1 referral_status == REFER_NOW        -> URGENT "complete the PHC referral today" (due today)
  R2 referral_status == REVIEW_REQUIRED  -> HIGH   "review unclear danger-sign mention with ANM"
  R3 next_visit_date recorded            -> NORMAL "next <type> visit on <date>" (due that date)
  R4 vaccinations_due recorded           -> NORMAL "vaccines due: ..." (due at the recorded next
                                            visit date if one was stated, otherwise undated)
  R5 next_visit_date missing             -> NORMAL "schedule next visit (date not recorded)"
  R6 weight missing                      -> LOW    "record weight at next visit"
"""
from __future__ import annotations

from datetime import date

from .readback import join_list, prompts, vaccine_spoken, visit_type_spoken
from .dates import speak_date

LANGS = ("en", "hi", "kn")


def _i18n(key: str, **kw_by_lang) -> dict:
    tpl = prompts()["followups"][key]
    out = {}
    for lang in LANGS:
        kw = {k: (v(lang) if callable(v) else v) for k, v in kw_by_lang.items()}
        out[lang] = tpl[lang].format(**kw) if kw else tpl[lang]
    return out


def _vt_display(vt: str | None, lang: str) -> str:
    if not vt:
        return ""
    return prompts().get("visit_types_display", {}).get(vt, {}).get(lang, vt)


def _display_date(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    if lang == "en":
        return d.strftime("%d %b %Y").lstrip("0")
    return f"{d.day}/{d.month}/{d.year}"


def generate(record: dict, today: date) -> list[dict]:
    out: list[dict] = []
    vt = record.get("visit_type")
    if record.get("referral_status") == "REFER_NOW":
        out.append({"action_type": "REFERRAL", "priority": "URGENT", "due_date": today.isoformat(),
                    "title_i18n": _i18n("referral"), "rule": "R1"})
    elif record.get("referral_status") == "REVIEW_REQUIRED":
        out.append({"action_type": "DANGER_REVIEW", "priority": "HIGH", "due_date": today.isoformat(),
                    "title_i18n": _i18n("review"), "rule": "R2"})
    nv = record.get("next_visit_date")
    if nv:
        out.append({"action_type": "NEXT_VISIT", "priority": "NORMAL", "due_date": nv, "rule": "R3",
                    "title_i18n": _i18n("next_visit", type=lambda l: _vt_display(vt, l))})
    due = record.get("vaccinations_due") or []
    if due:
        out.append({"action_type": "VACCINE_DUE", "priority": "NORMAL", "due_date": nv, "rule": "R4",
                    "title_i18n": _i18n("vaccines_due", list=lambda l: join_list(list(due), "en" if l == "en" else l))})
    if not nv:
        out.append({"action_type": "SCHEDULE_VISIT", "priority": "NORMAL", "due_date": None, "rule": "R5",
                    "title_i18n": _i18n("schedule")})
    if record.get("weight_kg") in (None, ""):
        out.append({"action_type": "RECORD_WEIGHT", "priority": "LOW", "due_date": nv, "rule": "R6",
                    "title_i18n": _i18n("weight")})
    for f in out:
        f["title"] = f["title_i18n"]["en"]
    return out


def spoken_summary(followups: list[dict], lang: str, record: dict) -> str:
    """Short spoken list (max 3 items) using spelled-out dates/vaccine names."""
    items = []
    for f in followups[:3]:
        if f["action_type"] == "NEXT_VISIT":
            vt = record.get("visit_type")
            tpl = prompts()["followups"]["next_visit_spoken"][lang]
            items.append(tpl.format(type=visit_type_spoken(vt, lang) if vt else "",
                                    date=speak_date(date.fromisoformat(f["due_date"]), lang)))
        elif f["action_type"] == "VACCINE_DUE":
            tpl = prompts()["followups"]["vaccines_due"][lang]
            items.append(tpl.format(list=join_list([vaccine_spoken(v, lang) for v in record.get("vaccinations_due") or []],
                                                   lang)))
        else:
            items.append(f["title_i18n"][lang])
    return ". ".join(items) + "." if items else ""
