# Submission checklist (Gnani Voice Hackathon 2026, PS1)

## Before the deadline
- [ ] Put the event Gnani key in `backend/.env` → run `python scripts/verification/gnani_smoke_test.py --lang hi` (and `kn`) → **Gate 1 must pass**
- [ ] Check Prisma `codemix` output on real speech; if numbers come back oddly, try `GNANI_STT_FORMAT=transcribe`
- [ ] Deploy over HTTPS (tunnel or Docker host) and open it on the actual Android phone
- [ ] Run 10+ live visits (with noise) → record real median/p95 from Settings; put them in the deck (slide 5), replacing "measure live"
- [ ] Optional: `python evaluation/run_eval.py --live-loopback --limit 10 --noise-snr 10`
- [ ] Ask organisers about multiple keys before setting `GNANI_SECONDARY_AUTHORISED=true`
- [ ] Confirm the MCP card / Guidebook page numbers against the PDFs (docs/danger-sign-guideline.md §1)
- [ ] Record the 2–3 min demo video from a **real live session** (storyboard: docs/demo-script.md §A) → `submission/demo-video/`
- [ ] Create a public GitHub repo; run `python scripts/verification/check_secrets.py`; push (never `backend/.env` or `backend/data/`)
- [ ] Add the repo URL and hosted link to the deck's last slide and the README header

## Deliverables mapping
| Required deliverable | Location | Status |
|---|---|---|
| Working prototype (hosted link or runnable repo) | whole repo; `start.sh` / `start.bat` / `Dockerfile` | runnable; hosting pending |
| Public GitHub repo with README (setup, architecture diagram, Gnani services) | `README.md`, `docs/images/architecture.png` | ready to push |
| Demo video 2–3 min, live session start to finish | `submission/demo-video/` | storyboard ready; **recording pending** |
| Pitch deck ≤ 6 slides | `submission/pitch-deck/ASHA_Vaani_Pitch.pptx` | ready (add live latency) |
| Live demo with a judge | `docs/demo-script.md` §B–C | rehearse |
| Danger-sign guideline cited in README | README §5 | done |

## After judging
- [ ] `python scripts/setup/delete_demo_data.py --yes`, delete `backend/data/`, rotate keys if anything was public
