# Requirements traceability

Sources: **R** = official problem statement / rulebook (authoritative), **P** = ASHA Vaani Complete Build Plan, **M** = master build prompt.

| ID | Requirement | Source | Implementation | Verification |
|---|---|---|---|---|
| T1 | STT must be Gnani Prisma v3.0 | R | `speech/gnani_stt.py`, `config.stt_model` | `test_stt_headers_follow_gnani_v3_docs`; smoke test (live) |
| T2 | TTS must be Gnani Timbre v3.0 | R | `speech/gnani_tts.py` | `test_tts_request_follow_gnani_v3_docs`; `test_full_anc_visit…` asserts every request is timbre-v3.0 |
| T3 | WebSocket streaming only, no telephony | R | browser↔backend WS `/ws/visit/{id}`; backend↔Gnani `wss://` | architecture; no telephony code exists |
| T4 | Hosted agent platforms cannot be the core loop | R | custom orchestration (`session_manager.py`) | code review |
| T5 | No voice cloning | R | stock catalog voice "Chetana" | `config.tts_voice` |
| T6 | Synthetic data only | R | `storage/seed.py` (18 fictional people) | privacy doc |
| T7 | AI disclosure in the first turn, in the user's language | R | `attach()` speaks `disclosure` first; `prompts.json` hi/kn/en | `test_full_anc_visit…` checks the first agent_say is the disclosure |
| T8 | Transcripts encrypted at rest, deleted after judging | R | `storage/crypto.py`, `db.purge_older_than`, delete endpoint/script | `test_encryption_roundtrip…`, `test_idempotent_save_and_deletion` |
| T9 | No diagnosis, treatment or dosage advice; fixed protocols | R | template-only speech; ADVICE intent → `no_advice` | `test_yes_no_undo_repeat_skip_advice`, `test_engine_never_outputs_advice_words` |
| T10 | API key out of the repo, `.env` in `.gitignore` | R | `.gitignore`, `.env.example`, `check_secrets.py` | secret scan |
| F1 | Streaming STT handles code-mix and local health words | R | 2 language codes + `format codemix` + keyterms glossary; Indic-safe parser | `test_language.py`; eval hi-en / kn-en rows |
| F2 | Visit form: beneficiary ID, visit type, weight, vaccinations due, next visit date | R | `extraction.py` (+ `vaccinations_given`, IFA, name, visit_date per P) | `test_extraction_validation.py`; eval |
| F3 | Read the form aloud before saving | R | `readback.readback_text`, `_readback()` | session-flow test; browser E2E |
| F4 | Fix mistakes by voice ("no, weight is 2.8 kilo") | R | `corrections.classify`, `_confirmation_turn` | `test_brief_correction_example_newborn`; E2E |
| F5 | Danger sign → tell her in her language to refer to PHC now, flag record | R | `danger_rules.py`, `_alert()`, `referral_status` | `test_newborn_danger_sign_alert_precedes_readback`; Hindi browser E2E |
| F6 | Follow the list only, no diagnosis | R | fixed list + fixed wording | danger tests |
| F7 | Team danger list from a public guideline, cited in README | R | README §5, `docs/danger-sign-guideline.md` | doc review |
| F8 | Works with household and street noise | R | browser NS/AEC/AGC, adaptive VAD, Prisma VAD headers, read-back + correction | noisy-text eval; live loopback tool (not run) |
| F9 | Follow-up list | R | `services/followups.py` | `test_followups_are_deterministic…` |
| D1 | Working prototype / runnable repo | R | `start.sh`, `start.bat`, `Dockerfile` | uvicorn launch check |
| D2 | README with setup, architecture diagram, Gnani services | R | `README.md`, `docs/images/architecture.png` | — |
| D3 | 2–3 min demo video | R | storyboard `docs/demo-script.md` | **to record live** |
| D4 | Pitch deck ≤ 6 slides | R | `submission/pitch-deck/ASHA_Vaani_Pitch.pptx` | 6 slides |
| P1 | Consent before recording | P | `POST /api/sessions` requires consent; consent screen | `test_api_consent_language…` |
| P2 | Explicit states and transitions | P | `state_machine.py` | all flow tests (invalid transitions reported) |
| P3 | Missing fields asked one at a time | P | `validation.missing_to_ask`, `next_step()` | `test_missing_fields_asked_one_at_a_time_and_skip` |
| P4 | Correction: explicit field first; bare value only with unambiguous last field; else ask | P | `bare_target()` | eval C08/C09 |
| P5 | Undo | P | history stack, `_undo_and_reply` | `test_undo_restores_previous_value` |
| P6 | Save only after explicit yes; idempotent | P | `save()`, idempotency key + UNIQUE | duplicate-confirm test |
| P7 | "Saved" shown only after persistence | P | `saved` event emitted after commit; UI waits for it | failed-save test |
| P8 | Danger alert does not wait for confirmation | P | `_run_danger` before read-back | alert-precedes-readback test |
| P9 | Negation / uncertain / unrelated / multiple / code-mix / LLM cannot add signs | P | engine + merge excludes danger | `test_danger_rules.py`, `test_llm_merge_requires_grounding` |
| P10 | 16 kHz s16le mono, 512-sample frames, bounded queues | P | worklet, `Rechunker`, `PrismaSTTStream` (250-frame queue, drop-oldest) | frontend + adapter tests; E2E frame sizes |
| P11 | Barge-in: stop playback, cancel TTS, treat speech as a possible correction | P | client VAD + pre-roll, `cancel_speech`, awaiting context kept | browser barge-in E2E |
| P12 | Latency instrumentation, median/p95 | P | `metrics` table, `/api/metrics`, Settings | E2E metrics output |
| P13 | Four-layer recovery | P | backoff, credential manager, pending drafts, demo mode | recovery tests |
| P14 | Light-theme tokens, 360 px, bottom nav, large targets | P | `styles.css` | screenshots |
| P15 | Screens: dashboard, consent, capture, review, correction, alert, summary, history, follow-ups, settings | P/M | `frontend/src/pages/*` | screenshots |
| P16 | CORS restricted, payload limits, session-scoped access, no secret logging | P | `main.py` middleware, tokens | `test_api_consent_language_cors_limits_headers`, `test_credential_manager_never_exposes_keys` |
| P17 | Evaluation set of 40–60+ utterances with expected outputs | P/M | `evaluation/` (65) | `run_eval.py` |
| M1 | Grounded LLM extraction with non-LLM fallback | M | `llm_gemini.py` + `merge()` | merge tests |
| M2 | Secondary key only if organiser-authorised | M | `CredentialManager` | `test_secondary_key_only_used_when_authorised` |
| M3 | Clearly labelled demo fallback | M | `mode=demo` banner, `source=demo` | `test_demo_mode_is_labelled…` |

## Product redesign (v2): requirement → implementation → verification

| Requirement | Where | Verified by |
|---|---|---|
| Light theme: ivory, forest, sage, charcoal, warm grey; terracotta only for urgent; amber only for pending/uncertain; Lucide-style icons; editorial headings | `frontend/public/styles.css` (tokens at the top), `frontend/src/ui/icons.ts` | Screenshot review at 4 widths (test-results §3b) |
| Landing page at `/` with header, mobile nav, hero, value strip, how it works, features, impact without invented statistics, final CTA, footer with privacy, prototype and hackathon notices; Get started opens the app (no fake login) | `pages/landing.ts` | Route sweep; onboarding E2E starts from the hero button |
| Onboarding (4 screens), English default, en/hi/kn only, mic and speaker check, workflow, persisted, not repeated | `pages/onboarding.ts`, `store.ts` (`prefs`), `i18n.ts` | `onb.mjs`: redirect on first run, English preselected, mic level detected, returning user skips |
| App shell: desktop sidebar + top bar, mobile header + bottom nav + More sheet; 8 nav items, none dead | `components/shell.ts`, `main.ts`, `router.ts` | Route sweep: 12 routes × 4 widths, no overflow or console errors |
| Overview from the database: greeting with name, date, service status, 4 counts, Start new visit, recent activity, upcoming follow-ups, quick actions, daily summary, empty states | `pages/overview.ts`, `GET /api/dashboard` | `test_demo_data_api.py` (counts), screenshots |
| Voice workspace: two columns, 13 display states, real-mic waveform, live transcript, record preview with evidence and confidence, missing info, connection status, barge-in, replay, retry mic, reconnect, keep draft, two-tap cancel, resume, per-field Correct, explicit confirm, summary only after `saved` | `pages/workspace.ts`, `services/visitSocket.ts` (`retry()`) | `e2e_v2.mjs` main/danger/demo at 390 and 1280 px; 175 backend tests incl. the full WebSocket flows |
| Beneficiaries directory (search, category, recent activity) and profile (history, follow-ups, referrals, latest record, timeline, status badges) | `pages/beneficiaries.ts`, `GET /api/beneficiaries[/{id}]` | `test_demo_data_api.py`, route sweep |
| Visit records: search, type/date/status/referral filters, newest first, Draft and Pending sync kept apart from Confirmed, detail with corrections and confirmation history, CSV export, print to PDF | `pages/visits.ts`, `GET /api/visits`, `GET /api/visits/export.csv` | Demo E2E (draft listed, resume, cancel, history lists the correction); CSV test |
| Follow-ups: Overdue, Due today, Upcoming, Completed; mark completed, reopen, links to beneficiary and visit; deterministic rules only | `pages/followups.ts`, `services/followups.py` (unchanged rules) | Route sweep; existing follow-up rule tests |
| Referral centre: sign, matched rule, heard phrase, guideline reference, open/completed; same danger engine | `pages/referrals.ts`, `GET /api/referrals` | `test_demo_data_api.py`; danger E2E shows the alert and the referral appears |
| Reports from the database with date ranges, demo notice and a table view for each chart | `pages/reports.ts`, `components/charts.ts`, `GET /api/reports` | `test_demo_data_api.py` (range validation, counts), screenshots |
| Settings: UI language separate from speaking language, name, mic test, Timbre speaker test, barge-in, service status, latency, AI disclosure, data handling, retention, reload or delete data, show onboarding again | `pages/settings.ts` | Route sweep; fixed: speaker test enabled from the server answer |
| Synthetic dataset: 20 beneficiaries, 9 ANC / 5 PNC / 5 newborn / 5 immunisation visits, follow-ups, referrals; idempotent; reset command; labelled DEMO DATA; never mixed with recorded visits | `storage/seed.py`, `storage/demo_seed.py`, `scripts/setup/seed_demo_data.py` | `test_demo_data_api.py`; CLI run (24 → 0 → reset 24) |
| Responsive 360/390/tablet/desktop, accessible names, skeletons, error and empty states | all pages | Route sweep in English, Hindi and Kannada |
