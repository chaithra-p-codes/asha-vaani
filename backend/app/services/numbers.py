"""Spoken-number parsing and speaking for Hindi, Kannada and English (incl. romanised forms).

Prisma v3.0 may return numbers as digits ("52") or, in codemix format, as spoken words
("बावन", "fifty two", "ಐವತ್ತೆರಡು"). Both are handled. Numbers are only interpreted where
a field cue makes the reading unambiguous (e.g. before "kilo"), because words like
"do" (Hindi: two / give) are otherwise ambiguous.
"""
from __future__ import annotations

from .normalise import Token, match_form

# --------------------------------------------------------------------------- Hindi 0..100
_HI = {
    0: ["शून्य", "जीरो", "shunya", "shoonya", "zero"], 1: ["एक", "ek"], 2: ["दो", "do"],
    3: ["तीन", "teen", "tin"], 4: ["चार", "char", "chaar"], 5: ["पांच", "पाँच", "paanch", "panch"],
    6: ["छह", "छः", "छे", "छै", "chhah", "chhe", "chah", "che", "chhai"], 7: ["सात", "saat", "sat"],
    8: ["आठ", "aath", "ath"], 9: ["नौ", "nau", "nao"], 10: ["दस", "das"],
    11: ["ग्यारह", "gyarah", "gyaarah", "gyara"], 12: ["बारह", "barah", "baarah", "bara"],
    13: ["तेरह", "terah", "tera"], 14: ["चौदह", "chaudah", "chauda"], 15: ["पंद्रह", "पन्द्रह", "pandrah", "pandra"],
    16: ["सोलह", "solah", "sola"], 17: ["सत्रह", "satrah", "satra"], 18: ["अठारह", "atharah", "athara"],
    19: ["उन्नीस", "unnees", "unnis"], 20: ["बीस", "bees", "bis"],
    21: ["इक्कीस", "ikkees", "ikkis"], 22: ["बाईस", "baees", "bais", "baais"], 23: ["तेईस", "teis", "teyis"],
    24: ["चौबीस", "chaubees", "chaubis"], 25: ["पच्चीस", "pachchees", "pachis", "pacchis"],
    26: ["छब्बीस", "chhabbees", "chhabbis"], 27: ["सत्ताईस", "sattaees", "sattais"],
    28: ["अट्ठाईस", "अठाईस", "atthaees", "athais", "atthais"], 29: ["उनतीस", "untees", "untis"],
    30: ["तीस", "tees", "tis"], 31: ["इकतीस", "iktees", "iktis"], 32: ["बत्तीस", "battees", "battis"],
    33: ["तैंतीस", "taintees", "taintis"], 34: ["चौंतीस", "chauntees", "chauntis"],
    35: ["पैंतीस", "paintees", "paintis"], 36: ["छत्तीस", "chhattees", "chhattis"],
    37: ["सैंतीस", "saintees", "saintis"], 38: ["अड़तीस", "अडतीस", "adtees", "adtis", "artis"],
    39: ["उनतालीस", "untalees", "untalis"], 40: ["चालीस", "chalees", "chalis"],
    41: ["इकतालीस", "iktalees", "iktalis"], 42: ["बयालीस", "bayalees", "bayalis"],
    43: ["तैंतालीस", "taintalees", "taintalis"], 44: ["चवालीस", "चौवालीस", "chavalees", "chawalis"],
    45: ["पैंतालीस", "paintalees", "paintalis"], 46: ["छियालीस", "chhiyalees", "chhiyalis"],
    47: ["सैंतालीस", "saintalees", "saintalis"], 48: ["अड़तालीस", "अडतालीस", "adtalees", "artalis"],
    49: ["उनचास", "unchaas", "unchas"], 50: ["पचास", "pachaas", "pachas"],
    51: ["इक्यावन", "ikyavan", "ikyawan"], 52: ["बावन", "baavan", "bavan", "bawan"],
    53: ["तिरपन", "tirpan"], 54: ["चौवन", "चव्वन", "chauvan", "chauwan", "chavvan"],
    55: ["पचपन", "pachpan"], 56: ["छप्पन", "chhappan"], 57: ["सत्तावन", "sattavan", "sattawan"],
    58: ["अट्ठावन", "अठावन", "atthavan", "athawan"], 59: ["उनसठ", "unsath"], 60: ["साठ", "saath", "sath"],
    61: ["इकसठ", "iksath"], 62: ["बासठ", "baasath", "basath"], 63: ["तिरसठ", "tirsath"],
    64: ["चौंसठ", "chaunsath"], 65: ["पैंसठ", "painsath"], 66: ["छियासठ", "chhiyasath"],
    67: ["सड़सठ", "सडसठ", "sadsath"], 68: ["अड़सठ", "अडसठ", "adsath"], 69: ["उनहत्तर", "unhattar"],
    70: ["सत्तर", "sattar"], 71: ["इकहत्तर", "ikhattar"], 72: ["बहत्तर", "bahattar"],
    73: ["तिहत्तर", "tihattar"], 74: ["चौहत्तर", "chauhattar"], 75: ["पचहत्तर", "pachhattar"],
    76: ["छिहत्तर", "chhihattar"], 77: ["सतहत्तर", "sathattar"], 78: ["अठहत्तर", "athhattar"],
    79: ["उन्यासी", "unyasi"], 80: ["अस्सी", "assi"], 81: ["इक्यासी", "ikyasi"], 82: ["बयासी", "bayasi"],
    83: ["तिरासी", "tirasi"], 84: ["चौरासी", "chaurasi"], 85: ["पचासी", "pachasi"],
    86: ["छियासी", "chhiyasi"], 87: ["सत्तासी", "sattasi"], 88: ["अट्ठासी", "अठासी", "atthasi"],
    89: ["नवासी", "navasi"], 90: ["नब्बे", "nabbe"], 91: ["इक्यानवे", "ikyanve"], 92: ["बानवे", "baanve"],
    93: ["तिरानवे", "tiranve"], 94: ["चौरानवे", "chauranve"], 95: ["पचानवे", "pachanve"],
    96: ["छियानवे", "chhiyanve"], 97: ["सत्तानवे", "sattanve"], 98: ["अट्ठानवे", "atthanve"],
    99: ["निन्यानवे", "ninyanve"], 100: ["सौ", "sau", "ek sau"],
}
# Hindi spoken forms for TTS (first Devanagari spelling)
HI_SPOKEN = {n: forms[0] for n, forms in _HI.items()}
HI_SPOKEN[0] = "शून्य"

# --------------------------------------------------------------------------- English
_EN_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
             "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
             "nineteen"]
_EN_TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy",
            80: "eighty", 90: "ninety"}


def en_words(n: int) -> str:
    if n < 20:
        return _EN_UNITS[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _EN_TENS[t * 10] + ("" if u == 0 else " " + _EN_UNITS[u])
    if n < 1000:
        h, r = divmod(n, 100)
        return _EN_UNITS[h] + " hundred" + ("" if r == 0 else " " + en_words(r))
    th, r = divmod(n, 1000)
    return en_words(th) + " thousand" + ("" if r == 0 else " " + en_words(r))


# --------------------------------------------------------------------------- Kannada
_KN_UNITS = {0: "ಸೊನ್ನೆ", 1: "ಒಂದು", 2: "ಎರಡು", 3: "ಮೂರು", 4: "ನಾಲ್ಕು", 5: "ಐದು", 6: "ಆರು", 7: "ಏಳು",
             8: "ಎಂಟು", 9: "ಒಂಬತ್ತು", 10: "ಹತ್ತು", 11: "ಹನ್ನೊಂದು", 12: "ಹನ್ನೆರಡು", 13: "ಹದಿಮೂರು",
             14: "ಹದಿನಾಲ್ಕು", 15: "ಹದಿನೈದು", 16: "ಹದಿನಾರು", 17: "ಹದಿನೇಳು", 18: "ಹದಿನೆಂಟು",
             19: "ಹತ್ತೊಂಬತ್ತು"}
_KN_TENS = {20: "ಇಪ್ಪತ್ತು", 30: "ಮೂವತ್ತು", 40: "ನಲವತ್ತು", 50: "ಐವತ್ತು", 60: "ಅರವತ್ತು", 70: "ಎಪ್ಪತ್ತು",
            80: "ಎಂಬತ್ತು", 90: "ತೊಂಬತ್ತು"}
_KN_VOWEL_SIGN = {"ಒ": "ೊ", "ಎ": "ೆ", "ಐ": "ೈ", "ಆ": "ಾ", "ಏ": "ೇ"}
_KN_ROMAN_UNITS = {0: ["sonne"], 1: ["ondu"], 2: ["eradu", "yeradu"], 3: ["mooru", "muru"],
                   4: ["naalku", "nalku"], 5: ["aidu", "eidu"], 6: ["aaru", "aru"], 7: ["elu", "yelu", "eelu"],
                   8: ["entu", "yentu"], 9: ["ombattu", "ombhattu"], 10: ["hattu"]}
_KN_ROMAN_TENS = {20: ["ippattu"], 30: ["moovattu", "muvattu"], 40: ["nalavattu", "nalvattu"],
                  50: ["aivattu", "aivatthu"], 60: ["aravattu"], 70: ["eppattu"], 80: ["embattu"],
                  90: ["tombattu", "thombattu"]}


def kn_words(n: int) -> str:
    if n in _KN_UNITS:
        return _KN_UNITS[n]
    if n == 100:
        return "ನೂರು"
    if 20 <= n < 100:
        t, u = divmod(n, 10)
        tens = _KN_TENS[t * 10]
        if u == 0:
            return tens
        unit = _KN_UNITS[u]
        stem = tens[:-1]  # drop final vowel sign U (ು) -> ends in consonant with inherent a
        if unit[0] in _KN_VOWEL_SIGN:
            return stem + _KN_VOWEL_SIGN[unit[0]] + unit[1:]
        return stem[:-1] + unit  # ಇಪ್ಪತ್ತ -> ಇಪ್ಪತ್ + ಮೂರು = ಇಪ್ಪತ್ಮೂರು
    if 100 < n < 1000:
        h, r = divmod(n, 100)
        head = "ನೂರ" if h == 1 else kn_words(h) + " ನೂರ"
        return head + " " + kn_words(r) if r else (kn_words(h) + " ನೂರು" if h > 1 else "ನೂರು")
    th, r = divmod(n, 1000)
    head = "ಸಾವಿರ" if th == 1 else kn_words(th) + " ಸಾವಿರ"
    return head + (" " + kn_words(r) if r else "")


# --------------------------------------------------------------------------- lexicon
WORD_VALUE: dict[str, int] = {}


def _add(word: str, value: int):
    WORD_VALUE.setdefault(match_form(word), value)


for _n, _forms in _HI.items():
    for _f in _forms:
        if " " not in _f:
            _add(_f, _n)
for _i, _w in enumerate(_EN_UNITS):
    _add(_w, _i)
for _n, _w in _EN_TENS.items():
    _add(_w, _n)
for _n in range(0, 101):
    _add(kn_words(_n), _n)
    # common alternative spelling keeps the tens' inherent vowel: ಐವತ್ತನಾಲ್ಕು / ಇಪ್ಪತ್ತಮೂರು
    if 20 < _n < 100 and _n % 10 in (3, 4):
        _add(_KN_TENS[_n - _n % 10][:-1] + _KN_UNITS[_n % 10], _n)
for _n, _forms in _KN_ROMAN_UNITS.items():
    for _f in _forms:
        _add(_f, _n)
for _n, _forms in _KN_ROMAN_TENS.items():
    for _f in _forms:
        _add(_f, _n)
_add("hundred", 100)
_add("नूरु", 100)

MULTIPLIERS = {match_form(w): v for w, v in {
    "hundred": 100, "sau": 100, "सौ": 100, "ನೂರು": 100, "ನೂರ": 100,
    "thousand": 1000, "hazaar": 1000, "hazar": 1000, "हज़ार": 1000, "हजार": 1000,
    "ಸಾವಿರ": 1000, "ಸಾವಿರದ": 1000, "saavira": 1000, "savira": 1000,
}.items()}

POINT_WORDS = {match_form(w) for w in ["point", "dot", "पॉइंट", "प्वाइंट", "पोइंट", "दशमलव", "dashamlav",
                                        "ಪಾಯಿಂಟ್", "ದಶಮಾಂಶ"]}
DOUBLE_WORDS = {match_form(w): 2 for w in ["double", "डबल", "ಡಬಲ್"]}
DOUBLE_WORDS.update({match_form(w): 3 for w in ["triple", "ट्रिपल", "ಟ್ರಿಪಲ್"]})

FRACTION_WORDS = {match_form(w): v for w, v in {
    "आधा": 0.5, "आधी": 0.5, "aadha": 0.5, "adha": 0.5, "half": 0.5, "ಅರ್ಧ": 0.5, "ardha": 0.5,
    "डेढ़": 1.5, "डेढ": 1.5, "dedh": 1.5, "derh": 1.5,
    "ढाई": 2.5, "dhai": 2.5, "dhaai": 2.5,
}.items()}
# prefix modifiers: साढ़े X = X + 0.5, सवा X = X + 0.25, पौने X = X - 0.25
PREFIX_MOD = {match_form(w): v for w, v in {
    "साढ़े": 0.5, "साढे": 0.5, "sadhe": 0.5, "saadhe": 0.5, "sade": 0.5,
    "सवा": 0.25, "sava": 0.25, "sawa": 0.25,
    "पौने": -0.25, "paune": -0.25, "pone": -0.25,
}.items()}
# Kannada "X-ವರೆ" = X + 0.5 (ಎರಡೂವರೆ = 2.5), "ಮುಕ್ಕಾಲು" = 0.75, "ಕಾಲು" = 0.25
for _n in range(1, 11):
    _base = _KN_UNITS[_n]
    _stem = _base[:-1] if _base.endswith("ು") else _base
    FRACTION_WORDS[match_form(_stem + "ೂವರೆ")] = _n + 0.5
    for _r in _KN_ROMAN_UNITS.get(_n, []):
        FRACTION_WORDS[match_form(_r[:-1] + "uvare")] = _n + 0.5
SUFFIX_FRACTION = {match_form("ಮುಕ್ಕಾಲು"): 0.75, match_form("mukkalu"): 0.75,
                   match_form("ಕಾಲು"): 0.25, match_form("kaalu"): 0.25}
AND_HALF = [["and", "a", "half"], ["aur", "aadha"], ["और", "आधा"], ["and", "half"]]


def word_value(tok: str) -> int | None:
    t = tok.rstrip(".")
    if t.isdigit():
        return int(t)
    return WORD_VALUE.get(t)


def _digits_value(tok: str) -> float | None:
    t = tok
    for suf in ("st", "nd", "rd", "th"):
        if t.endswith(suf) and t[:-2].isdigit():
            t = t[:-2]
    t = t.replace(",", "") if t.count(",") and "." not in t and all(len(p) == 3 for p in t.split(",")[1:]) else t
    t = t.replace(",", ".") if "," in t else t
    try:
        return float(t)
    except ValueError:
        return None


def parse_number(tokens: list[Token], i: int) -> tuple[float | None, int]:
    """Parse a number phrase starting at tokens[i]. Returns (value, next_index)."""
    n = len(tokens)
    if i >= n:
        return None, i
    t = tokens[i].text
    # prefix modifiers (साढ़े तीन)
    if t in PREFIX_MOD and i + 1 < n:
        v, j = parse_number(tokens, i + 1)
        if v is not None:
            return v + PREFIX_MOD[t], j
        return None, i
    if t in FRACTION_WORDS:
        return FRACTION_WORDS[t], i + 1
    base: float | None = None
    j = i
    if t[0].isdigit():
        base = _digits_value(t)
        j = i + 1
    else:
        wv = word_value(t)
        if wv is None:
            return None, i
        base = float(wv)
        j = i + 1
        # tens + unit composition ("fifty two", "aivattu eradu")
        if base >= 20 and base % 10 == 0 and base < 100 and j < n:
            u = word_value(tokens[j].text)
            if u is not None and 1 <= u <= 9 and not tokens[j].text.isdigit():
                base += u
                j += 1
        # multipliers ("one hundred", "ek hazaar", "ಒಂದು ಸಾವಿರ")
        while j < n and tokens[j].text in MULTIPLIERS:
            base *= MULTIPLIERS[tokens[j].text]
            j += 1
            if j < n:
                rest, k = parse_number(tokens, j)
                if rest is not None and rest < base:
                    base += rest
                    j = k
    if base is None:
        return None, i
    # decimals: "2 point 8", "do point aath", "fifty two point five"
    if j + 1 < n and tokens[j].text in POINT_WORDS:
        k = j + 1
        digits = ""
        while k < n:
            dv = word_value(tokens[k].text)
            if dv is None or dv > 99:
                break
            if tokens[k].text.isdigit():
                digits += tokens[k].text
            else:
                digits += str(dv)
            k += 1
            if len(digits) >= 3:
                break
        if digits:
            return float(f"{int(base)}.{digits}"), k
    # "X and a half" / "X aur aadha"
    for seq in AND_HALF:
        seq_mf = [match_form(s) for s in seq]
        if [tok.text for tok in tokens[j:j + len(seq_mf)]] == seq_mf:
            return base + 0.5, j + len(seq_mf)
    if j < n and tokens[j].text in SUFFIX_FRACTION:
        return base + SUFFIX_FRACTION[tokens[j].text], j + 1
    return base, j


def parse_number_ending_at(tokens: list[Token], end: int, max_back: int = 5) -> tuple[float | None, int]:
    """Find a number phrase that ends exactly at token index `end` (exclusive)."""
    for start in range(max(0, end - max_back), end):
        v, j = parse_number(tokens, start)
        if v is not None and j == end:
            return v, start
    return None, end


def parse_digit_string(tokens: list[Token], i: int, max_tokens: int = 12) -> tuple[str, int]:
    """Read an identifier: '1024', '10 24', 'one zero two four', 'एक शून्य दो चार',
    'ten twenty four', 'double two', 'one thousand twenty four'. Returns (digits, next_idx)."""
    n = len(tokens)
    j = i
    digits = ""
    words: list[Token] = []
    while j < n and j - i < max_tokens:
        t = tokens[j].text
        if t.isdigit():
            digits += t
            j += 1
            continue
        if t in DOUBLE_WORDS and j + 1 < n:
            v = word_value(tokens[j + 1].text)
            if v is not None and v <= 9:
                digits += str(v) * DOUBLE_WORDS[t]
                j += 2
                continue
        if t in MULTIPLIERS:
            words.append(tokens[j])
            j += 1
            continue
        v = word_value(t)
        if v is None or v > 99:
            break
        words.append(tokens[j])
        if 20 <= v < 100 and v % 10 == 0 and j + 1 < n and not tokens[j + 1].text.isdigit():
            u = word_value(tokens[j + 1].text)
            if u is not None and 1 <= u <= 9:
                v += u
                words.append(tokens[j + 1])
                j += 1
        digits += str(v)
        j += 1
    if any(w.text in MULTIPLIERS for w in words):
        val, k = parse_number(tokens, i)
        if val is not None and float(val).is_integer():
            return str(int(val)), k
    return digits, j


# --------------------------------------------------------------------------- speaking
def speak_int(n: int, lang: str) -> str:
    if lang == "hi":
        if 0 <= n <= 100:
            return HI_SPOKEN[n]
        if n < 1000:
            h, r = divmod(n, 100)
            return (HI_SPOKEN[h] + " सौ" + (" " + HI_SPOKEN[r] if r else ""))
        th, r = divmod(n, 1000)
        return speak_int(th, lang) + " हज़ार" + (" " + speak_int(r, lang) if r else "")
    if lang == "kn":
        return kn_words(n)
    return en_words(n)


def speak_digits(digits: str, lang: str) -> str:
    return " ".join(speak_int(int(d), lang) for d in digits if d.isdigit())


def speak_decimal(value: float, lang: str) -> str:
    """52 -> 'fifty two'; 2.8 -> 'two point eight' (fraction read digit by digit)."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    if "." not in text:
        return speak_int(int(text), lang)
    whole, frac = text.split(".")
    point = {"hi": "दशमलव", "kn": "ಪಾಯಿಂಟ್", "en": "point"}.get(lang, "point")
    return f"{speak_int(int(whole), lang)} {point} {speak_digits(frac, lang)}"
