"""Safety suite for the deterministic danger-sign engine (MCP Card 2018 list)."""
import pytest

from app.services.danger_rules import SIGNS, catalogue, evaluate


def status(text, vt):
    return {f.sign_id: f.status for f in evaluate(text, vt)}


POSITIVE = [
    ("ANC", "bleeding ho rahi hai", "PREG_BLEEDING"),
    ("ANC", "khoon aa raha hai", "PREG_BLEEDING"),
    ("ANC", "गर्भवती को खून आ रहा है", "PREG_BLEEDING"),
    ("ANC", "bleeding ruk nahi rahi", "PREG_BLEEDING"),
    ("ANC", "ರಕ್ತಸ್ರಾವ ಆಗುತ್ತಿದೆ", "PREG_BLEEDING"),
    ("ANC", "she has vaginal bleeding since morning", "PREG_BLEEDING"),
    ("PNC", "बहुत ज़्यादा खून जा रहा है", "PNC_EXCESSIVE_BLEEDING"),
    ("PNC", "heavy bleeding after delivery", "PNC_EXCESSIVE_BLEEDING"),
    ("ANC", "tez bukhar hai", "MATERNAL_HIGH_FEVER"),
    ("PNC", "high fever since two days", "MATERNAL_HIGH_FEVER"),
    ("ANC", "ತೀವ್ರ ಜ್ವರ ಇದೆ", "MATERNAL_HIGH_FEVER"),
    ("ANC", "aankhon ke aage andhera aur sar dard", "PREG_HEADACHE_BLURRED_VISION"),
    ("ANC", "blurred vision hai", "PREG_HEADACHE_BLURRED_VISION"),
    ("ANC", "use jhatke aa rahe hain", "CONVULSIONS"),
    ("ANC", "fits aaye", "CONVULSIONS"),
    ("NEWBORN", "baby ko daure pad rahe hain", "CONVULSIONS"),
    ("ANC", "poore sharir mein sujan hai", "PREG_SWELLING_ALL_OVER"),
    ("ANC", "paani ki thaili phat gayi", "PREG_WATER_BREAK"),
    ("ANC", "bachcha kam hil raha hai", "PREG_REDUCED_FETAL_MOVEMENT"),
    ("ANC", "severe anaemia hai", "PREG_SEVERE_ANAEMIA"),
    ("ANC", "12 ghante se dard ho raha hai", "PREG_PROLONGED_LABOUR"),
    ("NEWBORN", "baby ko tez bukhar hai", "NB_FEVER_OR_COLD"),
    ("NEWBORN", "बच्चे को बुखार है", "NB_FEVER_OR_COLD"),
    ("NEWBORN", "baby ka body thanda pad gaya", "NB_FEVER_OR_COLD"),
    ("NEWBORN", "ಮಗುವಿಗೆ ಜ್ವರ ಇದೆ", "NB_FEVER_OR_COLD"),
    ("NEWBORN", "baby doodh nahi pee raha", "NB_POOR_FEEDING"),
    ("NEWBORN", "ಮಗು ಹಾಲು ಕುಡಿಯುತ್ತಿಲ್ಲ", "NB_POOR_FEEDING"),
    ("NEWBORN", "baby is sucking weakly", "NB_POOR_FEEDING"),
    ("NEWBORN", "bachcha ro nahi raha", "NB_UNABLE_TO_CRY"),
    ("NEWBORN", "saans lene mein dikkat hai", "NB_DIFFICULT_BREATHING"),
    ("NEWBORN", "fast breathing and chest indrawing", "NB_DIFFICULT_BREATHING"),
    ("NEWBORN", "hatheli peeli hai", "NB_YELLOW_SKIN"),
    ("NEWBORN", "baby ko jaundice lag raha", "NB_YELLOW_SKIN"),
    ("NEWBORN", "potty mein khoon aa raha", "NB_BLOOD_IN_STOOL"),
    ("NEWBORN", "baby bahut sust hai", "NB_LETHARGIC_UNCONSCIOUS"),
    ("IMMUNISATION", "bachche ko tez bukhar hai", "CHILD_HIGH_FEVER"),
    ("IMMUNISATION", "dast band nahi ho rahe", "CHILD_DIARRHOEA_NOT_STOPPING"),
    (None, "bleeding ho rahi hai", "PREG_BLEEDING"),
]


@pytest.mark.parametrize("vt,text,sign", POSITIVE)
def test_positive_listed_signs(vt, text, sign):
    assert status(text, vt).get(sign) == "POSITIVE", status(text, vt)


NEGATED = [
    ("ANC", "bleeding nahi hai", "PREG_BLEEDING"),
    ("ANC", "no bleeding", "PREG_BLEEDING"),
    ("ANC", "ರಕ್ತಸ್ರಾವ ಇಲ್ಲ", "PREG_BLEEDING"),
    ("ANC", "खून नहीं आ रहा", "PREG_BLEEDING"),
    ("NEWBORN", "bachche ko bukhar nahi hai", "NB_FEVER_OR_COLD"),
    ("NEWBORN", "ಜ್ವರ ಇಲ್ಲ", "NB_FEVER_OR_COLD"),
    ("ANC", "no fits, no bleeding", "CONVULSIONS"),
]


@pytest.mark.parametrize("vt,text,sign", NEGATED)
def test_negated_mentions_are_not_flagged(vt, text, sign):
    st = status(text, vt)
    assert st.get(sign) in (None, "NEGATED"), st
    assert "POSITIVE" not in st.values(), st


UNCERTAIN = [
    ("ANC", "bukhar hai", "MATERNAL_HIGH_FEVER"),            # MCP lists HIGH fever in pregnancy
    ("ANC", "pata nahi bleeding hai ya nahi", "PREG_BLEEDING"),
    ("ANC", "shayad bleeding hai", "PREG_BLEEDING"),
    ("ANC", "pichhli pregnancy mein bleeding hui thi", "PREG_BLEEDING"),
    ("PNC", "thodi bleeding hai", "PREG_BLEEDING"),          # normal lochia vs excessive -> ask
    ("ANC", "pairon mein sujan hai", "PREG_SWELLING_ALL_OVER"),
    ("IMMUNISATION", "tika lagne ke baad bukhar hai", "CHILD_HIGH_FEVER"),
    ("ANC", "sar dard hai", "PREG_HEADACHE_BLURRED_VISION"),
]


@pytest.mark.parametrize("vt,text,sign", UNCERTAIN)
def test_uncertain_mentions_ask_instead_of_ignoring(vt, text, sign):
    st = status(text, vt)
    assert st.get(sign) == "UNCERTAIN", st
    assert "POSITIVE" not in st.values()


CLEAN = [
    ("ANC", "khoon ki jaanch hui, report normal"),   # blood TEST is not bleeding
    ("ANC", "she is fit and fine"),                   # 'fit' is not 'fits'
    ("ANC", "ASHA ka daura tha"),                     # daura = visit
    ("NEWBORN", "baby theek se doodh pee raha hai"),
    ("ANC", "ANC checkup for beneficiary 1024, weight 52 kilo, TT injection, IFA goli given"),
    ("IMMUNISATION", "penta 2 diya, agla tika next month"),
]


@pytest.mark.parametrize("vt,text", CLEAN)
def test_no_false_alarm_on_unrelated_text(vt, text):
    st = status(text, vt)
    assert "POSITIVE" not in st.values() and "UNCERTAIN" not in st.values(), st


def test_multiple_signs_in_one_note():
    st = status("ANC visit, khoon aa raha hai aur tez bukhar bhi hai", "ANC")
    assert st["PREG_BLEEDING"] == "POSITIVE" and st["MATERNAL_HIGH_FEVER"] == "POSITIVE"


def test_newborn_fever_and_maternal_fever_do_not_double_ask():
    findings = evaluate("bukhar hai", "IMMUNISATION")
    assert [f.status for f in findings].count("UNCERTAIN") == 1


def test_every_sign_cites_the_mcp_source_and_has_three_languages():
    for s in SIGNS:
        assert "MCP" in s.source_ref or "GB" in s.source_ref
        assert set(s.label) >= {"en", "hi", "kn"}
    assert len(catalogue()) == len(SIGNS)


def test_engine_never_outputs_advice_words():
    for f in evaluate("bleeding aur tez bukhar", "ANC"):
        text = " ".join(f.label.values()).lower()
        for banned in ("paracetamol", "tablet", "dose", "mg", "medicine", "दवा", "ಔಷಧ"):
            assert banned not in text
