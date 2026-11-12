"""Structured field extraction from a visit transcript.

Two extractors produce *candidates*; neither may bypass deterministic validation:
  1. RuleExtractor (always on, ~1 ms): cue-anchored parsing of IDs, names, visit type,
     weight, vaccines (given / due), IFA, dates. Every value keeps the phrase it came from.
  2. LLM extractor (optional, Gemini): schema-constrained JSON. Each LLM value must quote
     an evidence phrase that literally occurs in the transcript, otherwise it is discarded
     ("grounding check"). LLM output never sets danger signs.
Merge policy: rule value wins for numbers/IDs/dates when both exist; disagreement marks the
field "confirm" so the worker hears it read back slowly; LLM-only grounded values are
accepted as "confirm".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .dates import find_dates
from .normalise import (BOOSTER, GLOSSARY, ORDINALS, VACCINES, WORD_CHARS, Token, clauses,
                        find_phrases, match_form, tokenize)
from .numbers import parse_digit_string, parse_number, parse_number_ending_at, word_value

FIELDS = ["beneficiary_id", "beneficiary_name", "visit_type", "visit_date", "weight_kg",
          "vaccinations_given", "vaccinations_due", "ifa_tablets_given", "next_visit_date"]


@dataclass
class FieldValue:
    value: object
    raw: str = ""                 # phrase heard (match form)
    confidence: str = "high"      # high | confirm | system
    source: str = "speech"        # speech | register | system | llm
    note: str = ""

    def public(self) -> dict:
        return {"value": self.value, "raw": self.raw, "confidence": self.confidence,
                "source": self.source, "note": self.note}


@dataclass
class Extraction:
    fields: dict = field(default_factory=dict)        # name -> FieldValue
    notes: list = field(default_factory=list)         # clarification hints (codes)

    def get(self, name):
        fv = self.fields.get(name)
        return fv.value if fv else None


def _mf_list(variants):
    return sorted({match_form(v) for v in variants}, key=len, reverse=True)


VISIT_TYPE_TERMS = {k: _mf_list(GLOSSARY[k]) for k in ("ANC", "PNC", "NEWBORN", "IMMUNISATION")}
VACCINE_TERMS = {k: _mf_list(v) for k, v in VACCINES.items()}
IFA_TERMS = _mf_list(GLOSSARY["IFA"])
ID_CUES = _mf_list(["beneficiary id", "beneficiary number", "beneficiary", "id number", "id", "i d", "आईडी",
                    "आई डी", "लाभार्थी", "labharthi", "number", "no", "नंबर", "संख्या", "registration",
                    "ಐಡಿ", "ಐ ಡಿ", "ಫಲಾನುಭವಿ", "ಸಂಖ್ಯೆ", "ನಂಬರ್", "rch id", "mcts"])
NAME_CUES = _mf_list(["name", "naam", "नाम", "ಹೆಸರು", "hesaru", "called", "named"])
WEIGHT_CUES = _mf_list(["weight", "wt", "vajan", "wajan", "vazan", "wazan", "वजन", "वज़न", "भार", "ತೂಕ", "tooka", "tuka"])
KG_UNITS = _mf_list(["kg", "kgs", "kilo", "kilos", "kilogram", "kilograms", "kilogramme", "किलो", "किलोग्राम",
                     "केजी", "के जी", "ಕೆಜಿ", "ಕೆ ಜಿ", "ಕಿಲೋ", "ಕಿಲೋಗ್ರಾಂ", "ಕಿಲೋಗ್ರಾಮ್", "ಕೇಜಿ"])
GRAM_UNITS = _mf_list(["gram", "grams", "gm", "gms", "ग्राम", "ಗ್ರಾಂ", "ಗ್ರಾಮ್"])
NEXT_VISIT_CUES = _mf_list(["next visit", "next date", "next checkup", "follow up", "followup", "agli visit",
                            "agla visit", "agli baar", "agli bar", "agli date", "agli tarikh", "अगली विजिट",
                            "अगली बार", "अगला विजिट", "अगली तारीख", "अगली जांच", "phir aana", "phir aaungi",
                            "फिर आना", "फिर आऊंगी", "dobara", "दोबारा", "ಮುಂದಿನ ಭೇಟಿ", "ಮುಂದಿನ ವಿಸಿಟ್",
                            "ಮುಂದಿನ ದಿನಾಂಕ", "mundina bheti", "revisit", "next", "agli", "अगली"])
VISIT_DATE_CUES = _mf_list(["visit date", "date of visit", "visited on", "visit kiya", "visit ki", "visit hui",
                            "विजिट की", "विजिट हुई", "ಭೇಟಿ ನೀಡಿದ"])
DUE_CUES = _mf_list(["due", "baaki", "baki", "बाकी", "lagna hai", "lagana hai", "लगना है", "लगाना है", "dena hai",
                     "देना है", "pending", "next", "agli", "agle", "अगली", "अगले", "lagega", "लगेगा", "lagwana",
                     "ಬಾಕಿ", "ಕೊಡಬೇಕು", "ಹಾಕಬೇಕು", "ಮುಂದಿನ", "remaining", "to be given", "schedule"])
GIVEN_CUES = _mf_list(["given", "gave", "recorded", "done", "completed", "administered", "received", "got",
                       "diya", "di", "de diya", "de di", "dilaya", "laga", "lagi", "lagaya", "lagayi", "lag gaya",
                       "lag gayi", "ho gaya", "ho gayi", "hua", "दिया", "दी", "दे दिया", "दे दी", "लगा", "लगी",
                       "लगाया", "लगाई", "लग गया", "लग गई", "हो गया", "हो गई", "हुआ", "ಕೊಟ್ಟಿದೆ", "ಕೊಡಲಾಗಿದೆ",
                       "ಹಾಕಲಾಗಿದೆ", "ಹಾಕಿದೆ", "ಆಗಿದೆ", "ಕೊಟ್ಟೆ", "kottide"])
NEG_WORDS = {match_form(w) for w in ["nahi", "nahin", "नहीं", "नही", "not", "no", "ಇಲ್ಲ", "illa", "na", "न"]}
_KN_NEG_SUFFIX = ("ಿಲ್ಲ", "ಿಲ್ಲಾ")
FILLER = {match_form(w) for w in ["is", "was", "hai", "है", "tha", "था", "ka", "ki", "ke", "का", "की", "के", "of",
                                   "about", "around", "approx", "approximately", "lagbhag", "लगभग", "ಸುಮಾರು",
                                   "ಇದೆ", "ide", "abhi", "अभी", "now", "the", "her", "uska", "uski", "उसका", "उसकी",
                                   "baby", "बच्चे", "बच्चा", "bachche", "ka", "ಮಗುವಿನ", "taken", "measured", "liya",
                                   "लिया", "hua", "kg", "आज", "aaj"]}


def _negated_tokens(words: list[str]) -> bool:
    return any(w in NEG_WORDS or w.endswith(_KN_NEG_SUFFIX) for w in words)


def _token_index_at(tokens: list[Token], char_pos: int) -> int:
    for t in tokens:
        if t.start >= char_pos:
            return t.index
    return len(tokens)


def _token_index_ending(tokens: list[Token], char_pos: int) -> int:
    """Index of first token starting at/after char_pos (used after a phrase ends)."""
    return _token_index_at(tokens, char_pos)


class RuleExtractor:
    def __init__(self, registry: list[dict] | None = None):
        self.registry = registry or []

    # ------------------------------------------------------------------ public
    def extract(self, transcript: str, today: date, *, expect: str | None = None) -> Extraction:
        """`expect` = field the agent just asked about; enables bare answers
        ("1024", "52 kilo", "ANC", "20 November") to be attributed to it."""
        text = match_form(transcript)
        tokens = tokenize(text)
        ex = Extraction()
        self._visit_type(text, ex)
        self._beneficiary(text, tokens, ex, expect)
        self._weight(text, tokens, ex, expect)
        self._vaccines(text, ex)
        self._ifa(text, ex)
        self._dates(text, tokens, today, ex, expect)
        return ex

    # ------------------------------------------------------------------ visit type
    def _visit_type(self, text: str, ex: Extraction) -> None:
        found = []
        for vt, terms in VISIT_TYPE_TERMS.items():
            hits = find_phrases(text, terms)
            if hits:
                found.append((hits[0][0], vt, hits[0][2]))
        if not found:
            return
        found.sort()
        specific = [f for f in found if f[1] != "IMMUNISATION"]
        chosen = specific[0] if specific else found[0]
        # "PNC visit, newborn bhi dekha" -> more than one specific type heard
        conf = "confirm" if len({f[1] for f in specific}) > 1 else "high"
        ex.fields["visit_type"] = FieldValue(chosen[1], chosen[2], conf, note=(
            "more than one visit type heard" if conf == "confirm" else ""))

    # ------------------------------------------------------------------ beneficiary
    def _beneficiary(self, text: str, tokens: list[Token], ex: Extraction, expect: str | None) -> None:
        digits = None
        raw = ""
        for s, e, cue in find_phrases(text, ID_CUES):
            j = _token_index_ending(tokens, e)
            # allow small filler between cue and digits ("ID hai 1024", "number is 1024")
            while j < len(tokens) and tokens[j].text in FILLER and j < _token_index_ending(tokens, e) + 2:
                j += 1
            d, k = parse_digit_string(tokens, j)
            if len(d) >= 3:
                digits, raw = d, text[s:tokens[k - 1].end] if k > j else text[s:e]
                # self-correction mid-sentence: "1059 nahi, 1090" / "1059 no 1090" -> later value wins
                while k < len(tokens) and (tokens[k].text in NEG_WORDS or tokens[k].text.endswith(_KN_NEG_SUFFIX)):
                    d2, k2 = parse_digit_string(tokens, k + 1)
                    if len(d2) >= 3:
                        digits, raw, k = d2, text[s:tokens[k2 - 1].end], k2
                        ex.notes.append("id_self_corrected")
                    else:
                        break
                break
        if digits is None and expect == "beneficiary_id":
            d, k = parse_digit_string(tokens, 0)
            if len(d) >= 3:
                digits, raw = d, " ".join(t.text for t in tokens[:k])
        if digits is None:
            # a standalone 4+ digit number that is not a date/weight: candidate only
            unit_first = {match_form(u).split()[0] for u in KG_UNITS + GRAM_UNITS}
            for t in tokens:
                nxt = tokens[t.index + 1].text if t.index + 1 < len(tokens) else ""
                if nxt in unit_first:
                    continue
                if t.text.isdigit() and len(t.text) >= 4 and not (1900 < int(t.text) < 2100):
                    digits, raw = t.text, t.text
                    ex.notes.append("id_without_cue")
                    break
        reg_by_id = {r["synthetic_external_id"]: r for r in self.registry}
        name_hits = self._names(text)
        if digits:
            conf = "high"
            note = ""
            if "id_without_cue" in ex.notes:
                conf, note = "confirm", "number heard without an ID cue"
            if self.registry and digits not in reg_by_id:
                conf, note = "confirm", "ID not found in the synthetic register"
            ex.fields["beneficiary_id"] = FieldValue(digits, raw, conf, note=note)
        if name_hits:
            uniq = {h["synthetic_external_id"]: h for h in name_hits}
            names = list(uniq.values())
            if digits and digits in uniq:
                ex.fields["beneficiary_name"] = FieldValue(uniq[digits]["name"], uniq[digits]["_raw"], "high")
            elif len(names) == 1:
                r = names[0]
                ex.fields["beneficiary_name"] = FieldValue(r["name"], r["_raw"], "high")
                if digits and digits != r["synthetic_external_id"]:
                    ex.fields["beneficiary_name"].confidence = "confirm"
                    ex.fields["beneficiary_name"].note = "name and ID belong to different register entries"
                    if "beneficiary_id" in ex.fields:
                        ex.fields["beneficiary_id"].confidence = "confirm"
                        ex.fields["beneficiary_id"].note = "name and ID belong to different register entries"
                    ex.notes.append("name_id_mismatch")
            else:
                ex.notes.append("ambiguous_name")
                ex.fields["beneficiary_name"] = FieldValue(
                    names[0]["name"].split()[0], names[0]["_raw"], "confirm",
                    note="more than one beneficiary has this name; say the ID")
        elif digits and digits in reg_by_id:
            ex.fields["beneficiary_name"] = FieldValue(reg_by_id[digits]["name"], "", "high", source="register",
                                                       note="looked up from the synthetic register by ID")
        else:
            # unknown name after an explicit name cue
            for s, e, cue in find_phrases(text, NAME_CUES):
                j = _token_index_ending(tokens, e)
                while j < len(tokens) and tokens[j].text in FILLER:
                    j += 1
                if j < len(tokens) and not tokens[j].text[0].isdigit() and word_value(tokens[j].text) is None:
                    name = tokens[j].text
                    if j + 1 < len(tokens) and tokens[j + 1].text in {"devi", "देवी", "kumari", "कुमारी", "bai", "बाई", "ಬಾಯಿ"}:
                        name += " " + tokens[j + 1].text
                    ex.fields["beneficiary_name"] = FieldValue(name.title(), name, "confirm",
                                                               note="name not found in the synthetic register")
                    break

    def _names(self, text: str) -> list[dict]:
        hits = []
        for r in self.registry:
            aliases = r.get("aliases") or [r["name"]]
            full = _mf_list(aliases)
            found = find_phrases(text, full)
            if found:
                hits.append({**r, "_raw": found[0][2], "_full": True})
        if hits:
            return hits
        # first-name only
        for r in self.registry:
            firsts = _mf_list([a.split()[0] for a in (r.get("aliases") or [r["name"]])])
            found = find_phrases(text, firsts)
            if found:
                hits.append({**r, "_raw": found[0][2], "_full": False})
        return hits

    # ------------------------------------------------------------------ weight
    def _weight(self, text: str, tokens: list[Token], ex: Extraction, expect: str | None) -> None:
        candidates = []
        unit_hits = [(s, e, u, 1.0) for s, e, u in find_phrases(text, KG_UNITS)]
        unit_hits += [(s, e, u, 0.001) for s, e, u in find_phrases(text, GRAM_UNITS)]
        for s, e, unit, factor in unit_hits:
            ui = _token_index_at(tokens, s)
            v, start = parse_number_ending_at(tokens, ui)
            if v is not None:
                candidates.append((v * factor, text[tokens[start].start:e], ui))
        if not candidates:
            for s, e, cue in find_phrases(text, WEIGHT_CUES):
                j = _token_index_ending(tokens, e)
                hops = 0
                while j < len(tokens) and tokens[j].text in FILLER and hops < 3:
                    j += 1
                    hops += 1
                v, k = parse_number(tokens, j)
                if v is not None:
                    candidates.append((v, text[s:tokens[k - 1].end], j))
                    break
        if not candidates and expect == "weight_kg":
            v, k = parse_number(tokens, 0)
            if v is not None:
                candidates.append((v, " ".join(t.text for t in tokens[:k]), 0))
        if candidates:
            v, raw, _ = candidates[0]
            conf = "high" if len({round(c[0], 3) for c in candidates}) == 1 else "confirm"
            ex.fields["weight_kg"] = FieldValue(round(float(v), 3), raw, conf,
                                                note="" if conf == "high" else "more than one weight heard")

    # ------------------------------------------------------------------ vaccines
    def _vaccines(self, text: str, ex: Extraction) -> None:
        given, due = [], []
        raws = {}
        uncertain = False
        spans = clauses(text)
        taken: list[tuple[int, int]] = []
        for canon, terms in VACCINE_TERMS.items():
            for s, e, term in find_phrases(text, terms):
                if any(a <= s < b for a, b in taken):
                    continue
                taken.append((s, e))
                cs, ce = next(((a, b) for a, b in spans if a <= s < b), (0, len(text)))
                clause = text[cs:ce]
                after = text[e:ce]
                label = canon + self._dose(after)
                cw = re.findall(rf"[{WORD_CHARS}]+", clause)
                is_due = bool(find_phrases(clause, DUE_CUES))
                is_given = bool(find_phrases(clause, GIVEN_CUES))
                negated = _negated_tokens(re.findall(rf"[{WORD_CHARS}]+", after)[:4])
                if is_due and not is_given:
                    target = due
                elif is_given and not negated:
                    target = given
                elif negated and is_due:
                    target = due
                elif negated:
                    continue  # "TT nahi laga" with no due cue: record nothing, never invent
                else:
                    target = given
                    uncertain = True
                if label not in target:
                    target.append(label)
                    raws[label] = text[s:min(ce, e + 20)].strip()
                _ = cw
        if given:
            ex.fields["vaccinations_given"] = FieldValue(given, "; ".join(raws[g] for g in given),
                                                         "confirm" if uncertain else "high",
                                                         note="please confirm given today vs due" if uncertain else "")
        if due:
            ex.fields["vaccinations_due"] = FieldValue(due, "; ".join(raws[d] for d in due), "high")

    @staticmethod
    def _dose(after: str) -> str:
        words = re.findall(rf"[{WORD_CHARS}]+", after)[:2]
        if not words:
            return ""
        w = words[0]
        if w in {match_form(b) for b in BOOSTER}:
            return " booster"
        if w.isdigit() and 0 <= int(w) <= 5:
            return f"-{int(w)}"
        wv = word_value(w)
        if wv is not None and 0 <= wv <= 4:
            return f"-{wv}"
        for n, forms in ORDINALS.items():
            if w in {match_form(f) for f in forms if f not in ("one", "two", "three")}:
                return f"-{n}"
        if w in {"zero", "शून्य", "ಸೊನ್ನೆ"}:
            return "-0"
        return ""

    # ------------------------------------------------------------------ IFA
    def _ifa(self, text: str, ex: Extraction) -> None:
        hits = find_phrases(text, IFA_TERMS)
        if not hits:
            return
        s, e, term = hits[0]
        spans = clauses(text)
        cs, ce = next(((a, b) for a, b in spans if a <= s < b), (0, len(text)))
        after_words = re.findall(rf"[{WORD_CHARS}]+", text[e:ce])[:6]
        clause = text[cs:ce]
        if _negated_tokens(after_words):
            ex.fields["ifa_tablets_given"] = FieldValue(False, text[s:ce].strip(), "high")
        elif find_phrases(clause, GIVEN_CUES):
            ex.fields["ifa_tablets_given"] = FieldValue(True, text[s:ce].strip(), "high")
        else:
            ex.fields["ifa_tablets_given"] = FieldValue(True, text[s:ce].strip(), "confirm",
                                                        note="IFA mentioned; please confirm it was given")

    # ------------------------------------------------------------------ dates
    def _dates(self, text: str, tokens: list[Token], today: date, ex: Extraction, expect: str | None) -> None:
        future_hits = find_dates(tokens, today, future=True)
        past_hits = find_dates(tokens, today, future=False)
        cue_next = find_phrases(text, NEXT_VISIT_CUES)
        cue_visit = find_phrases(text, VISIT_DATE_CUES)

        def near(hit, cues, before=8, after=4):
            hs = tokens[hit.start].start
            he = tokens[hit.end - 1].end
            for s, e, _ in cues:
                ci = _token_index_at(tokens, s)
                if 0 <= hit.start - ci <= before or 0 <= ci - (hit.end - 1) <= after:
                    return True
                if s >= he and s - he < 3:
                    return True
                _ = hs
            return False

        for hit in future_hits:
            if near(hit, cue_next) or expect == "next_visit_date":
                ex.fields["next_visit_date"] = FieldValue(hit.value.isoformat(), hit.raw,
                                                          "confirm" if hit.ambiguous else "high",
                                                          note="approximate date; please confirm" if hit.ambiguous else "")
                break
        for hit in past_hits:
            if near(hit, cue_visit):
                ex.fields["visit_date"] = FieldValue(hit.value.isoformat(), hit.raw,
                                                     "confirm" if hit.ambiguous else "high")
                break
        if "next_visit_date" not in ex.fields:
            leftovers = [h for h in future_hits if h.value > today
                         and not ("visit_date" in ex.fields and ex.fields["visit_date"].raw == h.raw)]
            if len(leftovers) == 1:
                h = leftovers[0]
                ex.fields["next_visit_date"] = FieldValue(h.value.isoformat(), h.raw, "confirm",
                                                          note="date heard without 'next visit'; please confirm")


# ---------------------------------------------------------------------------- merge
def merge(rule: Extraction, llm: dict | None, transcript: str) -> Extraction:
    """Merge grounded LLM candidates into the rule extraction (see module docstring)."""
    if not llm:
        return rule
    text_mf = match_form(transcript)
    out = Extraction(dict(rule.fields), list(rule.notes))
    for name in FIELDS:
        item = llm.get(name)
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        evidence = match_form(str(item.get("evidence") or ""))
        if value in (None, "", []) or not evidence or evidence not in text_mf:
            continue  # ungrounded -> discarded
        if name in out.fields:
            if _norm(out.fields[name].value) != _norm(value):
                out.fields[name].confidence = "confirm"
                out.fields[name].note = (out.fields[name].note + "; " if out.fields[name].note else "") + \
                    "rule and LLM readings differ"
            continue
        out.fields[name] = FieldValue(value, evidence, "confirm", source="llm",
                                      note="found by the language model; please confirm")
    return out


def _norm(v):
    if isinstance(v, list):
        return sorted(str(x).lower() for x in v)
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, str):
        return v.strip().lower()
    return v
