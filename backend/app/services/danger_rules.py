"""Deterministic danger-sign engine (no LLM involvement in escalation).

SOURCE (cited in docs/danger-sign-guideline.md and README):
  [MCP]  Mother and Child Protection Card, 2018 version. Ministry of Health & Family
         Welfare and Ministry of Women & Child Development, Government of India.
         https://nhm.gov.in/New_Updates_2018/NHM_Components/Immunization/Guildelines_for_immunization/MCP_Card_English_version.pdf
  [GB]   Guidebook for Mother-Child Protection Card 2018 for ANM | ASHA | AWW (MoHFW & MoWCD).
         Section 6 "Emergency Care and Preparation for Delivery" pp. 14-15 (pregnancy danger
         signs); Section 8 "Care of Newborn and HBYC" p. 19 (newborn danger signs).
         https://iec.unicef.in/public/uploads/documents/222758bf054a1620a8bc64fe41f4ace2.pdf

Only signs that appear in those documents are implemented. Phrase variants (Hindi,
Kannada, English, romanised code-mix) were written by the build team and MUST be reviewed
by a health professional before any real use. This is a hackathon prototype, not a
clinically validated tool.

Pipeline: transcript -> match form -> clause split -> pattern match -> uncertainty / past /
other-person context -> negation window -> visit-type applicability -> result.
Recall-first: anything not clearly negated but not clearly positive becomes UNCERTAIN and
the agent asks one short yes/no question. Nothing is silently dropped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalise import WORD_CHARS, clauses, match_form

B = rf"(?<![{WORD_CHARS}])"   # word boundary (Indic-safe)
E = rf"(?![{WORD_CHARS}])"
G = r"(?:\s+\S+){0,3}?\s+"      # up to 3 intervening words


def _alt(*parts: str) -> str:
    return "(?:" + "|".join(parts) + ")"


@dataclass
class Sign:
    id: str
    label: dict                     # spoken / displayed label per language
    applies_to: tuple               # visit types where a positive match escalates immediately
    source_ref: str
    positive: list[str]             # regexes on match-form text (already lower-case, no nukta)
    uncertain: list[str] = field(default_factory=list)  # mentions needing a yes/no confirmation
    inherent_negation: bool = False  # phrase itself contains a negation ("not feeding")
    subject: str = "mother"          # mother | baby (chooses referral wording)


BLEED_WORDS = _alt("bleeding", "bleed", "spotting", "ब्लीडिंग", "रक्तस्राव", "रक्त स्राव", "ರಕ್ತಸ್ರಾವ",
                   "ರಕ್ತ ಸ್ರಾವ", "ಬ್ಲೀಡಿಂಗ್", "raktasrav", "rakt srav", "rakta srava", "raktasrava")
BLOOD_FLOW = (
    r"(?:khoon|khun|खून|blood|रक्त|ರಕ್ತ|rakta)\s+(?:\S+\s+)?"
    r"(?:aa|aana|aaya|aayi|a|gir|gira|girna|ja|jaa|jana|beh|bah|आ|आना|आया|आई|गिर|गिरा|गिरना|जा|जाना|बह|बहना|"
    r"coming|flowing|ಬರುತ್ತಿದೆ|ಹೋಗುತ್ತಿದೆ|ಬರ್ತಿದೆ|ಹೋಗ್ತಿದೆ|ಬಂತು|ಹೋಯಿತು)"
    r"(?:\s+(?:raha|rahi|रहा|रही|hai|है))?"
)
EXCESS = _alt("heavy", "excessive", "too much", "a lot of", "bahut", "bohot", "jyada", "zyada", "jada",
              "बहुत", "ज्यादा", "अधिक", "ತುಂಬಾ", "ಅತಿಯಾದ", "ಹೆಚ್ಚು", "ಜಾಸ್ತಿ", "tumba", "jaasti")
FEVER = _alt("fever", "bukhar", "bukhaar", "bukhār", "बुखार", "ज्वर", "ताप", "ಜ್ವರ", "jwara", "jvara", "taap")
HIGH = _alt("high", "tez", "tej", "teez", "तेज", "bahut", "बहुत", "jor", "जोर", "ಜೋರು", "ತೀವ್ರ", "ಹೆಚ್ಚು",
            "ತುಂಬಾ", "severe", "very")

SIGNS: list[Sign] = [
    # ---------------------------------------------------------------- pregnancy (MCP / GB p.14-15)
    Sign("PREG_BLEEDING",
         {"en": "bleeding during pregnancy", "hi": "गर्भावस्था में खून आना", "kn": "ಗರ್ಭಾವಸ್ಥೆಯಲ್ಲಿ ರಕ್ತಸ್ರಾವ"},
         ("ANC", None), "MCP 2018 pregnancy danger signs: 'Bleeding during pregnancy'; GB pp.14-15",
         positive=[BLEED_WORDS, BLOOD_FLOW, r"(?:pv|p v|vaginal)\s+(?:bleeding|blood)"]),
    Sign("PNC_EXCESSIVE_BLEEDING",
         {"en": "excessive bleeding after delivery", "hi": "डिलीवरी के बाद बहुत ज़्यादा खून आना",
          "kn": "ಹೆರಿಗೆಯ ನಂತರ ಅತಿಯಾದ ರಕ್ತಸ್ರಾವ"},
         ("PNC", None), "MCP 2018 'In case of emergency after delivery': 'Excessive bleeding during or after delivery'; GB p.15",
         positive=[EXCESS + G.replace("{0,3}", "{0,2}") + _alt(BLEED_WORDS, r"(?:khoon|khun|खून|blood|ರಕ್ತ)"),
                   r"(?:pad|पैड|ಪ್ಯಾಡ್)\s*(?:\S+\s+){0,2}(?:bhar|भर|soak|ತುಂಬ)\S*"]),
    Sign("MATERNAL_HIGH_FEVER",
         {"en": "high fever", "hi": "तेज़ बुखार", "kn": "ತೀವ್ರ ಜ್ವರ"},
         ("ANC", "PNC", None), "MCP 2018: 'High fever during pregnancy or within one month of delivery'; GB p.15",
         positive=[HIGH + r"\s+(?:\S+\s+)?" + FEVER, FEVER + r"\s+(?:bahut|बहुत|tez|तेज|ತುಂಬಾ)\s+(?:tez|तेज|zyada|ज्यादा|ಜಾಸ್ತಿ|hai|है)"],
         uncertain=[FEVER]),
    Sign("PREG_SEVERE_ANAEMIA",
         {"en": "severe anaemia", "hi": "खून की बहुत कमी (गंभीर एनीमिया)", "kn": "ತೀವ್ರ ರಕ್ತಹೀನತೆ"},
         ("ANC", "PNC", None), "MCP 2018: 'Severe Anemia with or without breathlessness'; GB p.15",
         positive=[r"(?:severe|गंभीर|ತೀವ್ರ)\s+(?:anaemia|anemia|एनीमिया|ರಕ್ತಹೀನತೆ)",
                   r"(?:khoon|खून)\s+(?:ki|की)\s+(?:bahut|बहुत|ज्यादा|jyada|zyada)\s+(?:kami|कमी)"],
         uncertain=[r"(?:anaemia|anemia|एनीमिया|ರಕ್ತಹೀನತೆ|rakthaheenathe)", r"(?:khoon|खून)\s+(?:ki|की)\s+(?:kami|कमी)"]),
    Sign("PREG_HEADACHE_BLURRED_VISION",
         {"en": "severe headache or blurred vision", "hi": "तेज़ सिरदर्द या धुंधला दिखना",
          "kn": "ತೀವ್ರ ತಲೆನೋವು ಅಥವಾ ಮಸುಕಾದ ದೃಷ್ಟಿ"},
         ("ANC", "PNC", None), "MCP 2018: 'Headache, blurring of vision, fits and swelling all over the body'; GB p.15",
         positive=[r"blur\S*\s+(?:vision|sight)", r"(?:vision|sight)\s+(?:is\s+)?blur\S*", r"blurring\s+of\s+vision",
                   r"(?:dhundhla|dhundla|धुंधला|धुंधली)\S*", r"(?:aankhon|आंखों|आँखों)\s+(?:ke|के)\s+(?:aage|आगे)\s+(?:andhera|अंधेरा)",
                   r"(?:ಮಸುಕಾದ|ಮಸುಕು)\s*\S*", r"ಕಣ್ಣು\s+ಮಂಜು\S*",
                   r"(?:severe|tez|तेज|bahut|बहुत|ತೀವ್ರ|ತುಂಬಾ)\s+(?:headache|sar\s?dard|sir\s?dard|सिर\s?दर्द|सिरदर्द|ತಲೆನೋವು|ತಲೆ\s+ನೋವು)"],
         uncertain=[r"(?:headache|sar\s?dard|sir\s?dard|सिर\s?दर्द|सिरदर्द|ತಲೆನೋವು|ತಲೆ\s+ನೋವು)"]),
    Sign("CONVULSIONS",
         {"en": "fits or convulsions", "hi": "झटके या दौरे", "kn": "ಫಿಟ್ಸ್ ಅಥವಾ ಸೆಳೆತ"},
         ("ANC", "PNC", "NEWBORN", "IMMUNISATION", None),
         "MCP 2018: pregnancy 'fits'; newborn 'convulsions'; GB pp.15,19",
         positive=[r"(?:fits|convulsions?|seizures?|फिट्स|ಫಿಟ್ಸ್)", r"(?:jhatke|jhatka|झटके|झटका)",
                   r"(?:daura|daure|दौरा|दौरे)\s+(?:pad|pada|padte|aa|aaya|aate|पड|पडा|पडते|आ|आया|आते)\S*", r"(?:ಸೆಳೆತ|ಸೆಳವು|ಮೂರ್ಛೆ\s*ರೋಗ)", r"abnormal\s+movements?"]),
    Sign("PREG_SWELLING_ALL_OVER",
         {"en": "swelling all over the body or face", "hi": "पूरे शरीर या चेहरे पर सूजन", "kn": "ಮೈಯೆಲ್ಲಾ ಅಥವಾ ಮುಖದ ಮೇಲೆ ಊತ"},
         ("ANC", "PNC", None), "MCP 2018: 'swelling all over the body'; GB p.15",
         positive=[r"swelling\s+all\s+over", r"(?:body|face|facial)\s+swelling", r"swelling\s+(?:on|of|in)\s+(?:the\s+)?(?:face|whole\s+body|body)",
                   r"(?:poore|pure|पूरे|सारे)\s+(?:sharir|shareer|badan|शरीर|बदन)\s+(?:\S+\s+)?(?:sujan|soojan|सूजन)",
                   r"(?:chehre|chehere|मुंह|चेहरे)\s+(?:\S+\s+)?(?:sujan|soojan|सूजन)",
                   r"(?:ಮೈಯೆಲ್ಲಾ|ಮೈಯೆಲ್ಲ|ಮುಖ|ಮುಖದ|ದೇಹ)\s*(?:\S+\s+)?ಊತ\S*"],
         uncertain=[r"(?:swelling|sujan|soojan|सूजन|ಊತ)\S*"]),
    Sign("PREG_WATER_BREAK",
         {"en": "water bag burst / leaking water", "hi": "पानी की थैली फटना या पानी जाना", "kn": "ನೀರಿನ ಚೀಲ ಒಡೆಯುವುದು / ನೀರು ಹೋಗುವುದು"},
         ("ANC", None), "MCP 2018: 'Bursting of water bag without labour pains'; GB p.15",
         positive=[r"water\s+(?:bag\s+)?(?:broke|burst|break|leak)\S*", r"leaking\s+(?:of\s+)?water",
                   r"(?:paani|pani|पानी)\s+(?:ki|की)\s+(?:thaili|थैली)\s+(?:\S+\s+)?(?:phat|फट)\S*",
                   r"(?:paani|pani|पानी)\s+(?:aa|आ|ja|jaa|जा|beh|बह)\S*\s+(?:raha|rahi|रहा|रही|गया|gaya)",
                   r"ನೀರಿನ\s+ಚೀಲ\s+\S*\s*ಒಡೆ\S*", r"ನೀರು\s+(?:ಹೋಗ|ಸೋರ)\S*"]),
    Sign("PREG_REDUCED_FETAL_MOVEMENT",
         {"en": "reduced baby movement in the womb", "hi": "पेट में बच्चे की हलचल कम होना", "kn": "ಹೊಟ್ಟೆಯಲ್ಲಿ ಮಗುವಿನ ಚಲನೆ ಕಡಿಮೆ"},
         ("ANC", None), "GB p.14-15: 'reduced foetal movement'",
         positive=[r"(?:reduced|decreased|less|no)\s+(?:fetal|foetal|baby)\s+movements?",
                   r"baby\s+(?:is\s+)?not\s+moving", r"(?:fetal|foetal|baby)\s+movements?\s+(?:is\s+|are\s+)?(?:less|reduced|decreased)",
                   r"(?:bachcha|baccha|bacha|बच्चा|बच्चे)\s+(?:\S+\s+)?(?:kam|कम)\s+(?:hil|हिल)\S*",
                   r"(?:bachcha|baccha|bacha|बच्चा|बच्चे)\s+(?:\S+\s+)?(?:nahi|nahin|नहीं)\s+(?:hil|हिल)\S*",
                   r"(?:halchal|हलचल)\s+(?:\S+\s+)?(?:kam|कम|nahi|नहीं|band|बंद)",
                   r"ಚಲನೆ\s+(?:ಕಡಿಮೆ|ಇಲ್ಲ)\S*"],
         inherent_negation=True),
    Sign("PREG_PROLONGED_LABOUR",
         {"en": "labour pain for more than 12 hours", "hi": "12 घंटे से ज़्यादा प्रसव पीड़ा", "kn": "12 ಗಂಟೆಗಿಂತ ಹೆಚ್ಚು ಹೆರಿಗೆ ನೋವು"},
         ("ANC", None), "MCP 2018: 'Labour pain for more than 12 hours'",
         positive=[r"(?:12|twelve|बारह|ಹನ್ನೆರಡು)\s+(?:ghante|घंटे|hours?|ಗಂಟೆ)\S*\s+(?:\S+\s+){0,3}(?:dard|दर्द|pain|ನೋವು|labou?r)",
                   r"(?:labou?r|dard|दर्द|ನೋವು)\s+(?:\S+\s+){0,4}(?:12|twelve|बारह|ಹನ್ನೆರಡು)\s+(?:ghante|घंटे|hours?|ಗಂಟೆ)"]),
    # ---------------------------------------------------------------- newborn (MCP / GB p.19)
    Sign("NB_POOR_FEEDING",
         {"en": "baby not feeding or sucking weakly", "hi": "बच्चा दूध नहीं पी रहा या कमज़ोर चूस रहा", "kn": "ಮಗು ಹಾಲು ಕುಡಿಯುತ್ತಿಲ್ಲ"},
         ("NEWBORN", "IMMUNISATION", "PNC", None), "MCP 2018 newborn: 'Is sucking weakly or refuses to breast feed'; GB p.19",
         positive=[r"not\s+(?:breast\s?)?feeding", r"refus\S*\s+(?:to\s+)?(?:breast\s?)?feed\S*", r"(?:sucking|suck)\s+weakly", r"weak\s+suck\S*",
                   r"(?:doodh|dudh|दूध|feed|स्तनपान|stanpan)\s+(?:\S+\s+){0,2}(?:nahi|nahin|नहीं|na|kam|कम)\s+(?:pee|pi|पी|le|ले|kar|कर|choos|चूस)\S*",
                   r"(?:doodh|dudh|दूध)\s+(?:peena|pina|पीना)\s+(?:band|बंद)",
                   r"(?:ಹಾಲು|ಎದೆಹಾಲು|halu)\s+(?:\S+\s+)?(?:ಕುಡಿಯುತ್ತಿಲ್ಲ|ಕುಡಿಯಲ್ಲ|ಕುಡಿಯುವುದಿಲ್ಲ|kudiyuttilla|kudiyalla)",
                   r"ಹಾಲು\s+ಕಡಿಮೆ\s+ಕುಡಿ\S*"],
         inherent_negation=True, subject="baby"),
    Sign("NB_UNABLE_TO_CRY",
         {"en": "baby unable to cry or weak cry", "hi": "बच्चा रो नहीं पा रहा या कमज़ोर रोना", "kn": "ಮಗು ಅಳುತ್ತಿಲ್ಲ"},
         ("NEWBORN", None), "MCP 2018 newborn: 'Is unable to cry or has difficulty in breathing'; GB p.19",
         positive=[r"(?:not|unable\s+to|cannot|can't)\s+cry\S*", r"weak\s+cry", r"(?:ro|रो)\s+(?:nahi|nahin|नहीं)\s+(?:raha|rahi|pa|रहा|रही|पा)\S*",
                   r"(?:rona|रोना)\s+(?:kamzor|कमजोर)", r"(?:ಅಳುತ್ತಿಲ್ಲ|ಅಳುವುದಿಲ್ಲ|aluttilla)"],
         inherent_negation=True, subject="baby"),
    Sign("NB_DIFFICULT_BREATHING",
         {"en": "fast or difficult breathing", "hi": "तेज़ या मुश्किल से सांस लेना", "kn": "ವೇಗವಾದ ಅಥವಾ ಕಷ್ಟದ ಉಸಿರಾಟ"},
         ("NEWBORN", "IMMUNISATION", None), "MCP 2018 newborn: 'difficulty in breathing'; child: 'rapid and/or difficult breathing'; GB p.19",
         positive=[r"(?:difficult\S*|fast|rapid|trouble|problem)\s+(?:in\s+)?breath\S*", r"breath\S*\s+(?:is\s+)?(?:fast|rapid|difficult)",
                   r"chest\s+indrawing", r"(?:saans|sans|सांस|श्वास)\s+(?:\S+\s+){0,3}(?:dikkat|दिक्कत|takleef|तकलीफ|pareshani|परेशानी|tez|तेज|jaldi|जल्दी)",
                   r"(?:tez|तेज)\s+(?:saans|सांस)", r"(?:pasli|पसली)\s+(?:chal|चल)\S*",
                   r"ಉಸಿರಾಟ\S*\s+(?:ತೊಂದರೆ|ಕಷ್ಟ)", r"ವೇಗವಾಗಿ\s+ಉಸಿರಾಡ\S*", r"ಉಸಿರು\s+ಕಟ್ಟ\S*"],
         uncertain=[r"(?:saans|सांस)\s+(?:\S+\s+)?(?:phool|फूल)\S*", r"breathless\S*"], subject="baby"),
    Sign("NB_YELLOW_SKIN",
         {"en": "yellow palms, soles, skin or eyes", "hi": "हथेली, तलवे, त्वचा या आंखें पीली", "kn": "ಅಂಗೈ, ಅಂಗಾಲು ಅಥವಾ ಚರ್ಮ ಹಳದಿ"},
         ("NEWBORN", None), "MCP 2018 newborn: 'Has yellow palms and soles'; GB p.19 (yellow skin: refer)",
         positive=[r"yellow\s+(?:palms?|soles?|skin|eyes?)", r"(?:palms?|soles?|skin|eyes?)\s+(?:\S+\s+){0,2}yellow", r"jaundice",
                   r"(?:peeliya|piliya|पीलिया)", r"(?:hatheli|हथेली|talve|तलवे|tvacha|त्वचा|skin|aankhen|आंखें|आँखें)\s+(?:\S+\s+){0,2}(?:peeli|pili|peele|पीली|पीले)",
                   r"ಕಾಮಾಲೆ", r"(?:ಅಂಗೈ|ಅಂಗಾಲು|ಚರ್ಮ|ಕಣ್ಣು)\S*\s+(?:\S+\s+)?ಹಳದಿ"],
         subject="baby"),
    Sign("NB_FEVER_OR_COLD",
         {"en": "fever or cold to touch", "hi": "बुखार या शरीर ठंडा", "kn": "ಜ್ವರ ಅಥವಾ ಮೈ ತಣ್ಣಗಿರುವುದು"},
         ("NEWBORN", None), "MCP 2018 newborn: 'Has fever or is cold to touch'; GB p.19",
         positive=[FEVER, r"(?:body|badan|बदन|sharir|शरीर|ಮೈ)\s+(?:\S+\s+)?(?:garam|गर्म|hot|ಬಿಸಿ)", r"(?:cold|thanda|ठंडा)\s+to\s+touch",
                   r"(?:thanda|ठंडा|ठंडी)\s+(?:pad|पड़|पड|lag|लग)\S*", r"(?:body|badan|बदन|sharir|शरीर)\s+(?:\S+\s+)?(?:thanda|ठंडा|cold)",
                   r"ಮೈ\s+(?:\S+\s+)?ತಣ್ಣಗ\S*", r"hypothermia", r"feels?\s+(?:very\s+)?(?:hot|cold)"],
         subject="baby"),
    Sign("NB_BLOOD_IN_STOOL",
         {"en": "blood in stools", "hi": "मल में खून", "kn": "ಮಲದಲ್ಲಿ ರಕ್ತ"},
         ("NEWBORN", "IMMUNISATION", None), "MCP 2018 newborn: 'Has blood in stools or convulsions'; GB p.19",
         positive=[r"blood\s+in\s+(?:the\s+)?(?:stool|stools|potty|motion)", r"(?:potty|पॉटी|पोटी|tatti|टट्टी|mal|मल|stool|dast|दस्त)\s+(?:\S+\s+)?(?:mein|में|me)\s+(?:khoon|खून|blood)",
                   r"ಮಲದಲ್ಲಿ\s+ರಕ್ತ"], subject="baby"),
    Sign("NB_LETHARGIC_UNCONSCIOUS",
         {"en": "baby lethargic or unconscious", "hi": "बच्चा सुस्त या बेहोश", "kn": "ಮಗು ಜಡವಾಗಿದೆ ಅಥವಾ ಪ್ರಜ್ಞೆ ಇಲ್ಲ"},
         ("NEWBORN", "IMMUNISATION", None), "MCP 2018 newborn: 'Is lethargic or unconscious'; GB p.19",
         positive=[r"letharg\S*", r"unconscious", r"(?:very\s+)?limp", r"not\s+responding", r"(?:sust|सुस्त|behosh|बेहोश)",
                   r"(?:dheela|ढीला)\s+(?:pad|पड़|पड)\S*", r"ಪ್ರಜ್ಞೆ\s+(?:ಇಲ್ಲ|ತಪ್ಪ)\S*", r"ಜಡವಾಗ\S*"],
         subject="baby"),
    # ---------------------------------------------------------------- child care during illness (MCP)
    Sign("CHILD_HIGH_FEVER",
         {"en": "high fever in the child", "hi": "बच्चे को तेज़ बुखार", "kn": "ಮಗುವಿಗೆ ತೀವ್ರ ಜ್ವರ"},
         ("IMMUNISATION",), "MCP 2018 care during illness: 'If the child has high fever take her/him to the health centre'",
         positive=[HIGH + r"\s+(?:\S+\s+)?" + FEVER], uncertain=[FEVER], subject="baby"),
    Sign("CHILD_DIARRHOEA_NOT_STOPPING",
         {"en": "loose motions not stopping", "hi": "दस्त बंद नहीं हो रहे", "kn": "ಭೇದಿ ನಿಲ್ಲುತ್ತಿಲ್ಲ"},
         ("IMMUNISATION", "NEWBORN", None), "MCP 2018 care during illness: 'Take the child to hospital if loose motion do not stop'",
         positive=[r"(?:loose\s+motions?|diarrho?ea|dast|दस्त)\s+(?:\S+\s+){0,2}(?:not\s+stop\S*|nahi\s+ruk\S*|नहीं\s+रुक\S*|band\s+nahi|बंद\s+नहीं)",
                   r"ಭೇದಿ\s+ನಿಲ್ಲುತ್ತಿಲ್ಲ"],
         uncertain=[r"(?:loose\s+motions?|diarrho?ea|dast|दस्त|ಭೇದಿ)"], inherent_negation=True, subject="baby"),
]

def _rx_form(p: str) -> str:
    """Apply the orthographic parts of match_form to a regex (no lower-casing: \\S != \\s)."""
    return p.replace("\u093C", "").replace("\u0901", "\u0902").replace("\u200C", "").replace("\u200D", "")


_COMPILED = [(s, [re.compile(B + _rx_form(p) + E) for p in s.positive],
              [re.compile(B + _rx_form(p) + E) for p in s.uncertain]) for s in SIGNS]

NEG_AFTER = {match_form(w) for w in ["nahi", "nahin", "nai", "nahi.", "नहीं", "नही", "ना", "न", "not", "no",
                                      "ಇಲ್ಲ", "ಇಲ್ಲಾ", "illa", "absent", "negative"]}
NEG_BEFORE = {match_form(w) for w in ["no", "not", "without", "never", "denies", "deny", "bina", "बिना", "na", "न", "ना", "nil"]}
STOP_POSITIVE = {match_form(w) for w in ["hai", "है", "ho", "हो", "hua", "हुआ", "hui", "हुई", "raha", "rahi", "रहा", "रही",
                                          "gaya", "गया", "gayi", "गई", "tha", "था", "thi", "थी", "is", "has", "have", "was",
                                          "started", "ಇದೆ", "ಆಗಿದೆ", "ಆಗುತ್ತಿದೆ", "ಬರುತ್ತಿದೆ", "ide", "aagide", "and", "aur",
                                          "और", "ಮತ್ತು"]}
CONTINUE_STEMS = tuple(match_form(w) for w in ["ruk", "रुक", "band", "बंद", "stop", "ನಿಲ್ಲ", "kam", "कम", "ಕಡಿಮೆ", "reduc"])
_KN_NEG_SUFFIX = ("ಿಲ್ಲ", "ಿಲ್ಲಾ")
UNCERTAIN_PHRASES = [match_form(p) for p in [
    "pata nahi", "pata nahin", "पता नहीं", "not sure", "unsure", "shayad", "शायद", "maybe", "perhaps", "possibly",
    "lagta hai", "लगता है", "ho sakta", "हो सकता", "ಗೊತ್ತಿಲ್ಲ", "ಇರಬಹುದು", "ಅನ್ನಿಸುತ್ತ", "doubt", "check karna", "confirm nahi"]]
PAST_OR_OTHER = {match_form(w) for w in ["pichhli", "pichli", "pichhle", "pichle", "पिछली", "पिछले", "previous", "last",
                                          "history", "padosi", "पड़ोसी", "पडोसी", "neighbour", "neighbor", "ಹಿಂದಿನ",
                                          "ಕಳೆದ", "ಪಕ್ಕದ್ಮನೆ", "earlier"]}
SINCE = {match_form(w) for w in ["se", "से", "since", "from"]}


@dataclass
class SignFinding:
    sign_id: str
    status: str            # POSITIVE | UNCERTAIN | NEGATED
    matched_phrase: str
    reason: str
    span: tuple
    label: dict
    source_ref: str
    subject: str
    applicable: bool

    def public(self) -> dict:
        return {"id": self.sign_id, "status": self.status, "matched_phrase": self.matched_phrase,
                "reason": self.reason, "label": self.label, "source_ref": self.source_ref,
                "subject": self.subject, "rule_id": f"RULE_{self.sign_id}"}


def _words(seg: str) -> list[str]:
    return re.findall(rf"[{WORD_CHARS}]+", seg)


def _is_neg_after(w: str) -> bool:
    return w in NEG_AFTER or w.endswith(_KN_NEG_SUFFIX)


def _negated(text: str, cs: int, ce: int, ms: int, me: int) -> bool:
    inside = _words(text[ms:me])
    if any(_is_neg_after(w) for w in inside[1:]):   # "खून नहीं आ रहा" (negation inside the phrase)
        return True
    before = _words(text[cs:ms])[-3:]
    if any(w in NEG_BEFORE for w in before):
        return True
    after = _words(text[me:ce])[:5]
    for w in after:
        if w.startswith(CONTINUE_STEMS):   # "ruk nahi rahi" = NOT stopping -> still positive
            return False
        if _is_neg_after(w):
            return True
        if w in STOP_POSITIVE:
            return False
    return False


def evaluate(transcript: str, visit_type: str | None) -> list[SignFinding]:
    """Return findings for every danger-sign mention in the transcript."""
    text = match_form(transcript)
    if not text:
        return []
    # mask uncertainty phrases so their own negation words ("pata nahi") are not
    # read as negating a sign; remember which clauses contained them
    masked = text
    unc_spans = []
    for p in UNCERTAIN_PHRASES:
        for m in re.finditer(rf"(?<![{WORD_CHARS}]){re.escape(p)}(?![{WORD_CHARS}])", masked):
            unc_spans.append((m.start(), m.end()))
            masked = masked[:m.start()] + ("~" * (m.end() - m.start())) + masked[m.end():]
    cls = clauses(masked)
    findings: list[SignFinding] = []
    for sign, pos_res, unc_res in _COMPILED:
        applicable = visit_type in sign.applies_to or visit_type is None
        for kind, regexes in (("pos", pos_res), ("unc", unc_res)):
            for rx in regexes:
                for m in rx.finditer(masked):
                    ms, me = m.start(), m.end()
                    cs, ce = next(((a, b) for a, b in cls if a <= ms < b), (0, len(masked)))
                    phrase = text[ms:me]
                    clause_words = _words(masked[cs:ce])
                    has_unc = any(cs <= a < ce for a, _ in unc_spans)
                    past = False
                    for k, w in enumerate(clause_words):
                        if w in PAST_OR_OTHER:
                            nxt = clause_words[k + 1:k + 4]
                            if not any(x in SINCE or x.endswith(("ಿಂದ", "ಇಂದ")) for x in nxt):
                                past = True
                    negated = False if sign.inherent_negation and kind == "pos" else _negated(masked, cs, ce, ms, me)
                    if negated and not has_unc:
                        status, reason = "NEGATED", "explicitly negated in the same clause"
                    elif negated and has_unc:
                        status, reason = "UNCERTAIN", "negation with uncertainty marker"
                    elif has_unc:
                        status, reason = "UNCERTAIN", "uncertainty marker in the same clause"
                    elif past:
                        status, reason = "UNCERTAIN", "may refer to the past or another person"
                    elif kind == "unc":
                        status, reason = "UNCERTAIN", "mention needs confirmation against the listed sign"
                    elif not applicable:
                        status, reason = "UNCERTAIN", f"listed sign for a different visit type than {visit_type}"
                    else:
                        status, reason = "POSITIVE", "listed danger sign mentioned"
                    findings.append(SignFinding(sign.id, status, phrase, reason, (ms, me), sign.label,
                                                sign.source_ref, sign.subject, applicable))
    return _resolve(findings)


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _resolve(findings: list[SignFinding]) -> list[SignFinding]:
    """One finding per sign (strongest status wins); an UNCERTAIN finding whose text span is
    already covered by a POSITIVE finding of another sign is dropped (no double questions);
    a NEGATED finding suppresses an UNCERTAIN 'needs confirmation' of the same span."""
    rank = {"POSITIVE": 3, "UNCERTAIN": 2, "NEGATED": 1}
    best: dict[str, SignFinding] = {}
    for f in findings:
        cur = best.get(f.sign_id)
        if cur is None or rank[f.status] > rank[cur.status]:
            best[f.sign_id] = f
    out = list(best.values())
    positives = [f for f in out if f.status == "POSITIVE"]
    negs = [f for f in out if f.status == "NEGATED"]
    result = []
    kept_unc: list[SignFinding] = []
    out.sort(key=lambda f: (not f.applicable, f.span[0]))
    for f in out:
        if f.status == "UNCERTAIN" and any(_overlap(f.span, p.span) for p in positives):
            continue
        if f.status == "UNCERTAIN" and any(_overlap(f.span, k.span) for k in kept_unc):
            continue
        if f.status == "UNCERTAIN" and f.reason.startswith("mention needs") and any(_overlap(f.span, n.span) for n in negs):
            continue
        if f.status == "UNCERTAIN":
            kept_unc.append(f)
        result.append(f)
    result.sort(key=lambda f: (-rank[f.status], f.span[0]))
    return result


def sign_by_id(sign_id: str) -> Sign | None:
    return next((s for s in SIGNS if s.id == sign_id), None)


def catalogue() -> list[dict]:
    return [{"id": s.id, "label": s.label, "applies_to": [a for a in s.applies_to if a], "source_ref": s.source_ref,
             "subject": s.subject} for s in SIGNS]
