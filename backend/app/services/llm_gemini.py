"""Optional Gemini extraction (LLM = open choice under the hackathon rules).

* Uses the public generateContent REST endpoint with header `x-goog-api-key`.
* Standard library only (urllib in a worker thread), so no extra dependency.
* Output is a JSON object of candidate values, EACH with an `evidence` quote that must
  appear verbatim in the transcript (checked in extraction.merge). The model is told
  not to decide danger signs and not to infer anything not spoken.
* Sampling parameters are intentionally not sent (deprecated for Gemini 3.5+ models).
* Any failure/timeout returns None and the rule-based extraction is used alone.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request

from ..config import Settings

log = logging.getLogger("asha.llm")

SYSTEM_INSTRUCTION = """You extract fields from an ASHA health worker's spoken home-visit note.
The note may mix Hindi, Kannada and English, in any script.
Rules:
- Extract ONLY facts explicitly stated. Never infer, guess or complete missing facts.
- For every field you fill, copy the exact words from the note into "evidence".
- If a field was not stated or is unclear, use null (or [] for lists).
- Do NOT decide danger signs, diagnoses, treatment or dosage. Ignore them.
- visit_type must be one of ANC, PNC, NEWBORN, IMMUNISATION or null.
- weight_kg is a number in kilograms (convert grams). Dates are YYYY-MM-DD using TODAY.
- vaccinations_given = given today; vaccinations_due = stated as due/pending.
Return only JSON with this shape:
{"beneficiary_id": {"value": "digits"|null, "evidence": "..."},
 "beneficiary_name": {"value": str|null, "evidence": "..."},
 "visit_type": {"value": str|null, "evidence": "..."},
 "visit_date": {"value": "YYYY-MM-DD"|null, "evidence": "..."},
 "weight_kg": {"value": number|null, "evidence": "..."},
 "vaccinations_given": {"value": [str], "evidence": "..."},
 "vaccinations_due": {"value": [str], "evidence": "..."},
 "ifa_tablets_given": {"value": true|false|null, "evidence": "..."},
 "next_visit_date": {"value": "YYYY-MM-DD"|null, "evidence": "..."}}"""


class GeminiExtractor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_latency_ms: float | None = None
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.settings.llm_configured

    def _request(self, transcript: str, today_iso: str) -> dict | None:
        url = f"{self.settings.gemini_endpoint}/{self.settings.gemini_model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": f"TODAY: {today_iso}\nNOTE: {transcript}"}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={
            "Content-Type": "application/json", "x-goog-api-key": self.settings.gemini_api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.settings.llm_timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.last_error = f"HTTP {exc.code}"
            return None
        except Exception as exc:
            self.last_error = type(exc).__name__
            return None
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            text = text.strip()
            if text.startswith("```"):
                text = text.strip("`")
                text = text[text.find("{"):]
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            self.last_error = "unparseable response"
            return None

    async def extract(self, transcript: str, today_iso: str) -> dict | None:
        if not self.enabled or not transcript.strip():
            return None
        import time
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(asyncio.to_thread(self._request, transcript, today_iso),
                                            self.settings.llm_timeout_s + 0.5)
        except asyncio.TimeoutError:
            self.last_error = "timeout"
            result = None
        self.last_latency_ms = (time.monotonic() - t0) * 1000
        return result
