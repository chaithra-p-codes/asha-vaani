# ASHA Vaani evaluation results

Generated 2026-11-11 15:32:29 by `python evaluation/run_eval.py` (reference date 2026-11-11).

**Scope:** transcript-level (NLU) scoring of 65 scripted synthetic utterances. 'Noisy' rows simulate ASR
noise in text only. Live Gnani STT accuracy and acoustic noise are measured separately with
`--live-loopback` (needs credentials; not run in the build environment).

| Metric | Result | Target |
|---|---|---|
| Field accuracy (clean) | 101/101 = 100.0% | ≥ 90% |
| Field accuracy (noisy text) | 26/26 = 100.0% | ≥ 80% |
| Number accuracy (ID, weight, next date) | 72/72 = 100.0% | > field accuracy |
| Invented (unstated) fields | 0 | 0 |
| Correction success | 10/10 | ≥ 95% |
| All intents (corrections, undo, yes/no, advice guardrail) | 16/16 | — |
| Danger-sign recall | 16/16 | 100% |
| False danger alerts | 0 | ~0 |
| Danger cases fully correct (incl. negation/uncertainty) | 18/18 | — |
| Median processing time per utterance | 1.52 ms | — |

## Field accuracy by language

| Language | Correct / fields |
|---|---|
| en | 51/51 (100%) |
| hi | 24/24 (100%) |
| hi-en | 34/34 (100%) |
| kn | 9/9 (100%) |
| kn-en | 9/9 (100%) |

## Failures (shown honestly)

None.
