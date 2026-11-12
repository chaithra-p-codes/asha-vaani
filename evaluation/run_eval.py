#!/usr/bin/env python3
"""ASHA Vaani evaluation runner.

Default (offline, no credentials, no credits): scores the language-understanding layer on
`utterances.csv` (transcript TEXT -> extraction / correction intents / danger rules). The
"noisy" rows simulate ASR noise in TEXT (fillers, repeats, background words); they are NOT
acoustic noise tests.

Optional live mode (spends Gnani credits, needs GNANI_API_KEY in backend/.env):
    python evaluation/run_eval.py --live-loopback --limit 10 [--noise-snr 10]
synthesises each utterance with Timbre v3.0 (synthetic voice, no cloning), optionally mixes
synthetic street-like noise at the given SNR, streams it to Prisma v3.0 and scores the
pipeline on what Prisma returned. This measures STT + NLU on a synthetic voice only; it is
not a substitute for testing with real (consented) speakers.

Outputs: evaluation/results.json and evaluation/results.md
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
os.environ.setdefault("ASHA_NO_AUTOAPP", "1")

from app.services.corrections import bare_target, classify  # noqa: E402
from app.services.danger_rules import evaluate  # noqa: E402
from app.services.extraction import RuleExtractor  # noqa: E402
from app.storage.seed import SYNTHETIC_BENEFICIARIES  # noqa: E402

TODAY = date(2026, 11, 11)  # fixed so relative dates are reproducible
RX = RuleExtractor(SYNTHETIC_BENEFICIARIES)


def _eq(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-6
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def score_extract(text, exp):
    ex = RX.extract(text, TODAY)
    got = {k: v.value for k, v in ex.fields.items()}
    fields = {k: v for k, v in exp.items() if not k.startswith("_")}
    correct = [k for k, v in fields.items() if _eq(got.get(k), v)]
    wrong = {k: {"expected": v, "got": got.get(k)} for k, v in fields.items() if not _eq(got.get(k), v)}
    # invented = extracted field that the utterance did not state (register name lookups are allowed)
    invented = [k for k in got if k not in fields and k != "beneficiary_name" and got[k] not in (None, [], "")]
    notes_ok = all(n in ex.notes for n in exp.get("_notes", []))
    return {"n_fields": len(fields), "n_correct": len(correct), "wrong": wrong, "invented": invented,
            "notes_ok": notes_ok, "got": got, "ok": not wrong and not invented and notes_ok}


def score_correct(text, ctx, exp):
    it = classify(text, TODAY, RX)
    ok = it.kind == exp["kind"]
    detail = {"kind": it.kind}
    if ok and exp["kind"] == "PATCH" and "field" in exp:
        fv = it.patch.get(exp["field"])
        ok = fv is not None and _eq(fv.value, exp["value"])
        detail["value"] = fv.value if fv else None
    if ok and exp["kind"] == "PATCH" and "remove" in exp:
        ok = exp["remove"] in it.remove_given
    if ok and exp["kind"] == "BARE":
        target = bare_target(it.bare_value, ctx or None, {})
        ok = target == exp.get("field")
        detail["target"] = target
    return {"ok": ok, **detail}


def score_danger(text, vt, exp):
    findings = evaluate(text, vt or None)
    pos = sorted(f.sign_id for f in findings if f.status == "POSITIVE")
    unc = sorted(f.sign_id for f in findings if f.status == "UNCERTAIN")
    neg = sorted(f.sign_id for f in findings if f.status == "NEGATED")
    exp_pos = sorted(exp.get("positive", []))
    missed = [s for s in exp_pos if s not in pos]
    false_pos = [s for s in pos if s not in exp_pos]
    unc_ok = all(s in unc for s in exp.get("uncertain", []))
    neg_ok = all(s in neg for s in exp.get("negated", []))
    return {"ok": not missed and not false_pos and unc_ok and neg_ok, "positive": pos, "uncertain": unc,
            "negated": neg, "missed": missed, "false_positive": false_pos, "expected_positive": exp_pos}


def run_offline(rows, expected):
    results = []
    for r in rows:
        exp = expected[r["id"]]
        t0 = time.perf_counter()
        if r["kind"] == "extract":
            res = score_extract(r["utterance"], exp)
        elif r["kind"] == "correct":
            res = score_correct(r["utterance"], r["context"], exp)
        else:
            res = score_danger(r["utterance"], r["context"], exp)
        res["ms"] = round((time.perf_counter() - t0) * 1000, 2)
        results.append({**r, "result": res})
    return results


def summarise(results):
    ext = [x for x in results if x["kind"] == "extract"]
    cor = [x for x in results if x["kind"] == "correct"]
    dan = [x for x in results if x["kind"] == "danger"]

    def acc(rows):
        n = sum(x["result"]["n_fields"] for x in rows)
        c = sum(x["result"]["n_correct"] for x in rows)
        return {"fields": n, "correct": c, "accuracy": round(c / n, 4) if n else None}

    num_fields = ("beneficiary_id", "weight_kg", "next_visit_date")
    num_total = num_ok = 0
    for x in ext:
        exp = {k: v for k, v in x["result"]["got"].items()}
        for f in num_fields:
            e = json.loads(json.dumps(EXPECTED[x["id"]])).get(f)
            if e is not None:
                num_total += 1
                num_ok += int(_eq(exp.get(f), e))
    by_lang = {}
    for x in ext:
        by_lang.setdefault(x["language"], []).append(x)
    exp_pos_total = sum(len(x["result"]["expected_positive"]) for x in dan)
    missed = sum(len(x["result"]["missed"]) for x in dan)
    fps = sum(len(x["result"]["false_positive"]) for x in dan)
    patch_rows = [x for x in cor if EXPECTED[x["id"]]["kind"] in ("PATCH", "BARE")]
    return {
        "utterances": len(results),
        "field_accuracy_clean": acc([x for x in ext if x["noise"] == "clean"]),
        "field_accuracy_noisy_text": acc([x for x in ext if x["noise"] == "noisy"]),
        "number_accuracy": {"fields": num_total, "correct": num_ok,
                            "accuracy": round(num_ok / num_total, 4) if num_total else None},
        "field_accuracy_by_language": {k: acc(v) for k, v in sorted(by_lang.items())},
        "invented_fields": sum(len(x["result"]["invented"]) for x in ext),
        "extraction_cases_fully_correct": f"{sum(x['result']['ok'] for x in ext)}/{len(ext)}",
        "correction_success": f"{sum(x['result']['ok'] for x in patch_rows)}/{len(patch_rows)}",
        "intent_success_all": f"{sum(x['result']['ok'] for x in cor)}/{len(cor)}",
        "danger_recall": {"expected_positive": exp_pos_total, "missed": missed,
                          "recall": round((exp_pos_total - missed) / exp_pos_total, 4) if exp_pos_total else None},
        "danger_false_positives": fps,
        "danger_cases_fully_correct": f"{sum(x['result']['ok'] for x in dan)}/{len(dan)}",
        "median_processing_ms": round(statistics.median(x["result"]["ms"] for x in results), 2),
    }


# ---------------------------------------------------------------- live loopback (credits!)
async def live_loopback(rows, expected, limit, snr_db):
    import contextlib
    import math
    import random
    import struct
    from app.config import get_settings
    from app.services.credential_manager import CredentialManager
    from app.services.normalise import keyterms_for
    from app.speech.gnani_stt import PrismaSTTStream
    from app.speech.gnani_tts import TimbreTTSClient

    s = get_settings()
    s.tts_sample_rate = 16000
    cm = CredentialManager(s)
    if not cm.configured:
        sys.exit("GNANI_API_KEY is not configured in backend/.env")
    out = []
    for r in rows[:limit]:
        lang = {"hi": "hi", "hi-en": "hi", "kn": "kn", "kn-en": "kn"}.get(r["language"], "en")
        tts = TimbreTTSClient(settings=s, credentials=cm)
        pcm = bytearray()
        async with contextlib.aclosing(tts.synthesize(r["utterance"], lang)) as gen:
            async for c in gen:
                pcm.extend(c)
        await tts.drop()
        samples = list(struct.unpack(f"<{len(pcm) // 2}h", bytes(pcm[: len(pcm) // 2 * 2])))
        if snr_db is not None and samples:
            sig = math.sqrt(sum(x * x for x in samples) / len(samples)) or 1
            nrms = sig / (10 ** (snr_db / 20))
            rnd = random.Random(7)
            brown = 0.0
            for i in range(len(samples)):  # brown-ish street rumble + hiss
                brown = 0.98 * brown + rnd.gauss(0, 1)
                samples[i] = max(-32767, min(32767, int(samples[i] + nrms * (0.6 * brown / 7 + 0.4 * rnd.gauss(0, 1)))))
        audio = struct.pack(f"<{len(samples)}h", *samples) + bytes(32000)
        texts = []
        done = asyncio.Event()

        async def on_event(e):
            if e["type"] == "transcript" and e["text"]:
                texts.append(e["text"])

        st = PrismaSTTStream(settings=s, credentials=cm, language=lang, keyterms=keyterms_for(lang),
                             on_event=on_event, request_id=f"eval-{r['id']}")
        t0 = time.monotonic()
        await st.open()
        for i in range(0, len(audio), 1024):
            st.push_audio(audio[i:i + 1024])
            await asyncio.sleep(0.032)
        await st.commit()
        await asyncio.sleep(1.5)
        await st.close()
        heard = " ".join(texts)
        r2 = dict(r, utterance=heard)
        res = run_offline([r2], expected)[0]
        res["heard"] = heard
        res["spoken"] = r["utterance"]
        res["stt_wall_s"] = round(time.monotonic() - t0, 2)
        out.append(res)
        print(r["id"], "OK" if res["result"]["ok"] else "FAIL", "|", heard[:90])
        _ = done
    return out


def write_reports(summary, results, live=None):
    payload = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "today_fixed": TODAY.isoformat(),
               "mode": "offline transcript-level", "summary": summary, "results": results}
    if live is not None:
        payload["live_loopback"] = live
    (HERE / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# ASHA Vaani evaluation results", "",
             f"Generated {payload['generated_at']} by `python evaluation/run_eval.py` (reference date {TODAY}).", "",
             "**Scope:** transcript-level (NLU) scoring of 65 scripted synthetic utterances. 'Noisy' rows simulate ASR",
             "noise in text only. Live Gnani STT accuracy and acoustic noise are measured separately with",
             "`--live-loopback` (needs credentials; not run in the build environment).", "",
             "| Metric | Result | Target |", "|---|---|---|"]
    s = summary
    lines += [
        f"| Field accuracy (clean) | {s['field_accuracy_clean']['correct']}/{s['field_accuracy_clean']['fields']} = {s['field_accuracy_clean']['accuracy']:.1%} | ≥ 90% |",
        f"| Field accuracy (noisy text) | {s['field_accuracy_noisy_text']['correct']}/{s['field_accuracy_noisy_text']['fields']} = {s['field_accuracy_noisy_text']['accuracy']:.1%} | ≥ 80% |",
        f"| Number accuracy (ID, weight, next date) | {s['number_accuracy']['correct']}/{s['number_accuracy']['fields']} = {s['number_accuracy']['accuracy']:.1%} | > field accuracy |",
        f"| Invented (unstated) fields | {s['invented_fields']} | 0 |",
        f"| Correction success | {s['correction_success']} | ≥ 95% |",
        f"| All intents (corrections, undo, yes/no, advice guardrail) | {s['intent_success_all']} | — |",
        f"| Danger-sign recall | {s['danger_recall']['expected_positive'] - s['danger_recall']['missed']}/{s['danger_recall']['expected_positive']} | 100% |",
        f"| False danger alerts | {s['danger_false_positives']} | ~0 |",
        f"| Danger cases fully correct (incl. negation/uncertainty) | {s['danger_cases_fully_correct']} | — |",
        f"| Median processing time per utterance | {s['median_processing_ms']} ms | — |", "",
        "## Field accuracy by language", "", "| Language | Correct / fields |", "|---|---|"]
    for k, v in s["field_accuracy_by_language"].items():
        lines.append(f"| {k} | {v['correct']}/{v['fields']} ({v['accuracy']:.0%}) |")
    lines += ["", "## Failures (shown honestly)", ""]
    fails = [x for x in results if not x["result"]["ok"]]
    if not fails:
        lines.append("None.")
    for x in fails:
        lines.append(f"- **{x['id']}** ({x['language']}, {x['category']}): `{x['utterance']}` → {json.dumps({k: v for k, v in x['result'].items() if k not in ('got', 'ms')}, ensure_ascii=False)}")
    (HERE / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


ROWS = list(csv.DictReader(open(HERE / "utterances.csv", encoding="utf-8")))
EXPECTED = json.load(open(HERE / "expected_outputs.json", encoding="utf-8"))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-loopback", action="store_true", help="spend Gnani credits: Timbre->Prisma loopback")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--noise-snr", type=float, default=None)
    args = ap.parse_args()
    results = run_offline(ROWS, EXPECTED)
    summary = summarise(results)
    live = None
    if args.live_loopback:
        live = asyncio.run(live_loopback([r for r in ROWS if r["kind"] == "extract"], EXPECTED, args.limit, args.noise_snr))
    write_reports(summary, results, live)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    fails = [x["id"] for x in results if not x["result"]["ok"]]
    print("failures:", fails or "none")
