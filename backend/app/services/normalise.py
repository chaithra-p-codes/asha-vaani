"""Conservative transcript normalisation and tokenisation for Hindi / Kannada / English
code-mixed text.

Design rules (build plan 7.3): never rewrite a transcript in a way that changes clinical
meaning. The original transcript is always kept; matching happens on a separate
"match form" that only removes orthographic noise:
  * Unicode NFC, then strip Devanagari nukta (वज़न == वजन), chandrabindu -> anusvara,
    zero-width joiners (ಎಎನ್‌ಸಿ == ಎಎನ್ಸಿ)
  * Devanagari / Kannada digits -> ASCII digits
  * Latin lower-casing

NOTE: Python's `\\w` does not match Indic vowel signs (they are combining marks), so a
custom word pattern is used everywhere.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Letters, digits and combining marks of Latin, Devanagari (minus danda) and Kannada.
WORD_CHARS = "0-9A-Za-zÀ-ɏऀ-ॣ०-ॿಀ-೿"
WORD_RE = re.compile(rf"\d+(?:[.,]\d+)*(?:st|nd|rd|th)?|[{WORD_CHARS}]+")
CLAUSE_SPLIT_RE = re.compile(r"[,.;:!?।॥\n]+")

_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate("೦೧೨೩೪೫೬೭೮೯")})


def match_form(text: str) -> str:
    """Normalise for matching only (never shown to the user as 'what was heard')."""
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("़", "")          # nukta
    t = t.replace("ँ", "ं")     # chandrabindu -> anusvara
    t = t.replace("‌", "").replace("‍", "")
    t = t.translate(_DIGIT_MAP)
    t = t.lower()
    t = t.replace("’", "'").replace("‘", "'")
    t = re.sub(r"\s+", " ", t).strip()
    return t


@dataclass
class Token:
    text: str      # match-form text
    start: int     # char offsets in the match-form string
    end: int
    index: int


def tokenize(text_mf: str) -> list[Token]:
    """Tokenise a match-form string. Hyphenated English numbers become separate tokens."""
    out: list[Token] = []
    for m in WORD_RE.finditer(text_mf):
        out.append(Token(m.group(0), m.start(), m.end(), len(out)))
    return out


def clauses(text_mf: str) -> list[tuple[int, int]]:
    """Character spans of clauses (split on punctuation and contrastive conjunctions)."""
    spans = []
    pos = 0
    for m in CLAUSE_SPLIT_RE.finditer(text_mf):
        if m.start() > pos:
            spans.append((pos, m.start()))
        pos = m.end()
    if pos < len(text_mf):
        spans.append((pos, len(text_mf)))
    # further split on contrastive conjunctions (but NOT on aur/and: coordination)
    out = []
    contrast = re.compile(r"\b(?:lekin|magar|parantu|but|however|aadare|adare)\b|लेकिन|मगर|परंतु|किंतु|ಆದರೆ")
    for s, e in spans:
        seg = text_mf[s:e]
        last = 0
        for m in contrast.finditer(seg):
            if m.start() > last:
                out.append((s + last, s + m.start()))
            last = m.end()
        if last < len(seg):
            out.append((s + last, e))
    return [(s, e) for s, e in out if text_mf[s:e].strip()]


def phrase_variants(*phrases: str) -> list[str]:
    return [match_form(p) for p in phrases]


def find_phrases(text_mf: str, phrases: list[str]) -> list[tuple[int, int, str]]:
    """Find whole-word occurrences of any phrase (match-form) in text. Returns spans."""
    hits = []
    for p in phrases:
        if not p:
            continue
        pat = re.compile(rf"(?<![{WORD_CHARS}]){re.escape(p)}(?![{WORD_CHARS}])")
        for m in pat.finditer(text_mf):
            hits.append((m.start(), m.end(), p))
    hits.sort()
    return hits


# ---------------------------------------------------------------------------------
# Controlled medical / programme glossary.
# Used for (a) Prisma `keyterms` boosting and (b) recognising terms in either script.
# ---------------------------------------------------------------------------------
GLOSSARY: dict[str, list[str]] = {
    "ANC": ["anc", "a n c", "anc checkup", "एएनसी", "ए एन सी", "ಎಎನ್ಸಿ", "ಎ ಎನ್ ಸಿ", "antenatal",
            "ante natal", "prenatal", "प्रसवपूर्व", "प्रसव पूर्व", "गर्भावस्था जांच", "ಗರ್ಭಿಣಿ ತಪಾಸಣೆ"],
    "PNC": ["pnc", "p n c", "पीएनसी", "पी एन सी", "ಪಿಎನ್ಸಿ", "ಪಿ ಎನ್ ಸಿ", "postnatal", "post natal",
            "postpartum", "प्रसव के बाद", "डिलीवरी के बाद", "delivery ke baad", "ಹೆರಿಗೆ ನಂತರ", "ಹೆರಿಗೆಯ ನಂತರ"],
    "NEWBORN": ["newborn", "new born", "neonate", "नवजात", "navjaat", "navjat", "नवजात शिशु", "ನವಜಾತ",
                "ನವಜಾತ ಶಿಶು", "hbnc", "एचबीएनसी", "ಎಚ್ಬಿಎನ್ಸಿ", "newborn visit", "baby visit"],
    "IMMUNISATION": ["immunisation", "immunization", "vaccination", "टीकाकरण", "टीकाकरन", "teekakaran",
                     "tikakaran", "ಲಸಿಕಾಕರಣ", "ಲಸಿಕೆ ಭೇಟಿ", "immunisation visit", "vaccination visit"],
    "PHC": ["phc", "पीएचसी", "पी एच सी", "ಪಿಎಚ್ಸಿ", "primary health centre", "primary health center"],
    "IFA": ["ifa", "i f a", "आईएफए", "आई एफ ए", "ಐಎಫ್ಎ", "ಐ ಎಫ್ ಎ", "ifa goli", "iron folic acid",
            "iron goli", "आयरन", "आयरन की गोली", "iron tablet", "iron tablets", "folic", "फोलिक",
            "ಕಬ್ಬಿಣ", "ಐರನ್", "ಐರನ್ ಮಾತ್ರೆ", "ಕಬ್ಬಿಣದ ಮಾತ್ರೆ", "khoon ki goli", "खून की गोली"],
    "MCP card": ["mcp card", "mcp", "एमसीपी कार्ड", "एमसीपी", "ಎಂಸಿಪಿ ಕಾರ್ಡ್", "ಎಂಸಿಪಿ", "mamta card", "ममता कार्ड"],
    "Anganwadi": ["anganwadi", "आंगनवाड़ी", "आंगनवाडी", "ಅಂಗನವಾಡಿ"],
}

# Vaccines / supplements on the MCP card immunisation pages. Canonical -> variants.
VACCINES: dict[str, list[str]] = {
    "TT/Td": ["tt", "t t", "td", "टीटी", "टी टी", "टीडी", "ಟಿಟಿ", "ಟಿ ಟಿ", "ಟಿಡಿ", "tetanus", "टिटनेस",
              "tt injection", "tt ka injection", "टीटी इंजेक्शन", "टीटी का इंजेक्शन", "ಟಿಟಿ ಇಂಜೆಕ್ಷನ್", "tt tika", "टीटी टीका"],
    "BCG": ["bcg", "b c g", "बीसीजी", "बी सी जी", "ಬಿಸಿಜಿ", "ಬಿ ಸಿ ಜಿ"],
    "OPV": ["opv", "o p v", "ओपीवी", "ओ पी वी", "ಒಪಿವಿ", "polio", "पोलियो", "ಪೋಲಿಯೊ", "ಪೋಲಿಯೋ", "polio drops", "पोलियो ड्रॉप"],
    "Hepatitis B": ["hepatitis b", "hep b", "hepb", "हेपेटाइटिस बी", "हेपेटाइटिस", "ಹೆಪಟೈಟಿಸ್ ಬಿ", "ಹೆಪಟೈಟಿಸ್"],
    "Pentavalent": ["penta", "pentavalent", "पेंटा", "पेंटावेलेंट", "ಪೆಂಟಾ", "ಪೆಂಟಾವೆಲೆಂಟ್"],
    "Rotavirus": ["rota", "rotavirus", "रोटा", "रोटावायरस", "ರೋಟಾ", "ರೋಟಾವೈರಸ್"],
    "IPV": ["ipv", "fipv", "आईपीवी", "ಐಪಿವಿ"],
    "PCV": ["pcv", "pneumococcal", "पीसीवी", "न्यूमोकोकल", "ಪಿಸಿವಿ"],
    "MR": ["mr", "m r", "measles", "measles rubella", "एमआर", "एम आर", "खसरा", "khasra", "ಎಂಆರ್", "ದಡಾರ"],
    "JE": ["je", "japanese encephalitis", "जेई", "ಜೆಇ"],
    "DPT booster": ["dpt", "dpt booster", "डीपीटी", "ಡಿಪಿಟಿ"],
    "Vitamin A": ["vitamin a", "vit a", "विटामिन ए", "ವಿಟಮಿನ್ ಎ"],
}

ORDINALS = {
    1: ["first", "1st", "pehla", "pehli", "pahla", "pahli", "पहला", "पहली", "ಮೊದಲ", "ಮೊದಲನೇ", "modala", "one"],
    2: ["second", "2nd", "doosra", "dusra", "doosri", "dusri", "दूसरा", "दूसरी", "ಎರಡನೇ", "eradane", "two"],
    3: ["third", "3rd", "teesra", "tisra", "teesri", "तीसरा", "तीसरी", "ಮೂರನೇ", "moorane", "three"],
}
BOOSTER = ["booster", "बूस्टर", "ಬೂಸ್ಟರ್"]


def keyterms_for(language: str) -> list[str]:
    """Up to 200 key terms for Prisma v3.0 boosting (English + the session language)."""
    terms: list[str] = []
    english = ["ANC", "PNC", "PHC", "IFA", "IFA goli", "TT injection", "Td", "BCG", "OPV", "Penta",
               "Pentavalent", "Rotavirus", "IPV", "PCV", "MR", "Hepatitis B", "Vitamin A", "MCP card",
               "Anganwadi", "ASHA", "newborn", "immunisation", "checkup", "beneficiary", "weight",
               "kilo", "next visit", "referral", "bleeding", "fever", "convulsions", "jaundice"]
    terms.extend(english)
    script = {"hi": "ऀ", "kn": "ಀ"}.get(language)
    if script:
        lo = ord(script)
        for variants in list(GLOSSARY.values()) + list(VACCINES.values()):
            for v in variants:
                if any(lo <= ord(ch) < lo + 0x80 for ch in v) and v not in terms:
                    terms.append(v)
    return terms[:200]
