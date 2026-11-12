# Privacy and data policy (prototype)

ASHA Vaani is a hackathon prototype. It must be used **only with synthetic beneficiaries and synthetic or consented test voices**. Anything collected during demos falls under India's Digital Personal Data Protection Act, 2023 (DPDP).

## What is collected, where, and for how long

| Data | Where | Protection | Retention |
|---|---|---|---|
| Microphone audio | streamed browser → backend → Gnani Prisma | TLS in transit when deployed over HTTPS | **not stored** by ASHA Vaani (transient frames only) |
| Transcripts | inside the visit record and the session draft | AES-256-GCM, key in `ASHA_DATA_KEY` (outside the DB) | 72 h (`RETENTION_HOURS`), then auto-purged |
| Visit record (ID, name, weight, vaccines, dates, danger flags) | SQLite `visits.payload_enc` | AES-256-GCM | 72 h |
| Follow-up text | `followups.payload_enc` | AES-256-GCM | 72 h |
| Session draft | `sessions.draft_enc`; browser IndexedDB when offline | AES-256-GCM / WebCrypto AES-GCM with a non-extractable key | session TTL 2 h / until resumed or deleted |
| Audit events, latency metrics, usage estimates | plaintext tables | contain no personal data (codes, ms, aliases) | 72 h |
| Cached TTS audio | `backend/data/tts_cache` | fixed prompts only (no beneficiary data) | until deletion |

## Principles applied
- **Consent before processing:** the session API rejects requests without `consent: true`, and the worker ticks the consent box after reading the AI disclosure and privacy notice.
- **AI disclosure:** the first spoken turn states that ASHA Vaani is an AI assistant.
- **Minimisation:** only the fields of the visit form are extracted; raw audio is never written to disk.
- **Purpose limitation:** data is used only to create the visit record and follow-ups.
- **Session-scoped access:** each visit has a random token (only its hash is stored) required for the WebSocket and session APIs.
- **Secrets:** API keys exist only in `backend/.env` or host environment variables, are never sent to the browser, and never appear in logs, API responses or the usage table (aliases only).
- **Transport and browser hardening:** restricted CORS, CSP and security headers, 32 KB HTTP and 64 KB WebSocket message limits, Pydantic validation of every client event.

## Deletion after judging
Run any one of:
```bash
python scripts/setup/delete_demo_data.py --yes
curl -X POST http://localhost:8000/api/demo-data/delete -H "Content-Type: application/json" -d '{"confirm":"DELETE"}'
```
or Settings → "Delete all demo data" in the app (also clears the phone's pending draft). Then delete `backend/data/` and rotate `ASHA_DATA_KEY` and the Gnani key if the deployment was public.

## Third parties
- **Gnani (Vachana) API Platform** receives the audio stream (Prisma) and the agent's sentences (Timbre).
- **Google Gemini** (only if `GEMINI_API_KEY` is set) receives the transcript text of dictation turns for extraction. Leave the key empty to keep transcripts within Gnani and the backend.

## Not production-ready
No user authentication, no key management service, no formal DPIA, and no clinical validation. Real patient data must not be entered.
