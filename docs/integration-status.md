# Integration status and release acceptance checklist

Legend: **PASS** = verified with evidence in this build · **FAIL** · **BLOCKED** = cannot be verified without something the build environment lacked (Gnani key or network, a real phone) · **NOT TESTED**.

| # | Item | Status | Evidence / remaining action |
|---|---|---|---|
| 1 | Required models configured (`prisma-v3.0`, `timbre-v3.0`) | PASS | `config.py` defaults; `test_stt_headers_follow_gnani_v3_docs`, `test_tts_request_follow_gnani_v3_docs`; `/api/config` |
| 2 | WebSocket protocol verified against current docs | PASS (docs) / BLOCKED (live) | Endpoints, headers, frames, commit, events, base64 audio, voices checked on docs.gnani.ai (Nov 2026). Live handshake not run: run `gnani_smoke_test.py` |
| 3 | Microphone input supported | PASS | Headless Chrome fake mic → AudioWorklet → 513 × 1,024-byte frames; frontend resampler tests |
| 4 | Real Gnani STT tested | BLOCKED | No key or network in build. Action: smoke test (Gate 1) |
| 5 | Real Gnani TTS tested | BLOCKED | Same. Action: smoke test plus Settings playback test |
| 6 | End-to-end audio loop tested | PASS with fakes / BLOCKED live | Browser E2E with protocol fakes passed; live loop pending a key |
| 7 | Code-mix tested | PASS (text) / BLOCKED (audio) | 26 hi/kn/romanised mixed rows in the eval plus unit tests; live Prisma code-mix not run |
| 8 | Names and numbers tested | PASS (text) | 72/72 number fields; register name matching and ambiguity tests |
| 9 | Background noise tested | PASS (text simulation) / NOT TESTED (acoustic) | 6 noisy-text rows; acoustic: `run_eval.py --live-loopback --noise-snr 10` |
| 10 | Structured extraction tested | PASS | 31/31 extraction cases; 0 invented fields |
| 11 | Voice correction tested | PASS | 10/10 eval; session-flow correction and undo tests; browser E2E correction |
| 12 | Danger-sign source verified | PASS (citation) | MCP Card 2018 + Guidebook 2018 (MoHFW/MoWCD) URLs and sections; confirm printed page numbers before submission |
| 13 | Danger-sign rules tested | PASS | 63 unit tests; 16/16 recall, 0 false alerts in eval; browser E2E alert (en + hi) |
| 14 | Negation handling tested | PASS | negated and "not stopping" cases (hi, kn, en) |
| 15 | Save confirmation tested | PASS | Save only on YES or confirm button; "sahi nahi hai" → NO; REST confirm requires the read-back state |
| 16 | Duplicate saves prevented | PASS | idempotency key + UNIQUE constraint; duplicate confirm test |
| 17 | Follow-ups generated | PASS | rules R1–R6 tests; E2E summary |
| 18 | Encrypted persistence tested | PASS | AES-GCM round trip + tamper test; ciphertext has no plaintext names |
| 19 | Recovery tested | PASS (sandbox) | quota → recovery; TTS failure; restart → resume with re-confirmation; save failure → PENDING → retry; WS backoff implemented (browser reconnect not separately scripted) |
| 20 | UI build successful | PASS | `tsc` strict, 0 errors; dist about 210 KB |
| 21 | Mobile layout verified | PASS (emulated) / NOT TESTED (device) | 360 × 760 Chrome screenshots of all screens; test on the real phone |
| 22 | Automated tests passed | PASS | 175 backend + 6 frontend + redesigned-UI browser tests (docs/test-results.md §3b) |
| 23 | Documentation complete | PASS | README, architecture, guideline, privacy, demo script, traceability, test results, this file |
| 24 | ZIP generated and verified | PASS | See final packaging step: extracted, secret-scanned, tests re-run from the extracted copy |
| 25 | Demo video | NOT DONE | Must be recorded from a real live session (storyboard in `docs/demo-script.md`) |
| 26 | Team credit/key policy confirmed with organisers | NOT DONE | Ask before setting `GNANI_SECONDARY_AUTHORISED=true` |
| 27 | Public GitHub repository | NOT DONE | Create the repo and push (see `submission/submission-checklist.md`) |
