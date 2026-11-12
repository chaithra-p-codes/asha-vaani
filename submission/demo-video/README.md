# Demo video (2–3 minutes): still to be recorded

**Status: not yet recorded.** The hackathon requires a video of a *live voice session start to finish*. It could not be recorded during the build because there was no Gnani API key or phone. Do not substitute the storyboard frames or a demo-mode recording for it.

## How to record (about 20 minutes)
1. Configure `GNANI_API_KEY`, pass `python scripts/verification/gnani_smoke_test.py --lang hi`.
2. Open the app on the Android phone over HTTPS (README §7). Start Android's screen recorder with **device audio + microphone** so the agent's Timbre voice is captured.
3. Follow the shot list in [`docs/demo-script.md`](../../docs/demo-script.md) §A (ANC visit with noise → read-back → voice correction → "haan" → saved and next actions → newborn danger-sign visit → Settings latency).
4. Trim to 2:30–3:00 and add the narration from the script as captions or voice-over. Export as `ASHA_Vaani_demo.mp4` in this folder.
5. If anything fails on camera, re-take it; never splice demo-mode output in as live.

`storyboard-frames/` holds reference screenshots from the automated browser test (Gnani simulated). They are for layout reference only, not the deliverable.
