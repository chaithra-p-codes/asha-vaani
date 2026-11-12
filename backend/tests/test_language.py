from datetime import date

import pytest

from app.services.dates import find_dates
from app.services.normalise import match_form, tokenize
from app.services.numbers import kn_words, parse_digit_string, parse_number, speak_decimal, speak_digits

TODAY = date(2026, 11, 11)  # Wednesday


def num(s):
    return parse_number(tokenize(match_form(s)), 0)[0]


@pytest.mark.parametrize("text,value", [
    ("52", 52), ("बावन", 52), ("fifty two", 52), ("fifty-two", 52), ("ಐವತ್ತೆರಡು", 52), ("aivattu eradu", 52),
    ("2.8", 2.8), ("do point aath", 2.8), ("दो दशमलव आठ", 2.8), ("two point eight", 2.8), ("ಎರಡು ಪಾಯಿಂಟ್ ಎಂಟು", 2.8),
    ("ढाई", 2.5), ("साढ़े तीन", 3.5), ("सवा दो", 2.25), ("पौने तीन", 2.75), ("two and a half", 2.5),
    ("ಎರಡೂವರೆ", 2.5), ("tees", 30), ("चौवन", 54), ("छप्पन", 56), ("नब्बे", 90), ("ninety nine", 99),
    ("2,800", 2800), ("२४", 24), ("೫೨", 52),
])
def test_spoken_numbers(text, value):
    assert num(text) == pytest.approx(value)


@pytest.mark.parametrize("text,digits", [
    ("one zero two four", "1024"), ("एक शून्य दो चार", "1024"), ("ten twenty four", "1024"),
    ("one thousand twenty four", "1024"), ("एक हज़ार चौबीस", "1024"), ("double two three four", "2234"),
    ("ಒಂದು ಸೊನ್ನೆ ಎರಡು ನಾಲ್ಕು", "1024"), ("10 24", "1024"), ("1024", "1024"), ("zero zero seven", "007"),
])
def test_digit_strings(text, digits):
    assert parse_digit_string(tokenize(match_form(text)), 0)[0] == digits


def test_kannada_number_words_follow_sandhi():
    assert kn_words(21) == "ಇಪ್ಪತ್ತೊಂದು"
    assert kn_words(23) == "ಇಪ್ಪತ್ಮೂರು"
    assert kn_words(52) == "ಐವತ್ತೆರಡು"
    assert all(kn_words(n) for n in range(0, 101))


def test_speaking_numbers_never_uses_digits():
    for lang in ("en", "hi", "kn"):
        assert not any(c.isdigit() for c in speak_decimal(2.8, lang) + speak_digits("1024", lang))
    assert speak_digits("1024", "en") == "one zero two four"
    assert speak_decimal(52.5, "en") == "fifty two point five"


def dates(text, future=True):
    return [(h.value.isoformat(), h.ambiguous) for h in find_dates(tokenize(match_form(text)), TODAY, future)]


@pytest.mark.parametrize("text,iso,amb", [
    ("20 November", "2026-11-20", False), ("November 20", "2026-11-20", False), ("बीस नवंबर", "2026-11-20", False),
    ("ನವೆಂಬರ್ 25", "2026-11-25", False), ("5 January", "2027-01-05", False), ("20/11", "2026-11-20", False),
    ("kal", "2026-11-12", False), ("कल", "2026-11-12", False), ("parso", "2026-11-13", False),
    ("ನಾಳೆ", "2026-11-12", False), ("ನಾಡಿದ್ದು", "2026-11-13", False), ("next monday", "2026-11-16", False),
    ("अगले सोमवार", "2026-11-16", False), ("ಮುಂದಿನ ಸೋಮವಾರ", "2026-11-16", False),
    ("15 din baad", "2026-11-26", False), ("ek hafte baad", "2026-11-18", True), ("in 7 days", "2026-11-18", False),
    ("20 तारीख", "2026-11-20", True), ("5 tarikh", "2026-12-05", True), ("2 mahine baad", "2027-01-11", True),
    ("20 November 2026", "2026-11-20", False),
])
def test_dates(text, iso, amb):
    found = dates(text)
    assert found and found[0] == (iso, amb), found


def test_kal_in_past_context_is_yesterday():
    assert dates("kal", future=False)[0][0] == "2026-11-10"


def test_match_form_handles_nukta_chandrabindu_zwj():
    assert match_form("वज़न") == match_form("वजन")
    assert match_form("पाँच") == match_form("पांच")
    assert match_form("ಎಎನ್‌ಸಿ") == "ಎಎನ್ಸಿ"


def test_tokenizer_keeps_indic_words_whole():
    assert [t.text for t in tokenize(match_form("वज़न बावन किलो, ಇಪ್ಪತ್ತೊಂದು ಕೆಜಿ"))] == \
        ["वजन", "बावन", "किलो", "ಇಪ್ಪತ್ತೊಂದು", "ಕೆಜಿ"]
