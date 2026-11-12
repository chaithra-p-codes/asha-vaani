"""Voice correction / confirmation understanding (deterministic).

Resolution order for an utterance heard after a read-back or question:
  advice request -> undo -> repeat -> explicit field values (patch) -> bare value
  (apply to the last single field read back, else ask which field) -> yes / no / skip /
  unsure keywords -> not understood.
A record is never saved from anything but an explicit YES.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .extraction import VACCINE_TERMS, Extraction, RuleExtractor
from .normalise import WORD_CHARS, find_phrases, match_form, tokenize
from .numbers import parse_number


def _set(*ws):
    return {match_form(w) for w in ws}


YES = _set("haan", "haa", "ha", "han", "haanji", "haan ji", "ji haan", "jee haan", "हाँ", "हां", "हा", "जी हां",
           "जी हाँ", "sahi", "सही", "theek", "thik", "ठीक", "correct", "right", "yes", "yeah", "yep", "ok",
           "okay", "confirm", "confirmed", "save", "सेव", "ಹೌದು", "houdu", "howdu", "ಸರಿ", "sari", "ಸೇವ್",
           "perfect", "bilkul", "बिल्कुल", "done", "ha ji", "जी")
NO = _set("nahi", "nahin", "nai", "नहीं", "नही", "no", "galat", "गलत", "wrong", "incorrect", "ಇಲ್ಲ", "illa",
          "ಇಲ್ಲಾ", "ತಪ್ಪು", "tappu", "mat", "मत", "dont", "don't")
YES_STRONG = [match_form(p) for p in ["sab sahi", "sab theek", "sab thik", "सब सही", "सब ठीक", "everything is correct",
                                      "all correct", "everything correct", "ಎಲ್ಲಾ ಸರಿ", "ಎಲ್ಲ ಸರಿ"]]
UNDO = [match_form(p) for p in ["undo", "pehle wala", "pahle wala", "पहले वाला", "पहले वाली", "pehle jaisa",
                                "पहले जैसा", "wapas karo", "वापस करो", "वापस", "revert", "ಹಿಂದಿನದು", "ಹಿಂದಿನಂತೆ",
                                "ರದ್ದು ಮಾಡಿ", "go back"]]
REPEAT = [match_form(p) for p in ["repeat", "phir se bolo", "phir se", "फिर से", "dobara bolo", "दोबारा बोलो",
                                  "फिर बोलो", "say again", "once more", "ಮತ್ತೆ ಹೇಳಿ", "ಇನ್ನೊಮ್ಮೆ"]]
SKIP = [match_form(p) for p in ["skip", "स्किप", "ಸ್ಕಿಪ್", "nahi pata", "pata nahi", "पता नहीं", "नहीं पता",
                                "baad mein", "बाद में", "chhodo", "छोड़ो", "छोडो", "leave it", "not known",
                                "ಗೊತ್ತಿಲ್ಲ", "ಬಿಡಿ", "next"]]
UNSURE = [match_form(p) for p in ["shayad", "शायद", "not sure", "maybe", "ho sakta", "हो सकता", "ಇರಬಹುದು"]]
ADVICE = [match_form(p) for p in ["kya dawai", "kaunsi dawai", "konsi dawai", "kya dava", "कौन सी दवा", "क्या दवा",
                                  "दवाई क्या", "kitni goli", "कितनी गोली", "kitna dose", "dose kitna", "what medicine",
                                  "which medicine", "what dose", "how much dose", "treatment kya", "ilaj kya",
                                  "इलाज क्या", "क्या इलाज", "ಯಾವ ಔಷಧಿ", "ಔಷಧಿ ಏನು", "ಎಷ್ಟು ಡೋಸ್", "what should i give",
                                  "kya du", "kya doon", "क्या दूं", "diagnosis kya", "kya bimari", "क्या बीमारी"]]

FIELD_ORDER = ["beneficiary_id", "beneficiary_name", "visit_type", "weight_kg", "vaccinations_given",
               "vaccinations_due", "ifa_tablets_given", "next_visit_date", "visit_date"]


@dataclass
class Intent:
    kind: str                       # ADVICE UNDO REPEAT PATCH BARE YES NO SKIP UNSURE UNKNOWN
    patch: dict = field(default_factory=dict)       # field -> FieldValue
    remove_given: list = field(default_factory=list)
    bare_value: float | None = None
    has_no: bool = False


def _words(mf: str) -> list[str]:
    return re.findall(rf"[{WORD_CHARS}]+", mf)


def _negated_vaccines(mf: str) -> list[str]:
    out = []
    neg = _set("nahi", "nahin", "नहीं", "not", "no", "ಇಲ್ಲ", "na")
    for canon, terms in VACCINE_TERMS.items():
        for s, e, _ in find_phrases(mf, terms):
            after = _words(mf[e:])[:4]
            if any(w in neg or w.endswith(("ಿಲ್ಲ",)) for w in after) or "remove" in _words(mf[:s])[-2:]:
                out.append(canon)
    return out


def classify(text: str, today: date, extractor: RuleExtractor, expect: str | None = None) -> Intent:
    mf = match_form(text)
    words = _words(mf)
    wset = set(words)
    has_no = bool(wset & NO)
    if not words:
        return Intent("UNKNOWN")
    if find_phrases(mf, ADVICE):
        return Intent("ADVICE")
    if find_phrases(mf, UNDO):
        return Intent("UNDO")
    if find_phrases(mf, REPEAT):
        return Intent("REPEAT")
    ex: Extraction = extractor.extract(text, today, expect=expect)
    patch = dict(ex.fields)
    removed = _negated_vaccines(mf)
    if patch or removed:
        return Intent("PATCH", patch=patch, remove_given=removed, has_no=has_no)
    if expect and find_phrases(mf, SKIP):
        return Intent("SKIP")
    tokens = tokenize(mf)
    for i, tok in enumerate(tokens):
        v, j = parse_number(tokens, i)
        if v is not None and (tok.text[0].isdigit() or j - i >= 1) and tok.text not in NO:
            # avoid treating "do" (give) etc. as a number unless it is the only content
            if not tok.text[0].isdigit() and len(words) > 3:
                continue
            return Intent("BARE", bare_value=v, has_no=has_no)
    if find_phrases(mf, YES_STRONG):
        return Intent("YES")
    yes = bool(wset & YES) or bool(find_phrases(mf, [match_form("theek hai"), match_form("sahi hai")]))
    if find_phrases(mf, UNSURE):
        return Intent("UNSURE", has_no=has_no)
    if has_no:
        # any negation wins over a yes-word: never save on an ambiguous answer
        return Intent("NO", has_no=True)
    if yes:
        return Intent("YES")
    if find_phrases(mf, SKIP):
        return Intent("SKIP")
    return Intent("UNKNOWN", has_no=has_no)


def bare_target(value: float, last_read_field: str | None, record: dict) -> str | None:
    """Which field a bare number ("no, 54") refers to. Only the last *single* field read
    back counts as unambiguous context, and the value must fit that field."""
    if last_read_field == "weight_kg" and 0.3 <= value <= 200:
        return "weight_kg"
    if last_read_field == "beneficiary_id" and float(value).is_integer() and value >= 100:
        return "beneficiary_id"
    return None
