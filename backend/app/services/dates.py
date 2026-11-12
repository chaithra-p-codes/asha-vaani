"""Spoken date parsing against the session's local date (Asia/Kolkata by default).

Handles: "20 November", "November 20", "20/11", "20 तारीख", "बीस नवंबर", "ನವೆಂಬರ್ 20",
"kal / कल" (future context = tomorrow), "parso / परसों", "aaj", "ನಾಳೆ", "ನಾಡಿದ್ದು",
"N din baad / N दिन बाद / in N days / N ದಿನ", "N hafte / weeks / ವಾರ", "N mahine / months",
"next Monday / अगले सोमवार / ಮುಂದಿನ ಸೋಮವಾರ". Approximate expressions (weeks/months, a bare
"20 tarikh") are returned with ambiguous=True so the agent reads them back for confirmation.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from .normalise import Token, match_form
from .numbers import parse_number

_MONTHS_RAW = {
    1: ["january", "jan", "जनवरी", "ಜನವರಿ", "janvari"],
    2: ["february", "feb", "फरवरी", "फ़रवरी", "ಫೆಬ್ರವರಿ", "farvari"],
    3: ["march", "mar", "मार्च", "ಮಾರ್ಚ್", "ಮಾರ್ಚ"],
    4: ["april", "apr", "अप्रैल", "एप्रिल", "ಏಪ್ರಿಲ್"],
    5: ["may", "मई", "ಮೇ"],
    6: ["june", "jun", "जून", "ಜೂನ್"],
    7: ["july", "jul", "जुलाई", "ಜುಲೈ"],
    8: ["august", "aug", "अगस्त", "ಆಗಸ್ಟ್", "ಆಗಸ್ಟ"],
    9: ["september", "sep", "sept", "सितंबर", "सितम्बर", "ಸೆಪ್ಟೆಂಬರ್"],
    10: ["october", "oct", "अक्टूबर", "अक्तूबर", "ಅಕ್ಟೋಬರ್"],
    11: ["november", "nov", "नवंबर", "नवम्बर", "ನವೆಂಬರ್", "navambar"],
    12: ["december", "dec", "दिसंबर", "दिसम्बर", "ಡಿಸೆಂಬರ್", "disambar"],
}
MONTHS = {match_form(w): m for m, ws in _MONTHS_RAW.items() for w in ws}

_WEEKDAYS_RAW = {
    0: ["monday", "सोमवार", "somvar", "somwar", "ಸೋಮವಾರ", "somavara"],
    1: ["tuesday", "मंगलवार", "mangalvar", "mangalwar", "ಮಂಗಳವಾರ", "mangalavara"],
    2: ["wednesday", "बुधवार", "budhvar", "budhwar", "ಬುಧವಾರ", "budhavara"],
    3: ["thursday", "गुरुवार", "guruvar", "guruwar", "बृहस्पतिवार", "ಗುರುವಾರ", "guruvara"],
    4: ["friday", "शुक्रवार", "shukravar", "shukrawar", "ಶುಕ್ರವಾರ", "shukravara"],
    5: ["saturday", "शनिवार", "shanivar", "shaniwar", "ಶನಿವಾರ", "shanivara"],
    6: ["sunday", "रविवार", "ravivar", "इतवार", "itvaar", "ಭಾನುವಾರ", "bhanuvara"],
}
WEEKDAYS = {match_form(w): d for d, ws in _WEEKDAYS_RAW.items() for w in ws}

NEXT_WORDS = {match_form(w) for w in ["next", "agle", "agla", "agli", "अगले", "अगला", "अगली", "ಮುಂದಿನ",
                                       "mundina", "aane wale", "आने"]}
TARIKH = {match_form(w) for w in ["tarikh", "tareekh", "tarik", "तारीख", "तारीख़", "ತಾರೀಖು", "ತಾರೀಕು",
                                   "ನೇ", "date"]}
DAY_UNITS = {match_form(w): 1 for w in ["din", "दिन", "day", "days", "ದಿನ", "ದಿನಗಳ", "ದಿನಗಳು", "dina"]}
DAY_UNITS.update({match_form(w): 7 for w in ["hafte", "hafta", "हफ्ते", "हफ़्ते", "हफ्ता", "सप्ताह", "week",
                                              "weeks", "ವಾರ", "ವಾರದ", "vaara"]})
MONTH_UNITS = {match_form(w) for w in ["mahine", "mahina", "महीने", "महीना", "month", "months", "ತಿಂಗಳು",
                                        "ತಿಂಗಳ", "tingalu"]}
AFTER_WORDS = {match_form(w) for w in ["baad", "बाद", "mein", "में", "me", "after", "later", "ನಂತರ",
                                        "ಬಳಿಕ", "nantara", "ಬಿಟ್ಟು"]}
IN_WORDS = {match_form(w) for w in ["in", "after"]}
RELATIVE = {
    match_form("aaj"): 0, match_form("आज"): 0, match_form("today"): 0, match_form("ಇಂದು"): 0,
    match_form("ಈವತ್ತು"): 0, match_form("indu"): 0,
    match_form("tomorrow"): 1, match_form("ನಾಳೆ"): 1, match_form("naale"): 1, match_form("nale"): 1,
    match_form("parso"): 2, match_form("parson"): 2, match_form("परसों"): 2, match_form("ನಾಡಿದ್ದು"): 2,
    match_form("naadiddu"): 2,
}
KAL = {match_form("kal"), match_form("कल")}


@dataclass
class DateHit:
    value: date
    start: int          # token index
    end: int            # token index (exclusive)
    ambiguous: bool
    raw: str


def _next_occurrence(today: date, month: int, day: int, future: bool) -> date | None:
    for year in ([today.year, today.year + 1] if future else [today.year, today.year - 1]):
        try:
            d = date(year, month, day)
        except ValueError:
            continue
        if future and d >= today:
            return d
        if not future and d <= today:
            return d
    return None


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def find_dates(tokens: list[Token], today: date, future: bool = True) -> list[DateHit]:
    """Scan tokens for date expressions. `future` picks the reading for bare 'kal' and
    month/day without a year (next visit -> future; visit date -> past/today)."""
    hits: list[DateHit] = []
    n = len(tokens)
    i = 0
    raw = lambda a, b: " ".join(t.text for t in tokens[a:b])
    while i < n:
        t = tokens[i].text
        # ISO yyyy-mm-dd typed by diagnostics, or dd/mm[/yyyy] — tokenizer splits on / and -
        if t.isdigit() and i + 1 < n and tokens[i + 1].text.isdigit() and len(t) <= 2 and len(tokens[i + 1].text) <= 2:
            d_, m_ = int(t), int(tokens[i + 1].text)
            y_ = None
            end = i + 2
            if end < n and tokens[end].text.isdigit() and len(tokens[end].text) == 4:
                y_ = int(tokens[end].text)
                end += 1
            if 1 <= d_ <= 31 and 1 <= m_ <= 12:
                d = None
                if y_:
                    try:
                        d = date(y_, m_, d_)
                    except ValueError:
                        d = None
                else:
                    d = _next_occurrence(today, m_, d_, future)
                if d:
                    hits.append(DateHit(d, i, end, False, raw(i, end)))
                    i = end
                    continue
        # relative single words
        if t in RELATIVE:
            hits.append(DateHit(today + timedelta(days=RELATIVE[t]), i, i + 1, False, t))
            i += 1
            continue
        if t in KAL:
            hits.append(DateHit(today + timedelta(days=1 if future else -1), i, i + 1, False, t))
            i += 1
            continue
        if t == match_form("day") and i + 2 < n and tokens[i + 1].text == "after" and tokens[i + 2].text == "tomorrow":
            hits.append(DateHit(today + timedelta(days=2), i, i + 3, False, raw(i, i + 3)))
            i += 3
            continue
        # next <weekday> / next week / next month
        if t in NEXT_WORDS and i + 1 < n:
            nt = tokens[i + 1].text
            if nt in WEEKDAYS:
                delta = (WEEKDAYS[nt] - today.weekday()) % 7 or 7
                hits.append(DateHit(today + timedelta(days=delta), i, i + 2, False, raw(i, i + 2)))
                i += 2
                continue
            if nt in DAY_UNITS and DAY_UNITS[nt] == 7:
                hits.append(DateHit(today + timedelta(days=7), i, i + 2, True, raw(i, i + 2)))
                i += 2
                continue
            if nt in MONTH_UNITS:
                hits.append(DateHit(_add_months(today, 1), i, i + 2, True, raw(i, i + 2)))
                i += 2
                continue
        if t in WEEKDAYS:  # bare weekday -> upcoming one, needs confirmation
            delta = (WEEKDAYS[t] - today.weekday()) % 7 or 7
            hits.append(DateHit(today + timedelta(days=delta), i, i + 1, True, t))
            i += 1
            continue
        # month-name first: "November 20"
        if t in MONTHS and i + 1 < n:
            v, j = parse_number(tokens, i + 1)
            if v is not None and float(v).is_integer() and 1 <= v <= 31:
                d = _next_occurrence(today, MONTHS[t], int(v), future)
                if d:
                    hits.append(DateHit(d, i, j, False, raw(i, j)))
                    i = j
                    continue
        # "in N days" style (English)
        if t in IN_WORDS and i + 2 < n:
            v, j = parse_number(tokens, i + 1)
            if v is not None and j < n and (tokens[j].text in DAY_UNITS or tokens[j].text in MONTH_UNITS):
                unit = tokens[j].text
                if unit in MONTH_UNITS:
                    hits.append(DateHit(_add_months(today, int(v)), i, j + 1, True, raw(i, j + 1)))
                else:
                    hits.append(DateHit(today + timedelta(days=int(v) * DAY_UNITS[unit]), i, j + 1,
                                        DAY_UNITS[unit] == 7, raw(i, j + 1)))
                i = j + 1
                continue
        # number-first constructs
        v, j = parse_number(tokens, i)
        if v is not None and float(v).is_integer():
            iv = int(v)
            if j < n and tokens[j].text in MONTHS and 1 <= iv <= 31:
                end = j + 1
                year = None
                if end < n and tokens[end].text.isdigit() and len(tokens[end].text) == 4:
                    year = int(tokens[end].text)
                    end += 1
                d = None
                if year:
                    try:
                        d = date(year, MONTHS[tokens[j].text], iv)
                    except ValueError:
                        d = None
                else:
                    d = _next_occurrence(today, MONTHS[tokens[j].text], iv, future)
                if d:
                    hits.append(DateHit(d, i, end, False, raw(i, end)))
                    i = end
                    continue
            if j < n and tokens[j].text in TARIKH and 1 <= iv <= 31:
                end = j + 1
                if end < n and tokens[end].text in TARIKH:
                    end += 1
                d = None
                for months_ahead in range(0, 3):
                    cand_month = _add_months(today.replace(day=1), months_ahead)
                    try:
                        cand = cand_month.replace(day=iv)
                    except ValueError:
                        continue
                    if (future and cand >= today) or (not future and cand <= today):
                        d = cand
                        break
                if d:
                    hits.append(DateHit(d, i, end, True, raw(i, end)))
                    i = end
                    continue
            if j < n and (tokens[j].text in DAY_UNITS or tokens[j].text in MONTH_UNITS) and 1 <= iv <= 365:
                unit = tokens[j].text
                end = j + 1
                if end < n and tokens[end].text in AFTER_WORDS:
                    end += 1
                    if unit in MONTH_UNITS:
                        d = _add_months(today, iv)
                        hits.append(DateHit(d, i, end, True, raw(i, end)))
                    else:
                        hits.append(DateHit(today + timedelta(days=iv * DAY_UNITS[unit]), i, end,
                                            DAY_UNITS[unit] == 7, raw(i, end)))
                    i = end
                    continue
        i += 1
    return hits


def speak_date(d: date, lang: str) -> str:
    from .numbers import speak_int
    names = {
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
               "October", "November", "December"],
        "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
               "नवंबर", "दिसंबर"],
        "kn": ["ಜನವರಿ", "ಫೆಬ್ರವರಿ", "ಮಾರ್ಚ್", "ಏಪ್ರಿಲ್", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗಸ್ಟ್", "ಸೆಪ್ಟೆಂಬರ್",
               "ಅಕ್ಟೋಬರ್", "ನವೆಂಬರ್", "ಡಿಸೆಂಬರ್"],
    }
    month = names.get(lang, names["en"])[d.month - 1]
    if lang == "kn":
        return f"{month} {speak_int(d.day, lang)}"
    return f"{speak_int(d.day, lang)} {month}"
