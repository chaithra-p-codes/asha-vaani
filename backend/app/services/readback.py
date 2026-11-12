"""Template-based read-back. Every spoken sentence comes from templates/prompts.json; no
free-form generation. Numbers, IDs and dates are spelled out in the session language."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from .dates import speak_date
from .numbers import speak_decimal, speak_digits

_PROMPTS_PATH = Path(__file__).resolve().parent.parent / "templates" / "prompts.json"

VACCINE_SPOKEN = {
    "TT/Td": {"en": "T T", "hi": "टी टी", "kn": "ಟಿ ಟಿ"},
    "BCG": {"en": "B C G", "hi": "बी सी जी", "kn": "ಬಿ ಸಿ ಜಿ"},
    "OPV": {"en": "O P V", "hi": "ओ पी वी", "kn": "ಒ ಪಿ ವಿ"},
    "Hepatitis B": {"en": "Hepatitis B", "hi": "हेपेटाइटिस बी", "kn": "ಹೆಪಟೈಟಿಸ್ ಬಿ"},
    "Pentavalent": {"en": "Penta", "hi": "पेंटा", "kn": "ಪೆಂಟಾ"},
    "Rotavirus": {"en": "Rota", "hi": "रोटा", "kn": "ರೋಟಾ"},
    "IPV": {"en": "I P V", "hi": "आई पी वी", "kn": "ಐ ಪಿ ವಿ"},
    "PCV": {"en": "P C V", "hi": "पी सी वी", "kn": "ಪಿ ಸಿ ವಿ"},
    "MR": {"en": "M R", "hi": "एम आर", "kn": "ಎಂ ಆರ್"},
    "JE": {"en": "J E", "hi": "जे ई", "kn": "ಜೆ ಇ"},
    "DPT booster": {"en": "D P T booster", "hi": "डी पी टी बूस्टर", "kn": "ಡಿ ಪಿ ಟಿ ಬೂಸ್ಟರ್"},
    "Vitamin A": {"en": "Vitamin A", "hi": "विटामिन ए", "kn": "ವಿಟಮಿನ್ ಎ"},
}
_AND = {"en": "and", "hi": "और", "kn": "ಮತ್ತು"}


@lru_cache(maxsize=1)
def prompts() -> dict:
    return json.loads(_PROMPTS_PATH.read_text(encoding="utf-8"))


def t(key: str, lang: str, **kw) -> str:
    entry = prompts()[key]
    text = entry.get(lang) or entry["en"]
    return text.format(**kw) if kw else text


def visit_type_spoken(vt: str, lang: str) -> str:
    return prompts()["visit_types"].get(vt, {}).get(lang, vt)


def field_name(field: str, lang: str) -> str:
    return prompts()["field_names"].get(field, {}).get(lang, field)


def vaccine_spoken(label: str, lang: str) -> str:
    base, _, dose = label.partition("-")
    booster = ""
    if base.endswith(" booster") and base not in VACCINE_SPOKEN:
        base, booster = base[:-8], " booster"
    spoken = VACCINE_SPOKEN.get(base, {}).get(lang, base)
    if dose.isdigit():
        from .numbers import speak_int
        spoken += " " + speak_int(int(dose), lang)
    return spoken + booster


def join_list(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {_AND.get(lang, 'and')} " + items[-1]


def field_phrase(field: str, value, lang: str, record: dict | None = None) -> str:
    if value in (None, "", []):
        return t("not_heard", lang, field=field_name(field, lang))
    if field == "beneficiary_id":
        return t("f_id", lang, digits=speak_digits(str(value), lang))
    if field == "beneficiary_name":
        return t("f_name", lang, name=value)
    if field == "visit_type":
        return t("f_visit_type", lang, type=visit_type_spoken(value, lang))
    if field == "weight_kg":
        return t("f_weight", lang, w=speak_decimal(float(value), lang))
    if field == "vaccinations_given":
        return t("f_vac_given", lang, list=join_list([vaccine_spoken(v, lang) for v in value], lang))
    if field == "vaccinations_due":
        return t("f_vac_due", lang, list=join_list([vaccine_spoken(v, lang) for v in value], lang))
    if field == "ifa_tablets_given":
        return t("f_ifa_yes" if value else "f_ifa_no", lang)
    if field == "next_visit_date":
        return t("f_next_visit", lang, date=speak_date(date.fromisoformat(value), lang))
    if field == "visit_date":
        return t("f_visit_date", lang, date=speak_date(date.fromisoformat(value), lang))
    return str(value)


READ_ORDER = ["beneficiary_id", "beneficiary_name", "visit_type", "weight_kg", "vaccinations_given",
              "vaccinations_due", "ifa_tablets_given", "next_visit_date"]


def readback_text(record: dict, meta: dict, lang: str, danger_labels: list[str] | None = None) -> str:
    parts = [t("readback_intro", lang)]
    for f in READ_ORDER:
        v = record.get(f)
        if v in (None, "", []):
            if f in ("beneficiary_name", "vaccinations_given", "vaccinations_due", "ifa_tablets_given"):
                continue
            parts.append(t("not_heard", lang, field=field_name(f, lang)) + ".")
            continue
        phrase = field_phrase(f, v, lang, record)
        if (meta.get(f) or {}).get("confidence") == "confirm":
            phrase += ", " + t("please_confirm", lang)
        parts.append(phrase + ".")
    if record.get("visit_date") and record.get("visit_date") != meta.get("_today"):
        parts.append(field_phrase("visit_date", record["visit_date"], lang) + ".")
    if danger_labels:
        parts.append(t("f_referral", lang, signs=join_list(danger_labels, lang)) + ".")
    parts.append(t("confirm_q", lang))
    return " ".join(parts)
