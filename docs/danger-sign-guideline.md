# Danger-sign list, source guideline and rule design

> **Status:** prototype rule set for the Gnani Voice Hackathon 2026. It has **not** been clinically validated. The sign list was taken only from the documents below; the phrase variants and the Hindi/Kannada referral wording were written by the build team and need review by a health professional and native speakers before any real use.

## 1. Source documents

| # | Issuing authority | Title | Edition | URL | Pages / sections used |
|---|---|---|---|---|---|
| MCP | Ministry of Health & Family Welfare and Ministry of Women & Child Development, Government of India | Mother and Child Protection Card (MCP Card) | 2018 version (English) | https://nhm.gov.in/New_Updates_2018/NHM_Components/Immunization/Guildelines_for_immunization/MCP_Card_English_version.pdf | Panels: "If you or anyone in your family sees any of these danger signs, take the pregnant woman to the hospital immediately"; "In case of emergency after delivery"; "Danger signs: contact your health worker if the baby…"; "Care during illness" |
| GB | MoHFW & MoWCD, Government of India | Guidebook for Mother-Child Protection Card 2018 for ANM / ASHA / AWW | 2018 | https://iec.unicef.in/public/uploads/documents/222758bf054a1620a8bc64fe41f4ace2.pdf | Section 6 "Emergency Care and Preparation for Delivery", pp. 14–15; Section 8 "Care of Newborn and HBYC", p. 19 |

Page numbers for the Guidebook come from its table of contents as extracted from the PDF text. The MCP card itself is a folded card whose extracted text carried no reliable page markers, so its panels are cited by heading. **Before submission, open both PDFs and confirm the page numbers against the printed copy.**

### Signs listed in the sources (as written)
- **Pregnancy (MCP):** high fever during pregnancy or within one month of delivery; labour pain for more than 12 hours; severe anaemia with or without breathlessness; headache, blurring of vision, fits and swelling all over the body; bursting of water bag without labour pains; bleeding during pregnancy. **GB pp. 14–15** adds reduced foetal movement and pre-term labour pain, with the instruction to take the woman to the nearest hospital or FRU immediately.
- **After delivery (MCP):** excessive bleeding during or after delivery.
- **Newborn (MCP; GB p. 19):** sucking weakly or refusing to breastfeed; unable to cry or difficulty in breathing; yellow palms and soles (GB: yellow skin also to be referred); fever or cold to touch; blood in stools or convulsions; lethargic or unconscious.
- **Child, care during illness (MCP):** rapid and/or difficult breathing → health centre; high fever → health centre; loose motions that do not stop → hospital.

The hackathon brief's examples (bleeding in pregnancy, high fever in a newborn) are both covered.

## 2. Implemented canonical signs

| Rule id | Sign (en) | hi / kn label | Escalates immediately for visit types | Subject | Source | Patterns |
|---|---|---|---|---|---|---|
| `PREG_BLEEDING` | bleeding during pregnancy | गर्भावस्था में खून आना / ಗರ್ಭಾವಸ್ಥೆಯಲ್ಲಿ ರಕ್ತಸ್ರಾವ | ANC | mother | MCP 2018 pregnancy danger signs: 'Bleeding during pregnancy'; GB pp.14-15 | 3 positive / 0 confirm patterns |
| `PNC_EXCESSIVE_BLEEDING` | excessive bleeding after delivery | डिलीवरी के बाद बहुत ज़्यादा खून आना / ಹೆರಿಗೆಯ ನಂತರ ಅತಿಯಾದ ರಕ್ತಸ್ರಾವ | PNC | mother | MCP 2018 'In case of emergency after delivery': 'Excessive bleeding during or after delivery'; GB p.15 | 2 positive / 0 confirm patterns |
| `MATERNAL_HIGH_FEVER` | high fever | तेज़ बुखार / ತೀವ್ರ ಜ್ವರ | ANC, PNC | mother | MCP 2018: 'High fever during pregnancy or within one month of delivery'; GB p.15 | 2 positive / 1 confirm patterns |
| `PREG_SEVERE_ANAEMIA` | severe anaemia | खून की बहुत कमी (गंभीर एनीमिया) / ತೀವ್ರ ರಕ್ತಹೀನತೆ | ANC, PNC | mother | MCP 2018: 'Severe Anemia with or without breathlessness'; GB p.15 | 2 positive / 2 confirm patterns |
| `PREG_HEADACHE_BLURRED_VISION` | severe headache or blurred vision | तेज़ सिरदर्द या धुंधला दिखना / ತೀವ್ರ ತಲೆನೋವು ಅಥವಾ ಮಸುಕಾದ ದೃಷ್ಟಿ | ANC, PNC | mother | MCP 2018: 'Headache, blurring of vision, fits and swelling all over the body'; GB p.15 | 8 positive / 1 confirm patterns |
| `CONVULSIONS` | fits or convulsions | झटके या दौरे / ಫಿಟ್ಸ್ ಅಥವಾ ಸೆಳೆತ | ANC, PNC, NEWBORN, IMMUNISATION | mother | MCP 2018: pregnancy 'fits'; newborn 'convulsions'; GB pp.15,19 | 5 positive / 0 confirm patterns |
| `PREG_SWELLING_ALL_OVER` | swelling all over the body or face | पूरे शरीर या चेहरे पर सूजन / ಮೈಯೆಲ್ಲಾ ಅಥವಾ ಮುಖದ ಮೇಲೆ ಊತ | ANC, PNC | mother | MCP 2018: 'swelling all over the body'; GB p.15 | 6 positive / 1 confirm patterns |
| `PREG_WATER_BREAK` | water bag burst / leaking water | पानी की थैली फटना या पानी जाना / ನೀರಿನ ಚೀಲ ಒಡೆಯುವುದು / ನೀರು ಹೋಗುವುದು | ANC | mother | MCP 2018: 'Bursting of water bag without labour pains'; GB p.15 | 6 positive / 0 confirm patterns |
| `PREG_REDUCED_FETAL_MOVEMENT` | reduced baby movement in the womb | पेट में बच्चे की हलचल कम होना / ಹೊಟ್ಟೆಯಲ್ಲಿ ಮಗುವಿನ ಚಲನೆ ಕಡಿಮೆ | ANC | mother | GB p.14-15: 'reduced foetal movement' | 7 positive / 0 confirm patterns (phrase contains its own negation) |
| `PREG_PROLONGED_LABOUR` | labour pain for more than 12 hours | 12 घंटे से ज़्यादा प्रसव पीड़ा / 12 ಗಂಟೆಗಿಂತ ಹೆಚ್ಚು ಹೆರಿಗೆ ನೋವು | ANC | mother | MCP 2018: 'Labour pain for more than 12 hours' | 2 positive / 0 confirm patterns |
| `NB_POOR_FEEDING` | baby not feeding or sucking weakly | बच्चा दूध नहीं पी रहा या कमज़ोर चूस रहा / ಮಗು ಹಾಲು ಕುಡಿಯುತ್ತಿಲ್ಲ | NEWBORN, IMMUNISATION, PNC | baby | MCP 2018 newborn: 'Is sucking weakly or refuses to breast feed'; GB p.19 | 8 positive / 0 confirm patterns (phrase contains its own negation) |
| `NB_UNABLE_TO_CRY` | baby unable to cry or weak cry | बच्चा रो नहीं पा रहा या कमज़ोर रोना / ಮಗು ಅಳುತ್ತಿಲ್ಲ | NEWBORN | baby | MCP 2018 newborn: 'Is unable to cry or has difficulty in breathing'; GB p.19 | 5 positive / 0 confirm patterns (phrase contains its own negation) |
| `NB_DIFFICULT_BREATHING` | fast or difficult breathing | तेज़ या मुश्किल से सांस लेना / ವೇಗವಾದ ಅಥವಾ ಕಷ್ಟದ ಉಸಿರಾಟ | NEWBORN, IMMUNISATION | baby | MCP 2018 newborn: 'difficulty in breathing'; child: 'rapid and/or difficult breathing'; GB p.19 | 9 positive / 2 confirm patterns |
| `NB_YELLOW_SKIN` | yellow palms, soles, skin or eyes | हथेली, तलवे, त्वचा या आंखें पीली / ಅಂಗೈ, ಅಂಗಾಲು ಅಥವಾ ಚರ್ಮ ಹಳದಿ | NEWBORN | baby | MCP 2018 newborn: 'Has yellow palms and soles'; GB p.19 (yellow skin: refer) | 7 positive / 0 confirm patterns |
| `NB_FEVER_OR_COLD` | fever or cold to touch | बुखार या शरीर ठंडा / ಜ್ವರ ಅಥವಾ ಮೈ ತಣ್ಣಗಿರುವುದು | NEWBORN | baby | MCP 2018 newborn: 'Has fever or is cold to touch'; GB p.19 | 8 positive / 0 confirm patterns |
| `NB_BLOOD_IN_STOOL` | blood in stools | मल में खून / ಮಲದಲ್ಲಿ ರಕ್ತ | NEWBORN, IMMUNISATION | baby | MCP 2018 newborn: 'Has blood in stools or convulsions'; GB p.19 | 3 positive / 0 confirm patterns |
| `NB_LETHARGIC_UNCONSCIOUS` | baby lethargic or unconscious | बच्चा सुस्त या बेहोश / ಮಗು ಜಡವಾಗಿದೆ ಅಥವಾ ಪ್ರಜ್ಞೆ ಇಲ್ಲ | NEWBORN, IMMUNISATION | baby | MCP 2018 newborn: 'Is lethargic or unconscious'; GB p.19 | 8 positive / 0 confirm patterns |
| `CHILD_HIGH_FEVER` | high fever in the child | बच्चे को तेज़ बुखार / ಮಗುವಿಗೆ ತೀವ್ರ ಜ್ವರ | IMMUNISATION | baby | MCP 2018 care during illness: 'If the child has high fever take her/him to the health centre' | 1 positive / 1 confirm patterns |
| `CHILD_DIARRHOEA_NOT_STOPPING` | loose motions not stopping | दस्त बंद नहीं हो रहे / ಭೇದಿ ನಿಲ್ಲುತ್ತಿಲ್ಲ | IMMUNISATION, NEWBORN | baby | MCP 2018 care during illness: 'Take the child to hospital if loose motion do not stop' | 2 positive / 1 confirm patterns (phrase contains its own negation) |

"Escalates immediately" means a positive match triggers the referral at once. In other visit types the same mention becomes **UNCERTAIN** and the agent asks one yes/no question, so a mention is never silently ignored. When the visit type is not yet known, every sign escalates (recall first).

Not implemented, deliberately: pre-term labour (needs gestational age, which is not captured) and any sign not in the sources above.

## 3. Engine pipeline (`backend/app/services/danger_rules.py`)
1. **Match form:** NFC, nukta removed (बुख़ार = बुखार), chandrabindu → anusvara, zero-width joiners removed, native digits → ASCII, Latin lower-case. The original transcript is kept for audit.
2. **Clause split** on punctuation and contrastive conjunctions (lekin, magar, but, ಆದರೆ), not on "aur/and".
3. **Pattern match** (Indic-safe word boundaries) for positive and "needs confirmation" patterns.
4. **Uncertainty markers** in the clause (pata nahi, shayad, maybe, ಗೊತ್ತಿಲ್ಲ, ಇರಬಹುದು) → UNCERTAIN. They are masked first so the "nahi" inside "pata nahi" is not read as a negation.
5. **Past / other person** (pichhli pregnancy, previous, padosi, ಹಿಂದಿನ) → UNCERTAIN, unless followed by "se/since" ("pichhle hafte se bukhar" = ongoing).
6. **Negation window:** up to 3 words before (no, not, without, bina, na) or 5 words after (nahi, नहीं, ಇಲ್ಲ, Kannada verbal negatives ending -ಇಲ್ಲ). The scan stops at a positive copula (hai, है, ide) and treats continuation verbs as positive ("bleeding ruk nahi rahi" = not stopping = still a danger sign). Negation inside the matched phrase also counts ("खून नहीं आ रहा").
7. **Phrases with their own negation** (baby doodh nahi pee raha, ಮಗು ಹಾಲು ಕುಡಿಯುತ್ತಿಲ್ಲ, bachcha ro nahi raha) are positive by definition.
8. **Resolution:** one finding per sign (POSITIVE > UNCERTAIN > NEGATED); an UNCERTAIN finding overlapping a positive one is dropped, and overlapping UNCERTAIN findings are merged, so one mention means at most one question.

## 4. Behaviour in the conversation
- **POSITIVE** → the fixed referral is spoken **immediately** (before the read-back), a red alert shows the matched phrase and rule id, the record gets `referral_status = REFER_NOW`, and an URGENT follow-up is created on save.
- **UNCERTAIN** → "I heard something about <sign>. Is this happening now? Say yes or no." Yes → alert; no → recorded as negated; no clear answer twice → `REVIEW_REQUIRED` plus an ANM-review follow-up.
- **NEGATED** → logged in the audit trail, no alert.
- **Retraction:** if the worker later negates a sign that was already flagged, it becomes "ANM review", never silently cleared.
- **No advice:** requests for medicine, dose or diagnosis get the fixed refusal "I cannot give diagnosis, medicine or dosage advice. Please follow the P H C protocol."

## 5. Fixed referral wording (spoken by Timbre v3.0)
| | Mother | Baby |
|---|---|---|
| en | Danger sign: {signs}. Please refer her to the P H C or nearest hospital now. | Danger sign: {signs}. Please refer the baby to the P H C or nearest hospital now. |
| hi | खतरे का संकेत: {signs}। कृपया उन्हें अभी पी एच सी या नज़दीकी अस्पताल रेफ़र कीजिए। | खतरे का संकेत: {signs}। कृपया बच्चे को अभी पी एच सी या नज़दीकी अस्पताल रेफ़र कीजिए। |
| kn | ಅಪಾಯದ ಲಕ್ಷಣ: {signs}. ದಯವಿಟ್ಟು ಅವರನ್ನು ಈಗಲೇ ಪಿ ಎಚ್ ಸಿ ಅಥವಾ ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಗೆ ರೆಫರ್ ಮಾಡಿ. | ಅಪಾಯದ ಲಕ್ಷಣ: {signs}. ದಯವಿಟ್ಟು ಮಗುವನ್ನು ಈಗಲೇ ಪಿ ಎಚ್ ಸಿ ಅಥವಾ ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಗೆ ರೆಫರ್ ಮಾಡಿ. |

`{signs}` is replaced by the fixed labels from the table in section 2. The MCP card says "nearest appropriate hospital"; the hackathon brief says "refer to the PHC now". The wording names both.

## 6. Test evidence
- `backend/tests/test_danger_rules.py`: 38 positive phrases (hi, kn, en, romanised), 7 negated, 8 uncertain, 6 unrelated texts that must not alarm (for example "khoon ki jaanch", "she is fit", "ASHA ka daura"), multiple signs, no duplicate questions, citations present, and no advice words in labels.
- `evaluation/`: 18 danger utterances. Recall 16/16 and 0 false alerts on this set (see docs/test-results.md). This set was written by the build team, so it is not evidence of real-world clinical safety.
