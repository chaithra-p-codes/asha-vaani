# Demo script, video storyboard and judge-test playbook

## A. 2:45 demo video (record from a real live session; never fake it)

**Setup:** Android phone on the HTTPS URL (README §8), screen recorder on, a second phone playing low household/street noise about 1 m away. Synthetic beneficiary 1024 (Sunita Devi). A colleague's voice or your own (consented). Do **not** use prerecorded audio as if it were live.

| Time | Shot | Narration (voice-over) | On screen |
|---|---|---|---|
| 0:00–0:15 | ASHA worker outside a house, phone in hand (or title card) | "Every visit an ASHA worker makes ends with typing on a small screen. ASHA Vaani lets her just say it." | Title: ASHA Vaani · voice field register |
| 0:15–0:30 | Overview (her day: visits, follow-ups, one urgent referral) → New visit → speaking language + consent | "She picks Hindi, reads the AI notice, and gives consent." | New visit start panel, Hindi selected, consent ticked |
| 0:30–0:42 | Voice workspace, agent speaking | (let the app speak) "Namaste, main Asha Vaani hoon, ek AI sahayak…" | "Live connection" badge; state "Speaking"; caption |
| 0:42–1:05 | Worker dictates with background noise | Worker: *"Sunita Devi, ID ek shunya do chaar, ANC checkup, vajan baavan kilo, TT ka injection laga, IFA goli di, agli visit bees November."* | Live transcript fills in; record rows show "Heard" and the phrase each field was heard as |
| 1:05–1:25 | Read-back | (agent reads the form back with numbers spelled out) | Step strip on Review; caption + structured record |
| 1:25–1:40 | Voice correction | Worker: *"Nahi, vajan chauvan kilo hai."* Agent: "Badal diya. Vazan chauvan kilo…" | Only the Weight row highlights "Corrected"; Undo enabled |
| 1:40–1:52 | Confirm | Worker: *"Haan, sahi hai."* | "Visit saved" with server time; follow-ups created; View record shows the correction in its history |
| 1:52–2:20 | Second visit: danger sign | Worker: *"Newborn visit, ID 1042, bachche ko tez bukhar hai aur doodh nahi pee raha."* Agent immediately: "Khatre ka sanket… kripya bachche ko abhi PHC refer kijiye." | Danger panel with rule ID + heard phrase; "Not a diagnosis"; it appears in Referrals |
| 2:20–2:35 | Referrals → Follow-ups → Settings latency | "Referrals and follow-ups come from what she confirmed, by fixed rules. Latency is measured live, end of speech to first audio." | Referral centre; Follow-ups (Due today); Settings latency table |
| 2:35–2:45 | Closing | "Speak once, confirm by voice, refer on time. Built on Gnani Prisma and Timbre v3.0. Synthetic data only." | Logo + repo URL |

Recording tips: put the phone in Do Not Disturb, keep it 15–25 cm from the mouth, use earphones if the speaker's echo triggers barge-in, and record two takes.

## B. Live judge test (30 points): what to say and do

1. Open the app on the phone over HTTPS **before** judging; run Settings → "Play test phrase" once (this warms the Timbre cache and checks the key).
2. Finish onboarding on the judging phone beforehand. Hand the phone to the judge on New visit with their speaking language chosen and consent ticked. Say: "Tap Start live visit, wait for it to finish introducing itself, then dictate any visit for beneficiary 1024, 1042, 1050 or 1081." To fix a field they can also tap Correct next to it and speak.
3. Suggested judge prompts (all synthetic):
   - *"ANC visit, beneficiary ten twenty-four, weight fifty-two point five kilo, TT two given, IFA goli di, next visit next Monday."*
   - *"ಫಲಾನುಭವಿ 1007, ಪಿಎನ್‌ಸಿ ಭೇಟಿ, ತೂಕ ಐವತ್ತಾರು ಕೆಜಿ, ಮುಂದಿನ ಭೇಟಿ ನಾಳೆ."*
   - Correction: *"No, weight is 54"* · *"ID galat hai, 1050 hai"* · *"undo"*.
   - Danger: *"Pregnant hai, bleeding ho rahi hai"* (immediate alert) vs *"bleeding nahi hai"* (no alert) vs *"bukhar hai"* (asks "is it high fever?").
   - Guardrail: *"Bukhar ke liye kaunsi dawai du?"* → fixed refusal, no advice.
4. If a number is misheard, show the strength: correct it by voice and point to the "Please confirm" chips.
5. If live speech fails: the state turns "Offline, draft kept" and the badge says "Not connected", which is honest. Say so and tap Reconnect; if it cannot be restored, start the labelled demo mode and say clearly that it is the demo fallback.

## C. Rehearsal checklist (T-60 min)
- [ ] `python scripts/verification/gnani_smoke_test.py --lang hi` passes with the event key
- [ ] Phone opens the HTTPS URL; mic permission granted; Settings → playback test plays
- [ ] One full ANC visit, one correction, one undo, one danger alert, one negated sign, rehearsed with noise playing
- [ ] Someone unfamiliar with the app completes a visit without help
- [ ] Latency table in Settings has real numbers; note median and p95 for the pitch (do not quote sandbox numbers)
- [ ] Hotspot ready as a backup network; laptop charger; phone at 100%
- [ ] Demo data deleted after judging (`scripts/setup/delete_demo_data.py --yes`)
