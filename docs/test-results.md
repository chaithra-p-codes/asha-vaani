# Test results

Build environment: Linux, Python 3.13, Node 22, headless Chrome 153 (Playwright), 11 Nov 2026. **No Gnani API key and no outbound network to api.vachana.ai were available**, so every "live" behaviour below was exercised against protocol-faithful fakes of Prisma v3.0 and Timbre v3.0 (`backend/tests/fakes.py`) that implement the documented message formats. Real Gnani accuracy and latency still have to be measured with a key (section 6).

## 1. Backend automated tests: 175 passed

```
cd backend && python -m pytest tests -q
175 passed in 10.7s
```
| File | Tests | Covers |
|---|---|---|
| `test_session_flow.py` | 13 | Full WebSocket visits through the real handler, state machine, adapters, rules and encrypted DB: disclosure first; dictation → read-back → voice correction (only weight changes) → yes → save; duplicate confirmation creates no second record; newborn danger alert spoken **before** the read-back; negated sign not flagged; uncertain sign → question → alert on "haan"; missing fields asked one at a time, with skip; undo; Timbre failure reported as `tts_unavailable` and the flow continues; quota exhaustion → recovery, never fake success; secondary key unused unless authorised; wrong token rejected (4401); resume after simulated backend restart re-asks for confirmation; demo mode labelled and never calls Gnani; typed text rejected in live mode; failed DB save stays PENDING, then retry saves exactly once |
| `test_danger_rules.py` | 63 | 38 positive phrases (hi/kn/en/romanised), 7 negated, 8 uncertain, 6 unrelated texts that must not alarm, multiple signs, no double questions, citations, no advice words |
| `test_language.py` | 61 | spoken numbers (Hindi 0–100, Kannada sandhi, English, decimals, fractions, native digits), digit-by-digit IDs, 21 date forms, Unicode normalisation, Indic-safe tokenizer |
| `test_extraction_validation.py` | 22 | brief example, Hindi and Kannada notes, given vs due vaccines, grams → kg, negated IFA, ambiguous names, name/ID mismatch, unknown ID, weight ranges, date order, LLM grounding (ungrounded values discarded), correction intents, yes/no/undo/advice, ID self-correction, dose number words |
| `test_demo_data_api.py` | 3 | Synthetic seed: 24 visits, idempotent re-run, `--reset` removes only seeded rows, retention never purges seeds; seeded records never sort above a visit recorded now; dashboard counts; beneficiary list, profile and timeline; referrals open/closed; reports by day and type with range validation; follow-up listing; CSV export with the DEMO DATA source label |
| `test_adapters_storage_api.py` | 13 | Prisma headers per docs, Timbre request per docs, 1024-byte framing, commit, transcript parsing; TTS decode, cache saves credits, quota → key marked exhausted; cancel drops the socket; keys never exposed; AES-GCM tamper detection; idempotent save; follow-ups never invent dates; consent required; CORS; 413 on large bodies; security headers; refusal without a Gnani key; TTS diagnostic WAV |

## 2. Frontend automated tests: 6 passed
`cd frontend && npm test` (tsc strict build, then `node --test`): AudioWorklet resampler produces exact 1,024-byte / 512-sample 16 kHz frames from 48 kHz and 44.1 kHz stereo input with frequency preserved; client VAD and pre-roll ring buffer; PCM16 decode with the 5-byte frame header; every UI string present in hi/kn/en; HTML escaping of transcripts.

## 3. Browser integration test (headless Chrome, real PWA, fake Gnani)
Chrome ran with a **synthetic WAV as the fake microphone** (tone/harmonic bursts, no human voice) at a 360 × 760 viewport. The real backend ran behind a minimal WebSocket ASGI server used only in the sandbox (production uses uvicorn). Prisma transcripts were scripted.

| Scenario | Result |
|---|---|
| Home → consent → live visit → AI disclosure spoken and played | PASS |
| Mic → AudioWorklet → WebSocket: **513 frames, all exactly 1,024 bytes** | PASS |
| Auto-listen after the agent finishes, endpointing, transcript → draft (ID 1024, ANC, 52 kg, TT, IFA, 20 Nov) | PASS |
| Read-back played → correction "No, weight is 54 kilos" → only weight changed | PASS |
| "yes that is correct" → saved (server timestamp) → follow-up NEXT_VISIT → history, follow-ups, settings, dashboard updated | PASS |
| Newborn note (Hindi UI) "तेज़ बुखार … दूध नहीं पी रहा" → alert spoken immediately with NB_FEVER_OR_COLD + NB_POOR_FEEDING, REFER_NOW | PASS |
| **Barge-in:** synthetic speech during the disclosure → playback stopped → `tts_cancel` → listening (reason `barge_in`) | PASS |
| Browser console errors / page errors | none |
| Real uvicorn launch (`uvicorn app.main:app`): API, PWA, worklet, service worker served; live session refused honestly without a key | PASS (HTTP only; the sandbox lacked uvicorn's websocket extra) |

**Sandbox latency (fake Gnani, so NOT representative of live performance):** client end of speech → first agent audio median 819 ms / p95 1,339 ms (n=3). This is dominated by the endpoint silence window (median 720 ms). Pipeline overhead from turn end to first audio sent: median 21 ms. Real Prisma and Timbre network latency comes on top; measure it live (Settings → measured latency).

## 3b. Redesigned product: browser tests (headless Chrome, real PWA, fake Gnani)

Same set-up as section 3, with the redesigned app (history routes, app shell, voice workspace). Assertions are made on the rendered page, not only on socket events. Scripts are in the build sandbox (`/home/claude/tools/e2e_v2.mjs`, `sweep.mjs`, `onb.mjs`) and are not shipped.

| Scenario | Result |
|---|---|
| Route sweep: 12 routes (landing, onboarding, overview, new visit, beneficiaries, profile, visit records, record detail, follow-ups, referrals, reports, settings) × 360, 390, 768, 1280 px: no horizontal overflow, no console errors, no failed requests | PASS (48/48) |
| Same sweep with the UI in Hindi (360, 1280 px) and Kannada (360, 768 px) | PASS |
| First run: Get started → onboarding (English preselected, mic level detected, name stored) → Enter dashboard → greeting uses the name; a returning user goes straight to the app; old `#/visits` link maps to `/app/visits` | PASS |
| Live visit at 390 px and 1280 px: "Live connection" badge, state "Listening" while streaming, Prisma transcript shown, read-back, spoken correction to 54 kg, spoken "yes" → summary only after the server's `saved` event; **515 mic frames, all 1,024 bytes**; record detail says "Live visit" and "Voice"; the new record is first in Visit records and is not labelled demo | PASS |
| Danger sign (newborn fever + not feeding; pregnancy bleeding): danger panel rendered with `role="alert"`, rule ID and heard phrase | PASS |
| Demo mode: demo badge, mic disabled, field "Correct" button shows what to say, typed demo correction updates only the weight and marks it Corrected, no `saved` event before explicit confirmation, record detail shows source "Demo session", confirmation method and the correction in its history | PASS |
| Keep draft and leave → draft listed separately as "Draft" in Visit records → Resume restores the record from the server → two-tap Cancel → no local draft remains | PASS |

Bugs found and fixed by these runs: seeded "today" records sorted above a just-recorded live visit (seed timestamps were later than now; fixed and covered by a backend test); Settings disabled the Timbre speaker test on a direct page load until refresh; landing sections were misaligned and the floating cards hid the phone's mic; report panels had no inner padding; cramped draft row on phones.

## 4. Offline evaluation: 65 scripted utterances (`evaluation/`)

| Metric | First run | Final | Target |
|---|---|---|---|
| Field accuracy, clean | 100/101 (99.0%) | 101/101 (100%) | ≥ 90% |
| Field accuracy, noisy **text** | 25/26 (96.2%) | 26/26 (100%) | ≥ 80% |
| Number accuracy (ID, weight, next date) | 71/72 | 72/72 | above field accuracy |
| Invented (unstated) fields | 0 | 0 | 0 |
| Correction success | 10/10 | 10/10 | ≥ 95% |
| Danger-sign recall | 16/16 | 16/16 | 100% |
| False danger alerts | 0 | 0 | about 0 |

The two first-run failures (a mid-sentence ID self-correction "…उनसठ नहीं, एक शून्य नौ शून्य" and a dose spoken as a number word "penta teen") were fixed as general features, with regression tests added.

**How to read these numbers:** the set was written by the build team at the same time as the rules, so 100% shows the rules do what they were designed to do. It does **not** show accuracy on new speakers or real ASR errors. Before judging, add 20+ held-out utterances written by someone who did not write the rules, and run the live loopback (section 6).

## 5. Static checks
- `python -m compileall backend evaluation scripts`: OK
- `python scripts/verification/check_secrets.py`: OK (no keys, `.env` files or databases)
- TypeScript `strict` with `noUnusedLocals`: 0 errors

## 6. Not tested in the build environment (needs your key / device)
| Item | How to test |
|---|---|
| Real Prisma v3.0 transcription (hi/kn code-mix, names, numbers) | `python scripts/verification/gnani_smoke_test.py --lang hi` (and `kn`, `en`) |
| Real Timbre v3.0 audio quality, voice "Chetana", 24 kHz raw PCM | smoke test output WAV; Settings → Play test phrase |
| Live end-to-end latency (median/p95) | run 10+ visits, then Settings → measured latency or `GET /api/metrics` |
| Acoustic noise robustness | `python evaluation/run_eval.py --live-loopback --limit 10 --noise-snr 10`, then real noise with a person |
| Barge-in on a real Android phone speaker (echo) | rehearse; use earphones or turn off barge-in if echo triggers it |
| Gemini extraction path | set `GEMINI_API_KEY`; the merge and grounding logic is unit-tested, the HTTP call is not |
| Docker image, hosted HTTPS deployment | `docker build .` then deploy |
| Low-end Android performance | test on the actual phone |
