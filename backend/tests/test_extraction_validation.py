from datetime import date

from app.services.corrections import bare_target, classify
from app.services.extraction import RuleExtractor, merge
from app.services.validation import can_save, missing_to_ask, validate
from app.storage.seed import SYNTHETIC_BENEFICIARIES

TODAY = date(2026, 11, 11)
RX = RuleExtractor(SYNTHETIC_BENEFICIARIES)
IDS = {b["synthetic_external_id"] for b in SYNTHETIC_BENEFICIARIES}


def ex(text, expect=None):
    e = RX.extract(text, TODAY, expect=expect)
    return {k: v.value for k, v in e.fields.items()}, e


def test_brief_example_extracts_only_stated_fields():
    f, _ = ex("ANC checkup for beneficiary 1024. Weight is 52 kilos. TT injection recorded. IFA goli given. "
              "Next visit is on 20 November.")
    assert f == {"visit_type": "ANC", "beneficiary_id": "1024", "beneficiary_name": "Sunita Devi", "weight_kg": 52.0,
                 "vaccinations_given": ["TT/Td"], "ifa_tablets_given": True, "next_visit_date": "2026-11-20"}
    # nothing invented
    assert "vaccinations_due" not in f and "visit_date" not in f


def test_hindi_devanagari_note():
    f, _ = ex("लाभार्थी आईडी एक शून्य दो चार, एएनसी चेकअप, वज़न बावन किलो, टीटी का इंजेक्शन लगा, आयरन की गोली दी, "
              "अगली विज़िट बीस नवंबर")
    assert f["beneficiary_id"] == "1024" and f["visit_type"] == "ANC" and f["weight_kg"] == 52
    assert f["vaccinations_given"] == ["TT/Td"] and f["ifa_tablets_given"] is True
    assert f["next_visit_date"] == "2026-11-20"


def test_kannada_note():
    f, _ = ex("ಫಲಾನುಭವಿ ಸಂಖ್ಯೆ 1007, ಎಎನ್‌ಸಿ ಭೇಟಿ, ತೂಕ ಐವತ್ತೆರಡು ಕೆಜಿ, ಐಎಫ್‌ಎ ಮಾತ್ರೆ ಕೊಟ್ಟಿದೆ, ಮುಂದಿನ ಭೇಟಿ ನವೆಂಬರ್ 25")
    assert f["beneficiary_id"] == "1007" and f["beneficiary_name"] == "Lakshmi Gowda"
    assert f["weight_kg"] == 52 and f["ifa_tablets_given"] is True and f["next_visit_date"] == "2026-11-25"


def test_newborn_decimal_weight_and_vaccine_given_vs_due():
    f, _ = ex("Newborn visit for 1042, weight do point aath kilo, BCG aur OPV zero diya, Penta 1 due hai")
    assert f["visit_type"] == "NEWBORN" and f["weight_kg"] == 2.8
    assert f["vaccinations_given"] == ["BCG", "OPV-0"] and f["vaccinations_due"] == ["Pentavalent-1"]


def test_grams_are_converted_and_not_mistaken_for_an_id():
    f, _ = ex("baby weight 2800 gram")
    assert f["weight_kg"] == 2.8 and "beneficiary_id" not in f


def test_negated_ifa_and_vaccine():
    f, _ = ex("IFA nahi di, TT nahi laga")
    assert f["ifa_tablets_given"] is False and "vaccinations_given" not in f


def test_similar_names_are_ambiguous():
    f, e = ex("Sunita ka ANC visit")
    assert "ambiguous_name" in e.notes and e.fields["beneficiary_name"].confidence == "confirm"
    assert "beneficiary_id" not in f


def test_name_id_mismatch_flagged():
    _, e = ex("Sunita Kumari, beneficiary 1024")
    assert e.fields["beneficiary_id"].confidence == "confirm"


def test_unknown_id_flagged_by_validation():
    f, e = ex("beneficiary 9999 ANC")
    meta = {k: v.public() for k, v in e.fields.items()}
    issues = validate(f, meta, TODAY, IDS)
    assert any(i.code == "id_unknown" for i in issues) and meta["beneficiary_id"]["confidence"] == "confirm"


def test_weight_range_by_visit_type():
    meta = {}
    issues = validate({"visit_type": "NEWBORN", "weight_kg": 28.0, "beneficiary_id": "1042"}, meta, TODAY, IDS)
    assert any(i.code == "weight_out_of_range" for i in issues)
    assert not validate({"visit_type": "ANC", "weight_kg": 52, "beneficiary_id": "1024"}, {}, TODAY, IDS)


def test_next_visit_must_follow_visit_date():
    issues = validate({"visit_type": "ANC", "beneficiary_id": "1024", "next_visit_date": "2026-11-01"}, {}, TODAY, IDS)
    assert any(i.code == "next_before_visit" for i in issues)


def test_missing_fields_order_and_can_save():
    r = {"beneficiary_id": None, "visit_type": None, "weight_kg": None, "next_visit_date": None}
    assert missing_to_ask(r, set()) == "beneficiary_id"
    assert missing_to_ask(r, {"beneficiary_id"}) == "visit_type"
    assert missing_to_ask(r, {"beneficiary_id", "visit_type"}) == "weight_kg"
    assert not can_save(r) and can_save({"beneficiary_id": "1024", "visit_type": "ANC"})


def test_expected_field_bare_answers():
    assert ex("1024", expect="beneficiary_id")[0]["beneficiary_id"] == "1024"
    assert ex("chauvan", expect="weight_kg")[0]["weight_kg"] == 54
    assert ex("बीस नवंबर", expect="next_visit_date")[0]["next_visit_date"] == "2026-11-20"


def test_llm_merge_requires_grounding():
    rule = RX.extract("ANC visit 1024 weight 52 kilo", TODAY)
    llm = {"weight_kg": {"value": 52, "evidence": "weight 52 kilo"},
           "next_visit_date": {"value": "2026-11-30", "evidence": "next visit thirty november"},  # not in text
           "vaccinations_given": {"value": ["TT/Td"], "evidence": "ANC visit"}}
    out = merge(rule, llm, "ANC visit 1024 weight 52 kilo")
    assert "next_visit_date" not in out.fields           # ungrounded -> discarded
    assert out.fields["vaccinations_given"].confidence == "confirm" and out.fields["vaccinations_given"].source == "llm"
    assert out.fields["weight_kg"].confidence == "high"  # agreement keeps rule confidence


def test_llm_disagreement_marks_confirm():
    rule = RX.extract("weight 52 kilo", TODAY)
    out = merge(rule, {"weight_kg": {"value": 25, "evidence": "52 kilo"}}, "weight 52 kilo")
    assert out.fields["weight_kg"].value == 52 and out.fields["weight_kg"].confidence == "confirm"


# ---------------------------------------------------------------- corrections
def intent(text, expect=None):
    return classify(text, TODAY, RX, expect=expect)


def test_correction_with_field_word_patches_only_that_field():
    i = intent("No, weight is 54 kilos")
    assert i.kind == "PATCH" and set(i.patch) == {"weight_kg"} and i.patch["weight_kg"].value == 54


def test_brief_correction_example_newborn():
    i = intent("no, weight is 2.8 kilo")
    assert i.kind == "PATCH" and i.patch["weight_kg"].value == 2.8


def test_bare_number_needs_unambiguous_context():
    i = intent("No, 54")
    assert i.kind == "BARE" and i.bare_value == 54
    assert bare_target(54, "weight_kg", {}) == "weight_kg"
    assert bare_target(54, None, {}) is None           # full read-back -> ask which field


def test_yes_no_undo_repeat_skip_advice():
    assert intent("haan sahi hai").kind == "YES"
    assert intent("हाँ").kind == "YES"
    assert intent("ಹೌದು").kind == "YES"
    assert intent("sab theek hai").kind == "YES"
    assert intent("nahi").kind == "NO"
    assert intent("sahi nahi hai").kind == "NO"       # negation wins: never save on ambiguity
    assert intent("ತಪ್ಪು").kind == "NO"
    assert intent("undo karo").kind == "UNDO"
    assert intent("phir se bolo").kind == "REPEAT"
    assert intent("skip", expect="weight_kg").kind == "SKIP"
    assert intent("kaunsi dawai du?").kind == "ADVICE"
    assert intent("hmm").kind == "UNKNOWN"


def test_vaccine_removal_by_negation():
    i = intent("OPV nahi diya")
    assert "OPV" in i.remove_given


def test_mid_sentence_id_self_correction_takes_later_value():
    f, e = ex("लाभार्थी नंबर एक हज़ार उनसठ नहीं, एक शून्य नौ शून्य, एएनसी")
    assert f["beneficiary_id"] == "1090" and "id_self_corrected" in e.notes


def test_dose_spoken_as_number_word():
    f, _ = ex("immunisation 1081 penta teen diya")
    assert f["vaccinations_given"] == ["Pentavalent-3"]
