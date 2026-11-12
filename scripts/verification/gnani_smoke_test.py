#!/usr/bin/env python3
"""GATE 1 (build plan, hour 0-3): prove a real Prisma v3.0 + Timbre v3.0 round trip.

  1. Timbre v3.0 synthesises a fixed synthetic test sentence (no voice cloning)
     -> saved as scripts/verification/out_timbre.wav (listen to it!)
  2. The same audio (16 kHz) is streamed to Prisma v3.0 in real-time 1024-byte frames
  3. Prints what Prisma heard and the measured latencies.

Costs a small number of Gnani credits. Needs GNANI_API_KEY in backend/.env.
    python scripts/verification/gnani_smoke_test.py --lang hi
"""
import argparse
import asyncio
import contextlib
import os
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
os.environ["ASHA_NO_AUTOAPP"] = "1"
from app.config import get_settings  # noqa: E402
from app.services.credential_manager import CredentialManager  # noqa: E402
from app.services.normalise import keyterms_for  # noqa: E402
from app.speech.audio_utils import wav_bytes  # noqa: E402
from app.speech.gnani_stt import PrismaSTTStream  # noqa: E402
from app.speech.gnani_tts import TimbreTTSClient  # noqa: E402

SENTENCES = {
    "hi": "एएनसी चेकअप, लाभार्थी आईडी एक शून्य दो चार, वज़न बावन किलो, टीटी इंजेक्शन लगा, अगली विज़िट बीस नवंबर",
    "kn": "ಎಎನ್‌ಸಿ ಭೇಟಿ, ಫಲಾನುಭವಿ ಐಡಿ ಒಂದು ಸೊನ್ನೆ ಸೊನ್ನೆ ಏಳು, ತೂಕ ಐವತ್ತೆರಡು ಕೆಜಿ",
    "en": "ANC checkup for beneficiary one zero two four, weight fifty two kilos, next visit twenty November",
}


async def main(lang: str):
    s = get_settings()
    cm = CredentialManager(s)
    if not cm.configured:
        sys.exit("GNANI_API_KEY is empty in backend/.env")
    s.tts_sample_rate = 16000
    print(f"models: STT={s.stt_model} ({s.stt_format})  TTS={s.tts_model} voice={s.tts_voice}")
    tts = TimbreTTSClient(settings=s, credentials=cm)
    pcm = bytearray()
    t0 = time.monotonic()
    async with contextlib.aclosing(tts.synthesize(SENTENCES[lang], lang)) as gen:
        async for chunk in gen:
            pcm.extend(chunk)
    await tts.drop()
    print(f"[Timbre] first chunk {tts.last_first_chunk_ms:.0f} ms, total {1000*(time.monotonic()-t0):.0f} ms, "
          f"{len(pcm)/32000:.1f} s audio")
    out = Path(__file__).with_name("out_timbre.wav")
    out.write_bytes(wav_bytes(bytes(pcm), 16000))
    print(f"[Timbre] saved {out}")

    events = []

    async def on_event(e):
        events.append((time.monotonic(), e))
        if e["type"] in ("transcript", "error", "speech_start", "processing"):
            print(f"[Prisma] {e['type']}: {e.get('text', e.get('message', ''))}")

    st = PrismaSTTStream(settings=s, credentials=cm, language=lang, keyterms=keyterms_for(lang),
                         on_event=on_event, request_id="smoke-test")
    t1 = time.monotonic()
    await st.open()
    print(f"[Prisma] connected in {st.open_latency_ms:.0f} ms; config {st.connected_info.get('config')}")
    audio = bytes(pcm) + bytes(32000)
    for i in range(0, len(audio), 1024):
        st.push_audio(audio[i:i + 1024])
        await asyncio.sleep(0.032)
    t_end = time.monotonic()
    await st.commit()
    await asyncio.sleep(2.0)
    await st.close()
    finals = [(t, e) for t, e in events if e["type"] == "transcript" and e.get("text")]
    if finals:
        print(f"\nRESULT: Prisma heard -> {' '.join(e['text'] for _, e in finals)}")
        print(f"last transcript arrived {1000*(finals[-1][0]-t_end):.0f} ms after audio end (incl. 1 s padding)")
        print("GATE 1 PASSED: real Timbre -> Prisma round trip works.")
    else:
        print("\nNo transcript received. Check key, model names, language and network.")
    _ = t1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="hi", choices=["hi", "kn", "en"])
    asyncio.run(main(ap.parse_args().lang))
