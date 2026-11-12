"""Deterministic validation of the visit draft. Nothing is accepted silently:
implausible or ambiguous values are kept but marked `confirm`, and an issue is raised
so the read-back says "please confirm" and reads the value slowly."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

VISIT_TYPES = ("ANC", "PNC", "NEWBORN", "IMMUNISATION")
REQUIRED = ("beneficiary_id", "visit_type")
ASK_ONCE = ("weight_kg", "next_visit_date")  # asked once, can be skipped

# Plausibility ranges (kg). Not clinical thresholds: only "did we hear this right?" checks.
WEIGHT_RANGES = {
    "ANC": (30.0, 150.0),
    "PNC": (30.0, 150.0),
    "NEWBORN": (0.5, 6.5),
    "IMMUNISATION": (0.5, 30.0),
    None: (0.5, 150.0),
}


@dataclass
class Issue:
    field: str
    code: str
    message: str

    def public(self):
        return {"field": self.field, "code": self.code, "message": self.message}


def validate(record: dict, field_meta: dict, today: date, registry_ids: set[str]) -> list[Issue]:
    """Mutates field_meta[field]['confidence'] to 'confirm' where needed; returns issues."""
    issues: list[Issue] = []

    def flag(field, code, msg):
        issues.append(Issue(field, code, msg))
        meta = field_meta.setdefault(field, {})
        if meta.get("confidence") != "missing":
            meta["confidence"] = "confirm"

    bid = record.get("beneficiary_id")
    if bid is not None:
        if not str(bid).isdigit():
            flag("beneficiary_id", "id_not_digits", "Beneficiary ID must contain digits only")
        elif not (3 <= len(str(bid)) <= 12):
            flag("beneficiary_id", "id_length", "Beneficiary ID length looks wrong")
        elif registry_ids and str(bid) not in registry_ids:
            flag("beneficiary_id", "id_unknown", "ID is not in the synthetic register")

    vt = record.get("visit_type")
    if vt is not None and vt not in VISIT_TYPES:
        flag("visit_type", "visit_type_invalid", "Visit type must be ANC, PNC, newborn or immunisation")

    w = record.get("weight_kg")
    if w is not None:
        try:
            wv = float(w)
            lo, hi = WEIGHT_RANGES.get(vt, WEIGHT_RANGES[None])
            if not (lo <= wv <= hi):
                flag("weight_kg", "weight_out_of_range",
                     f"Weight {wv:g} kg is outside the expected range for {vt or 'this visit'}; please confirm")
        except (TypeError, ValueError):
            flag("weight_kg", "weight_not_number", "Weight is not a number")

    vd = record.get("visit_date")
    vd_date = None
    if vd:
        try:
            vd_date = date.fromisoformat(vd)
            if vd_date > today:
                flag("visit_date", "visit_date_future", "Visit date is in the future")
            elif vd_date < today - timedelta(days=60):
                flag("visit_date", "visit_date_old", "Visit date is more than 60 days ago")
        except ValueError:
            flag("visit_date", "date_invalid", "Visit date is not a valid date")

    nv = record.get("next_visit_date")
    if nv:
        try:
            nv_date = date.fromisoformat(nv)
            ref = vd_date or today
            if nv_date <= ref:
                flag("next_visit_date", "next_before_visit", "Next visit must be after the visit date")
            elif nv_date > ref + timedelta(days=366):
                flag("next_visit_date", "next_too_far", "Next visit is more than a year away")
        except ValueError:
            flag("next_visit_date", "date_invalid", "Next visit date is not a valid date")

    given = set(record.get("vaccinations_given") or [])
    due = set(record.get("vaccinations_due") or [])
    both = given & due
    for v in sorted(both):
        flag("vaccinations_given", "vaccine_given_and_due", f"{v} is listed as both given and due")

    for f in REQUIRED:
        if record.get(f) in (None, "", []):
            issues.append(Issue(f, "missing_required", {"beneficiary_id": "Beneficiary ID is required before saving",
                                                        "visit_type": "Visit type is required before saving"}[f]))
            field_meta.setdefault(f, {})["confidence"] = "missing"
    return issues


def missing_to_ask(record: dict, asked: set[str]) -> str | None:
    """Next field to ask about (one at a time): required first, then ask-once fields."""
    for f in REQUIRED:
        if record.get(f) in (None, "", []) and f not in asked:
            return f
    for f in ASK_ONCE:
        if record.get(f) in (None, "", []) and f not in asked:
            return f
    return None


def can_save(record: dict) -> bool:
    return all(record.get(f) not in (None, "", []) for f in REQUIRED)
