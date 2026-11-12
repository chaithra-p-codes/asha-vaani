"""Visit session orchestration: one VisitSession per active visit.

Mic audio (browser) -> Prisma v3.0 stream -> final transcripts -> turn endpointing ->
rule (+ optional LLM) extraction -> validation -> deterministic danger rules ->
template read-back -> Timbre v3.0 stream -> browser playback -> voice correction ->
explicit confirmation -> idempotent encrypted save -> follow-ups.

Truthfulness rules enforced here:
  * `saved` is only emitted after the database transaction commits;
  * if Timbre fails, the client is told `tts_unavailable` (never "spoken");
  * demo mode is labelled on every event and never calls Gnani;
  * no LLM output can raise or clear a danger flag.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from .config import SUPPORTED_LANGUAGES, Settings
from .services import danger_rules, followups as followups_svc, validation
from .services.corrections import FIELD_ORDER, bare_target, classify
from .services.credential_manager import CredentialManager, NoAuthorisedCredential
from .services.extraction import FIELDS, FieldValue, RuleExtractor, merge
from .services.llm_gemini import GeminiExtractor
from .services.normalise import keyterms_for, match_form, find_phrases
from .services.readback import field_name, field_phrase, join_list, readback_text, t
from .speech.audio_utils import EnergyVAD, frame_rms, pcm16_duration_ms
from .speech.gnani_stt import PrismaSTTStream, STTError
from .speech.gnani_tts import TimbreTTSClient, TTSCache, TTSError
from .speech.transport import ConnectFn
from .state_machine import InvalidTransition, check
from .storage.db import Database, token_hash
from .websocket.events import AUDIO_FRAME_TAG

log = logging.getLogger("asha.session")

DANGER_REDIRECT = {("PREG_BLEEDING", "PNC"): "PNC_EXCESSIVE_BLEEDING"}
FIELD_WORDS = {
    "weight_kg": ["weight", "vajan", "wajan", "वजन", "ತೂಕ"],
    "beneficiary_id": ["id", "आईडी", "ಐಡಿ", "beneficiary", "लाभार्थी", "ಫಲಾನುಭವಿ", "number", "नंबर"],
    "visit_type": ["visit type", "type", "प्रकार", "ಪ್ರಕಾರ"],
    "next_visit_date": ["next visit", "date", "tarikh", "तारीख", "अगली", "ದಿನಾಂಕ", "ಮುಂದಿನ"],
    "vaccinations_given": ["vaccine", "vaccines", "tika", "टीका", "टीके", "ಲಸಿಕೆ"],
}


class ClientSender:
    """Serialises writes to one browser WebSocket; silently drops after close."""

    def __init__(self, ws):
        self.ws = ws
        self._lock = asyncio.Lock()
        self.closed = False

    async def send_json(self, obj: dict) -> None:
        if self.closed:
            return
        async with self._lock:
            try:
                await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
            except Exception:
                self.closed = True

    async def send_bytes(self, data: bytes) -> None:
        if self.closed:
            return
        async with self._lock:
            try:
                await self.ws.send_bytes(data)
            except Exception:
                self.closed = True


@dataclass
class SpeechItem:
    uid: int
    text: str
    kind: str
    cacheable: bool = False
    speed: float | None = None
    after: Callable[[], Awaitable[None]] | None = None
    awaiting_after: str | None = None
    cancelled: bool = False
    finished: bool = False
    streamed_ms: float = 0.0
    turn_end_ts: float | None = None
    last_voice_ts: float | None = None


@dataclass
class Turn:
    started: float = field(default_factory=time.monotonic)
    texts: list = field(default_factory=list)
    open_utterances: int = 0
    speech_seen: bool = False
    last_voice: float | None = None
    detected_language: str | None = None
    stt_latencies: list = field(default_factory=list)


class VisitSession:
    def __init__(self, *, manager: "SessionManager", session_id: str, token_hash_: str, language: str,
                 mode: str, draft: dict | None = None):
        self.m = manager
        self.s: Settings = manager.settings
        self.id = session_id
        self.token_hash = token_hash_
        self.language = language if language in SUPPORTED_LANGUAGES else "hi"
        self.mode = mode                       # live | demo | diag
        self.state = "IDLE"
        self.awaiting = "dictation"
        self.record: dict = {f: ([] if f.startswith("vaccinations") else None) for f in FIELDS}
        self.meta: dict = {}
        self.history: list[list[dict]] = []
        self.asked: set[str] = set()
        self.danger: dict[str, dict] = {}
        self.pending_danger: list[str] = []
        self.transcript_log: list[dict] = []
        self.last_read_field: str | None = None
        self.draft_version = 0
        self.saved_visit_id: str | None = None
        self.retries: dict[str, int] = {}
        self.id_suggestion: dict | None = None
        self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if draft:
            self._load_draft(draft)
        self.sender: ClientSender | None = None
        self._seq = 0
        self._uid = 0
        self._speech_q: asyncio.Queue = asyncio.Queue()
        self._speech_task: asyncio.Task | None = None
        self._current: SpeechItem | None = None
        self._items: dict[int, SpeechItem] = {}
        self._timers: dict[int, asyncio.Task] = {}
        self._turn_lock = asyncio.Lock()
        self.stt: PrismaSTTStream | None = None
        self.tts: TimbreTTSClient | None = None
        self.turn: Turn | None = None
        self.vad = EnergyVAD()
        self._endpoint_task: asyncio.Task | None = None
        self._audio_backlog: list[bytes] = []
        self.stt_seconds = 0.0
        self.last_error: str | None = None
        self._turn_end_ts: float | None = None
        self._turn_last_voice: float | None = None

    # ================================================================== utilities
    def today(self) -> date:
        return datetime.now(ZoneInfo(self.s.timezone)).date()

    def registry(self) -> list[dict]:
        return self.m.registry_cache

    async def emit(self, etype: str, **payload) -> None:
        if not self.sender:
            return
        self._seq += 1
        await self.sender.send_json({"type": etype, "session_id": self.id, "seq": self._seq,
                                     "ts": time.time(), "mode": self.mode, **payload})

    async def set_state(self, new: str) -> bool:
        try:
            check(self.state, new)
        except InvalidTransition as exc:
            log.warning("session %s: %s", self.id[:8], exc)
            await self.emit("error", code="invalid_transition", message=str(exc), recoverable=True)
            return False
        if new != self.state:
            prev, self.state = self.state, new
            await self.emit("state", state=new, prev=prev, awaiting=self.awaiting)
        return True

    async def audit(self, event_type: str, field_name_: str | None = None, reason: str | None = None):
        await asyncio.to_thread(self.m.db.add_event, self.id, event_type, field_name_, reason)

    async def metric(self, name: str, value_ms: float):
        if value_ms is None or value_ms < 0:
            return
        await asyncio.to_thread(self.m.db.add_metric, self.id, name, value_ms)

    def snapshot(self) -> dict:
        return {
            "record": self.record, "meta": self.meta, "danger": self.danger, "pending_danger": self.pending_danger,
            "referral_status": self.referral_status(), "awaiting": self.awaiting, "state": self.state,
            "draft_version": self.draft_version, "saved_visit_id": self.saved_visit_id,
            "can_undo": bool(self.history), "can_save": validation.can_save(self.record),
            "transcript": self.transcript_log[-20:], "language": self.language,
        }

    def _draft(self) -> dict:
        return {"record": self.record, "meta": self.meta, "history": self.history[-20:], "asked": sorted(self.asked),
                "danger": self.danger, "pending_danger": self.pending_danger, "transcript": self.transcript_log[-40:],
                "awaiting": self.awaiting, "draft_version": self.draft_version, "saved_visit_id": self.saved_visit_id,
                "last_read_field": self.last_read_field, "state": self.state}

    def _load_draft(self, d: dict) -> None:
        self.record.update(d.get("record") or {})
        self.meta = d.get("meta") or {}
        self.history = d.get("history") or []
        self.asked = set(d.get("asked") or [])
        self.danger = d.get("danger") or {}
        self.pending_danger = d.get("pending_danger") or []
        self.transcript_log = d.get("transcript") or []
        self.awaiting = d.get("awaiting") or "dictation"
        self.draft_version = d.get("draft_version") or 0
        self.saved_visit_id = d.get("saved_visit_id")
        self.last_read_field = d.get("last_read_field")

    async def persist(self) -> None:
        try:
            await asyncio.to_thread(self.m.db.save_session, self.id, None, self.language, self.mode, self.state,
                                    self._draft(), self.s.session_ttl_minutes)
        except Exception as exc:  # persistence failure must not break the live loop
            log.warning("persist failed: %s", type(exc).__name__)

    def referral_status(self) -> str:
        statuses = [d["status"] for d in self.danger.values()]
        if "POSITIVE" in statuses:
            return "REFER_NOW"
        if "REVIEW" in statuses or self.pending_danger:
            return "REVIEW_REQUIRED"
        return "NONE"

    async def send_draft(self, changed: list[str] | None = None) -> None:
        issues = validation.validate(dict(self.record), self.meta, self.today(), self.m.registry_ids)
        await self.emit("draft", **self.snapshot(), changed_fields=changed or [],
                        issues=[i.public() for i in issues])

    # ================================================================== wiring
    async def attach(self, sender: ClientSender, resume: bool = False) -> None:
        self.sender = sender
        live = self.mode in ("live", "diag")
        await self.emit("session", state=self.state, language=self.language, services={
            "stt": self.s.stt_model if live else None, "tts": self.s.tts_model if live else None,
            "voice": self.s.tts_voice if live else None, "llm": self.s.gemini_model if self.m.llm.enabled else None,
            "tts_sample_rate": self.s.tts_sample_rate}, demo=self.mode == "demo")
        if self._speech_task is None or self._speech_task.done():
            self._speech_task = asyncio.create_task(self._speech_worker())
        if live and self.tts is None:
            self.tts = TimbreTTSClient(settings=self.s, credentials=self.m.credentials, cache=self.m.tts_cache,
                                       connect_fn=self.m.tts_connect)
            asyncio.create_task(self.tts.prewarm())
        if live:
            asyncio.create_task(self._prewarm_stt())
        if self.saved_visit_id:
            await self.send_draft()
            await self.emit("saved", visit_id=self.saved_visit_id, resumed=True)
            return
        has_draft = any(self.record.get(f) not in (None, [], "") for f in FIELDS)
        if has_draft:
            # Resumed after refresh / reconnect / backend restart: never auto-save; ask again.
            await self.audit("session_resumed")
            if self.state not in ("CONFIRMING",):
                with contextlib.suppress(Exception):
                    self.state = "RECONNECTING"
                    await self.emit("state", state="RECONNECTING", prev=None, awaiting=self.awaiting)
                await self.set_state("CONFIRMING")
            self.awaiting = "confirmation"
            await self.send_draft()
            await self.say(t("confirm_q", self.language), "confirm_prompt", cacheable=True,
                           awaiting_after="confirmation", after=lambda: self.start_listening("confirmation", "auto"))
            return
        if self.mode == "diag":
            self.awaiting = "echo"
            await self.say(t("ack", self.language), "diag", cacheable=True)
            return
        await self.audit("session_started", reason=self.mode)
        await self.send_draft()
        # FIRST TURN = AI disclosure in the selected language (hackathon baseline rule).
        await self.say(t("disclosure", self.language), "disclosure", cacheable=True, awaiting_after="dictation",
                       after=lambda: self.start_listening("dictation", "auto"))

    async def detach(self) -> None:
        self.sender = None
        await self.cancel_speech("client_disconnected", notify=False)
        await self._stop_endpoint_watch()
        if self.stt:
            with contextlib.suppress(Exception):
                await self.stt.close()
            self.stt = None
        if self.tts:
            with contextlib.suppress(Exception):
                await self.tts.drop()
        if self.state == "LISTENING":
            self.state = {"confirmation": "CONFIRMING", "dictation": "IDLE"}.get(self.awaiting, "ASKING")
        await self.persist()

    # ================================================================== speech output
    async def say(self, text: str, kind: str, *, cacheable: bool = False, speed: float | None = None,
                  after: Callable[[], Awaitable[None]] | None = None, awaiting_after: str | None = None) -> int:
        self._uid += 1
        item = SpeechItem(self._uid, text, kind, cacheable, speed, after, awaiting_after,
                          turn_end_ts=self._turn_end_ts, last_voice_ts=self._turn_last_voice)
        self._turn_end_ts = None  # only the first reply after a turn counts towards TTFA
        self._items[item.uid] = item
        self.transcript_log.append({"role": "agent", "text": text, "kind": kind})
        await self._speech_q.put(item)
        return item.uid

    async def _speech_worker(self) -> None:
        while True:
            item: SpeechItem = await self._speech_q.get()
            if item.cancelled:
                continue
            self._current = item
            audio = self.mode in ("live", "diag")
            await self.emit("agent_say", utterance_id=item.uid, text=item.text, kind=item.kind, audio=audio,
                            sample_rate=self.s.tts_sample_rate, encoding="pcm_s16le")
            if not audio:
                self._arm_timeout(item, 2500 + 45 * len(item.text))
                continue
            try:
                t0 = time.monotonic()
                total = 0
                first = True
                async with contextlib.aclosing(self.tts.synthesize(item.text, self.language, speed=item.speed,
                                                                  cacheable=item.cacheable)) as gen:
                    async for chunk in gen:
                        if item.cancelled or not self.sender:
                            break
                        if first:
                            first = False
                            now = time.monotonic()
                            await self.metric("tts_first_chunk_ms", (now - t0) * 1000)
                            if item.turn_end_ts:
                                await self.metric("server_turn_end_to_first_audio_ms", (now - item.turn_end_ts) * 1000)
                            if item.last_voice_ts:
                                await self.metric("server_end_of_speech_to_first_audio_ms",
                                                  (now - item.last_voice_ts) * 1000)
                            await self.emit("tts_start", utterance_id=item.uid,
                                            from_cache=self.tts.last_from_cache,
                                            first_chunk_ms=round((now - t0) * 1000))
                        for i in range(0, len(chunk), 16384):
                            part = chunk[i:i + 16384]
                            total += len(part)
                            await self.sender.send_bytes(bytes([AUDIO_FRAME_TAG]) + item.uid.to_bytes(4, "little") + part)
                item.streamed_ms = pcm16_duration_ms(total, self.s.tts_sample_rate)
                if not item.cancelled:
                    await self.emit("tts_end", utterance_id=item.uid, audio_ms=round(item.streamed_ms))
                    self._arm_timeout(item, item.streamed_ms + 3000)
            except (TTSError, NoAuthorisedCredential) as exc:
                code = getattr(exc, "code", "no_credential")
                self.last_error = f"tts:{code}"
                await self.emit("tts_unavailable", utterance_id=item.uid, reason=code,
                                message="Speech audio unavailable; the text is shown instead.")
                await self.audit("tts_unavailable", reason=code)
                await self._finish_item(item)
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("speech worker error")
                await self.emit("tts_unavailable", utterance_id=item.uid, reason=type(exc).__name__)
                await self._finish_item(item)
            finally:
                if self._current is item:
                    self._current = None

    def _arm_timeout(self, item: SpeechItem, ms: float) -> None:
        async def _t():
            await asyncio.sleep(ms / 1000.0)
            await self._finish_item(item)
        self._timers[item.uid] = asyncio.create_task(_t())

    async def _finish_item(self, item: SpeechItem) -> None:
        if item.finished or item.cancelled:
            return
        item.finished = True
        timer = self._timers.pop(item.uid, None)
        if timer and timer is not asyncio.current_task():
            timer.cancel()
        if item.after:
            try:
                await item.after()
            except Exception:  # pragma: no cover
                log.exception("continuation failed")

    async def cancel_speech(self, reason: str, notify: bool = True) -> str | None:
        """Barge-in / interruption: stop forwarding audio, drop queued prompts and the
        Timbre stream. Returns what the interrupted prompt was waiting for."""
        awaiting = None
        cancelled = []
        cur = self._current
        for item in list(self._items.values()):
            if not item.finished and not item.cancelled:
                item.cancelled = True
                cancelled.append(item.uid)
                awaiting = awaiting or item.awaiting_after
                t_ = self._timers.pop(item.uid, None)
                if t_:
                    t_.cancel()
        while not self._speech_q.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._speech_q.get_nowait()
        if cur is not None and self.tts is not None:
            await self.tts.drop()
        if cancelled and notify:
            await self.emit("tts_cancel", utterance_ids=cancelled, reason=reason)
            await self.audit("barge_in" if reason == "barge_in" else "tts_cancelled", reason=reason)
        return awaiting

    # ================================================================== listening
    async def _prewarm_stt(self) -> None:
        try:
            await self._ensure_stt()
        except Exception:
            pass

    async def _ensure_stt(self) -> None:
        if self.stt and self.stt.is_open:
            return
        if not self.m.credentials.configured:
            raise STTError("not_configured", "Gnani API key is not configured on the server")
        delays = [0.0, 0.5, 1.5]
        last_exc = None
        for attempt, delay in enumerate(delays):
            if delay:
                await asyncio.sleep(delay + secrets.randbelow(200) / 1000.0)
            stream = PrismaSTTStream(settings=self.s, credentials=self.m.credentials, language=self.language,
                                     keyterms=keyterms_for(self.language), on_event=self._on_stt_event,
                                     request_id=f"asha-{self.id[:8]}-{uuid.uuid4().hex[:6]}",
                                     connect_fn=self.m.stt_connect)
            try:
                await self.emit("stt_status", status="connecting", attempt=attempt + 1)
                await stream.open()
                self.stt = stream
                await self.metric("stt_open_ms", stream.open_latency_ms or 0)
                return
            except NoAuthorisedCredential as exc:
                raise STTError("quota", str(exc)) from exc
            except STTError as exc:
                last_exc = exc
                if exc.code in ("auth", "not_configured"):
                    break
                # quota: credential manager already marked the key; next attempt picks the
                # next AUTHORISED key if one exists, otherwise active() raises
        raise last_exc or STTError("connect_failed", "Could not connect to Prisma")

    async def start_listening(self, awaiting: str | None = None, reason: str = "user") -> None:
        if self.state in ("SAVING", "SUMMARY"):
            return
        if awaiting:
            self.awaiting = awaiting
        if self.mode == "demo":
            # Demo mode never captures audio; the UI offers labelled sample utterances.
            await self.emit("listen", on=False, demo=True, awaiting=self.awaiting)
            return
        if self.stt_seconds >= self.s.max_stt_seconds_per_session:
            await self.emit("error", code="stt_budget", recoverable=False,
                            message="Per-session speech budget reached (credit protection).")
            return
        try:
            await self._ensure_stt()
        except STTError as exc:
            self.last_error = f"stt:{exc.code}"
            await self.audit("stt_unavailable", reason=exc.code)
            if self.state != "RECOVERY":
                with contextlib.suppress(Exception):
                    await self.set_state("RECOVERY")
            await self.emit("stt_status", status="unavailable", code=exc.code, message=str(exc))
            await self.emit("recovery", layer=1 if exc.code not in ("quota", "auth", "not_configured") else 3,
                            code=exc.code, message="Live speech is unavailable. Your draft is kept and is NOT saved.")
            return
        if self.state == "RECOVERY":
            await self.set_state("RECONNECTING")
        self.turn = Turn()
        self.vad = EnergyVAD()
        if not await self.set_state("LISTENING"):
            return
        await self.emit("listen", on=True, awaiting=self.awaiting, reason=reason,
                        endpoint_ms=self._endpoint_ms())
        for frame in self._audio_backlog:
            self._push_audio(frame)
        self._audio_backlog.clear()
        await self._stop_endpoint_watch()
        self._endpoint_task = asyncio.create_task(self._endpoint_watch())

    def _endpoint_ms(self) -> int:
        return self.s.endpoint_silence_dictation_ms if self.awaiting == "dictation" else self.s.endpoint_silence_short_ms

    async def _stop_endpoint_watch(self) -> None:
        task, self._endpoint_task = self._endpoint_task, None
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def on_audio(self, data: bytes) -> None:
        if self.mode == "demo":
            return
        if self.state != "LISTENING":
            # pre-roll audio sent right after a barge-in arrives before LISTENING; keep ~0.5 s
            if self._barge_pending:
                self._audio_backlog.append(data)
                self._audio_backlog = self._audio_backlog[-16:]
            return
        self._push_audio(data)

    _barge_pending = False

    def _push_audio(self, data: bytes) -> None:
        if not self.stt or not self.turn:
            return
        self.stt.push_audio(data)
        self.stt_seconds += len(data) / 32000.0
        for i in range(0, len(data) - 1, 1024):
            rms = frame_rms(data[i:i + 1024])
            if self.vad.update(rms) and self.vad.speech_frames >= 3:
                self.turn.speech_seen = True
                self.turn.last_voice = time.monotonic()

    async def _on_stt_event(self, evt: dict) -> None:
        etype = evt["type"]
        if etype == "connected":
            await self.emit("stt_status", status="connected", open_latency_ms=evt.get("open_latency_ms"),
                            config=evt.get("config"))
        elif etype == "speech_start":
            if self.turn:
                self.turn.open_utterances += 1
                self.turn.speech_seen = True
                self.turn.last_voice = time.monotonic()
            await self.emit("stt_status", status="speech_start")
        elif etype == "processing":
            await self.emit("stt_status", status="processing")
        elif etype == "transcript":
            text = evt.get("text", "")
            if self.turn:
                self.turn.open_utterances = max(0, self.turn.open_utterances - 1)
                if text:
                    self.turn.texts.append(text)
                    self.turn.detected_language = evt.get("detected_language")
                    if evt.get("latency_ms") is not None:
                        self.turn.stt_latencies.append(evt["latency_ms"])
            if evt.get("latency_ms") is not None:
                await self.metric("prisma_reported_latency_ms", float(evt["latency_ms"]))
            await self.emit("transcript", text=text, is_final=True, segment_index=evt.get("segment_index"),
                            latency_ms=evt.get("latency_ms"), detected_language=evt.get("detected_language"))
        elif etype == "error":
            self.last_error = "stt:server_error"
            await self.emit("stt_status", status="error", message=evt.get("message"), quota=evt.get("quota"))
        elif etype == "closed":
            self.stt = None
            await self.emit("stt_status", status="closed", code=evt.get("code"))
            if self.state == "LISTENING":
                # Layer 1: reconnect once automatically and keep listening
                await self.emit("stt_status", status="reconnecting")
                try:
                    await self._ensure_stt()
                    await self.emit("stt_status", status="connected")
                except STTError as exc:
                    await self._abort_listening(f"stt:{exc.code}")

    async def _abort_listening(self, reason: str) -> None:
        await self._stop_endpoint_watch()
        await self.emit("listen", on=False, awaiting=self.awaiting, reason=reason)
        if self.state == "LISTENING":
            await self.set_state("RECOVERY")
        await self.emit("recovery", layer=1, code=reason,
                        message="Speech connection lost. Your draft is kept and is NOT saved.")

    async def _endpoint_watch(self) -> None:
        try:
            idle_limit = self.s.listen_idle_timeout_s
            while self.state == "LISTENING" and self.turn:
                await asyncio.sleep(0.04)
                turn = self.turn
                if turn is None:
                    return
                now = time.monotonic()
                elapsed = now - turn.started
                if not turn.speech_seen and not turn.texts and elapsed > idle_limit:
                    await self._listen_timeout()
                    return
                if elapsed > self.s.max_turn_s:
                    await self._end_turn("max_turn")
                    return
                last = turn.last_voice or turn.started
                silence_ms = (now - last) * 1000
                if (turn.texts or turn.speech_seen) and turn.open_utterances == 0 and silence_ms >= self._endpoint_ms():
                    if turn.texts:
                        await self._end_turn("endpoint")
                        return
                if turn.speech_seen and not turn.texts and silence_ms >= self._endpoint_ms() + 900:
                    await self._end_turn("endpoint_commit")
                    return
                # safety: a speech_start whose transcript never arrives must not hold the turn open
                if turn.texts and turn.open_utterances > 0 and silence_ms >= self._endpoint_ms() + 1500:
                    await self._end_turn("endpoint_stuck_segment")
                    return
        except asyncio.CancelledError:
            pass

    async def _listen_timeout(self) -> None:
        await self.emit("listen", on=False, awaiting=self.awaiting, reason="timeout")
        back = {"confirmation": "CONFIRMING", "dictation": "IDLE", "correction": "CONFIRMING"}.get(
            self.awaiting, "ASKING")
        await self.set_state(back)
        await self.audit("listen_timeout", reason=self.awaiting)

    async def stop_listening_manual(self) -> None:
        if self.state == "LISTENING":
            await self._stop_endpoint_watch()
            await self._end_turn("manual_stop")

    async def _end_turn(self, reason: str) -> None:
        turn = self.turn
        if turn is None or self.state != "LISTENING":
            return
        self._turn_end_ts = time.monotonic()
        self._turn_last_voice = turn.last_voice
        await self.set_state("TRANSCRIBING")
        await self.emit("listen", on=False, awaiting=self.awaiting, reason=reason)
        if self.stt:
            await self.stt.commit()
        # wait for any utterance Prisma is still finalising (commit closes it immediately)
        deadline = time.monotonic() + 2.5
        while (turn.open_utterances > 0 or (reason != "endpoint" and not turn.texts and turn.speech_seen)) \
                and time.monotonic() < deadline:
            await asyncio.sleep(0.03)
        self.turn = None
        text = " ".join(turn.texts).strip()
        if turn.last_voice:
            await self.metric("endpoint_wait_ms", (self._turn_end_ts - turn.last_voice) * 1000)
        await self.metric("transcript_ready_after_turn_end_ms", (time.monotonic() - self._turn_end_ts) * 1000)
        await self.handle_utterance(text, source="speech")

    # ================================================================== client events
    async def on_control(self, evt) -> None:
        et = evt.type
        if et == "ping":
            await self.emit("pong")
        elif et == "start_listening":
            if self._current is not None or any(not i.finished and not i.cancelled for i in self._items.values()):
                await self._barge_in("manual")
            else:
                await self.start_listening(None, evt.reason)
        elif et == "stop_listening":
            await self.stop_listening_manual()
        elif et in ("barge_in", "cancel_tts"):
            await self._barge_in("barge_in" if et == "barge_in" else "manual")
        elif et == "playback_ended":
            item = self._items.get(evt.utterance_id)
            if item and not evt.interrupted:
                await self._finish_item(item)
        elif et == "playback_started":
            pass
        elif et == "client_metric":
            await self.metric(evt.name, evt.value_ms)
        elif et == "action":
            await self._button(evt.action)
        elif et == "demo_utterance":
            if self.mode != "demo":
                await self.emit("error", code="demo_only", recoverable=True,
                                message="Typed utterances are only accepted in labelled demo mode.")
                return
            await self.cancel_speech("demo_input", notify=True)
            self._turn_end_ts = time.monotonic()
            await self.handle_utterance(evt.text, source="demo")

    async def _barge_in(self, reason: str) -> None:
        self._barge_pending = True
        try:
            awaiting = await self.cancel_speech("barge_in" if reason == "barge_in" else "manual")
            await self.start_listening(awaiting or self.awaiting, "barge_in")
        finally:
            self._barge_pending = False

    async def _button(self, action: str) -> None:
        if action == "confirm":
            if self.saved_visit_id:
                await self.save(via="button")  # idempotent: re-announces the existing visit
                return
            if self.state in ("CONFIRMING", "PENDING", "READBACK", "LISTENING") and self.awaiting in ("confirmation", "correction"):
                await self.cancel_speech("button", notify=True)
                await self._stop_endpoint_watch()
                if self.state == "LISTENING":
                    self.turn = None
                    await self.emit("listen", on=False, awaiting=self.awaiting, reason="button")
                    await self.set_state("CONFIRMING")
                if self.state == "READBACK":
                    await self.set_state("CONFIRMING")
                await self.save(via="button")
            else:
                await self.emit("error", code="not_ready_to_confirm", recoverable=True,
                                message="The record has not been read back for confirmation yet.")
        elif action == "undo":
            async with self._turn_lock:
                await self._undo_and_reply()
        elif action == "repeat":
            await self.cancel_speech("repeat")
            await self._readback()
        elif action == "skip" and self.awaiting.startswith("field:"):
            async with self._turn_lock:
                self.asked.add(self.awaiting.split(":", 1)[1])
                await self.say(t("skip_ok", self.language), "ack", cacheable=True)
                await self.next_step()
        elif action == "retry_save" and self.state == "PENDING":
            await self.save(via="retry")
        elif action == "new_visit":
            await self.emit("closed_for_new_visit")
        elif action == "dismiss_alert":
            await self.emit("alert_acknowledged")

    # ================================================================== turn handling
    async def handle_utterance(self, text: str, source: str) -> None:
        async with self._turn_lock:
            self.transcript_log.append({"role": "worker", "text": text, "source": source})
            await self.emit("turn_transcript", text=text, source=source, awaiting=self.awaiting)
            await self.audit("turn", reason=f"{self.awaiting}:{source}")
            if self.state == "LISTENING":
                await self.set_state("TRANSCRIBING")
            if self.state == "IDLE" and self.mode == "demo":
                self.state = "TRANSCRIBING"
                await self.emit("state", state="TRANSCRIBING", prev="IDLE", awaiting=self.awaiting)
            elif self.state in ("CONFIRMING", "ASKING", "READBACK", "ALERTING", "PENDING", "RECOVERY", "RECONNECTING"):
                # demo input or button-free path straight from a speaking/waiting phase
                self.state = "TRANSCRIBING"
                await self.emit("state", state="TRANSCRIBING", prev=None, awaiting=self.awaiting)
            if not text.strip():
                await self._not_understood()
                return
            if self.mode == "diag":
                await self.emit("diag_result", text=text)
                await self.set_state("ASKING")
                await self.say(text, "diag", after=lambda: self._diag_done())
                return
            mf = match_form(text)
            from .services.corrections import ADVICE
            if find_phrases(mf, ADVICE):
                await self.set_state("ASKING")
                await self.audit("advice_refused")
                await self.say(t("no_advice", self.language), "guardrail", cacheable=True)
                await self._reprompt()
                return
            aw = self.awaiting
            if aw in ("dictation",) or aw.startswith("field:"):
                await self._information_turn(text, expect=aw.split(":", 1)[1] if aw.startswith("field:") else None)
            elif aw == "id_suggestion":
                await self._id_suggestion_turn(text)
            elif aw.startswith("danger:"):
                await self._danger_confirm_turn(text, aw.split(":", 1)[1])
            elif aw in ("confirmation", "correction"):
                await self._confirmation_turn(text)
            else:
                await self._information_turn(text, expect=None)
            await self.persist()

    async def _diag_done(self):
        await self.set_state("IDLE")

    async def _not_understood(self) -> None:
        key = self.awaiting
        self.retries[key] = self.retries.get(key, 0) + 1
        await self.set_state("ASKING")
        if self.retries[key] > 2:
            # stop looping: leave the mic off; the worker taps to try again
            await self.say(t("not_understood", self.language), "question", cacheable=True)
            return
        await self.say(t("not_understood", self.language), "question", cacheable=True, awaiting_after=key,
                       after=lambda: self.start_listening(key, "auto"))

    async def _reprompt(self) -> None:
        aw = self.awaiting
        if aw in ("confirmation", "correction"):
            await self.say(t("confirm_q", self.language), "confirm_prompt", cacheable=True, awaiting_after=aw,
                           after=lambda: self._enter_confirming())
        else:
            await self.next_step()

    # ---------------------------------------------------------------- information
    async def _information_turn(self, text: str, expect: str | None) -> None:
        await self.set_state("EXTRACTING")
        today = self.today()
        llm_task = None
        if self.m.llm.enabled and expect is None:
            llm_task = asyncio.create_task(self.m.llm.extract(text, today.isoformat()))
            if self.s.ack_filler and self.mode != "demo":
                await self.say(t("ack", self.language), "ack", cacheable=True)
        t0 = time.monotonic()
        rx = RuleExtractor(self.registry())
        ex = rx.extract(text, today, expect=expect)
        await self.metric("rule_extraction_ms", (time.monotonic() - t0) * 1000)
        from .services.corrections import SKIP
        if expect and not ex.fields and find_phrases(match_form(text), SKIP):
            self.asked.add(expect)
            await self.set_state("VALIDATING")
            await self.set_state("SAFETY_CHECK")
            await self._run_danger(text)
            await self.say(t("skip_ok", self.language), "ack", cacheable=True)
            await self.next_step()
            return
        changed = self._apply(ex.fields, mode="info")
        if "ambiguous_name" in ex.notes:
            self.meta.setdefault("_notes", {})["ambiguous_name"] = True
        await self.set_state("VALIDATING")
        await self.set_state("SAFETY_CHECK")
        alerted = await self._run_danger(text)
        if llm_task is not None:
            try:
                llm_out = await llm_task
            except Exception:
                llm_out = None
            if self.m.llm.last_latency_ms is not None:
                await self.metric("llm_extraction_ms", self.m.llm.last_latency_ms)
            if llm_out:
                merged = merge(ex, llm_out, text)
                extra = {k: v for k, v in merged.fields.items()
                         if k not in ex.fields or merged.fields[k].confidence != ex.fields[k].confidence}
                changed += self._apply(extra, mode="info")
                await self.audit("llm_merge", reason=f"{len(extra)} fields")
        if expect and expect not in changed and not ex.fields:
            self.retries[f"field:{expect}"] = self.retries.get(f"field:{expect}", 0) + 1
            if self.retries[f"field:{expect}"] >= 2:
                self.asked.add(expect)
        self.draft_version += 1
        await self.send_draft(changed)
        _ = alerted
        await self.next_step()

    def _apply(self, fields: dict, mode: str) -> list[str]:
        """Apply FieldValues to the draft, keeping old values for undo."""
        group = []
        changed = []
        for name, fv in fields.items():
            if name not in self.record:
                continue
            old = self.record.get(name)
            new = fv.value
            if isinstance(old, list) and isinstance(new, list):
                # lists are merged, never silently replaced; removals are explicit ("OPV nahi diya")
                new = old + [x for x in new if x not in old]
            if old == new and (self.meta.get(name) or {}).get("confidence") == fv.confidence:
                continue
            group.append({"field": name, "old": old, "new": new, "old_meta": self.meta.get(name)})
            self.record[name] = new
            self.meta[name] = {"confidence": fv.confidence, "raw": fv.raw, "source": fv.source, "note": fv.note}
            changed.append(name)
        # vaccines cannot be both given and due: newest statement wins
        if "vaccinations_due" in changed:
            self.record["vaccinations_given"] = [v for v in self.record["vaccinations_given"]
                                                 if v not in self.record["vaccinations_due"]]
        elif "vaccinations_given" in changed:
            self.record["vaccinations_due"] = [v for v in self.record["vaccinations_due"]
                                               if v not in self.record["vaccinations_given"]]
        if group:
            self.history.append(group)
        return changed

    # ---------------------------------------------------------------- danger
    async def _run_danger(self, text: str) -> list[str]:
        t0 = time.monotonic()
        findings = danger_rules.evaluate(text, self.record.get("visit_type"))
        await self.metric("danger_rules_ms", (time.monotonic() - t0) * 1000)
        new_pos = []
        for f in findings:
            cur = self.danger.get(f.sign_id)
            if f.status == "POSITIVE":
                if not cur or cur["status"] != "POSITIVE":
                    self.danger[f.sign_id] = {**f.public(), "status": "POSITIVE"}
                    new_pos.append(f.sign_id)
                    if f.sign_id in self.pending_danger:
                        self.pending_danger.remove(f.sign_id)
            elif f.status == "UNCERTAIN":
                if not cur:
                    self.danger[f.sign_id] = {**f.public(), "status": "UNCERTAIN"}
                    if f.sign_id not in self.pending_danger:
                        self.pending_danger.append(f.sign_id)
            elif f.status == "NEGATED":
                if cur and cur["status"] == "POSITIVE":
                    # retraction after an alert is never silent: it becomes ANM review
                    cur["status"] = "REVIEW"
                    cur["reason"] = "worker negated a previously flagged sign; needs ANM review"
                    await self.audit("danger_retracted_review", reason=f.sign_id)
                elif not cur:
                    self.danger[f.sign_id] = {**f.public(), "status": "NEGATED"}
            await self.audit(f"danger_{f.status.lower()}", reason=f.sign_id)
        if new_pos:
            await self._alert(new_pos)
        return new_pos

    async def _alert(self, sign_ids: list[str]) -> None:
        """Immediate fixed-protocol referral: does NOT wait for record confirmation."""
        await self.set_state("ALERTING")
        signs = [self.danger[s] for s in sign_ids]
        labels = [s["label"].get(self.language, s["label"]["en"]) for s in signs]
        subject = "baby" if all(s.get("subject") == "baby" for s in signs) else "mother"
        text = t("danger_alert_baby" if subject == "baby" else "danger_alert_mother", self.language,
                 signs=join_list(labels, self.language))
        await self.emit("danger_alert", signs=signs, referral_status="REFER_NOW", message=text,
                        source="MCP Card 2018 (MoHFW & MoWCD) and its 2018 Guidebook")
        await self.audit("referral_alert", reason=",".join(sign_ids))
        await self.say(text, "alert", speed=0.95)

    async def _danger_confirm_turn(self, text: str, sign_id: str) -> None:
        intent = classify(text, self.today(), RuleExtractor(self.registry()))
        target = DANGER_REDIRECT.get((sign_id, self.record.get("visit_type")), sign_id)
        # the answer itself may contain a clear positive/negative danger statement
        await self.set_state("SAFETY_CHECK")
        alerted = await self._run_danger(text)
        if sign_id in self.pending_danger:
            self.pending_danger.remove(sign_id)
        entry = self.danger.get(sign_id) or {}
        if alerted:
            pass
        elif intent.kind == "YES":
            sign = danger_rules.sign_by_id(target)
            self.danger.pop(sign_id, None) if target != sign_id else None
            self.danger[target] = {"id": target, "status": "POSITIVE", "matched_phrase": entry.get("matched_phrase", ""),
                                   "reason": "confirmed by the worker", "label": sign.label, "source_ref": sign.source_ref,
                                   "subject": sign.subject, "rule_id": f"RULE_{target}"}
            await self.audit("danger_confirmed", reason=target)
            await self._alert([target])
        elif intent.kind == "NO":
            entry["status"] = "NEGATED"
            entry["reason"] = "worker answered no"
            self.danger[sign_id] = entry
            await self.audit("danger_denied", reason=sign_id)
            await self.say(t("danger_not_flagged", self.language), "ack", cacheable=True)
        else:
            n = self.retries.get(f"danger:{sign_id}", 0) + 1
            self.retries[f"danger:{sign_id}"] = n
            if n < 2:
                self.pending_danger.insert(0, sign_id)
            else:
                entry["status"] = "REVIEW"
                entry["reason"] = "could not be confirmed by voice"
                self.danger[sign_id] = entry
                await self.audit("danger_review", reason=sign_id)
                await self.say(t("danger_review", self.language), "ack", cacheable=True)
        self.draft_version += 1
        await self.send_draft()
        await self.next_step()

    # ---------------------------------------------------------------- id suggestion
    async def _id_suggestion_turn(self, text: str) -> None:
        intent = classify(text, self.today(), RuleExtractor(self.registry()), expect="beneficiary_id")
        sug = self.id_suggestion or {}
        self.id_suggestion = None
        if intent.kind == "YES" and sug:
            self._apply({"beneficiary_id": FieldValue(sug["id"], "", "high", source="register",
                                                      note="confirmed by voice from the register match")}, "info")
            await self.audit("id_from_register_confirmed", field_name_="beneficiary_id")
        elif intent.kind == "PATCH":
            self._apply(intent.patch, "info")
        else:
            self.asked.add("_id_suggestion")
        self.draft_version += 1
        await self.send_draft(["beneficiary_id"])
        await self.next_step()

    # ---------------------------------------------------------------- next step
    async def next_step(self) -> None:
        lang = self.language
        while self.pending_danger:
            sid = self.pending_danger[0]
            d = self.danger.get(sid)
            if not d or d["status"] != "UNCERTAIN":
                self.pending_danger.pop(0)
                continue
            target = DANGER_REDIRECT.get((sid, self.record.get("visit_type")), sid)
            sign = danger_rules.sign_by_id(target)
            label = sign.label.get(lang, sign.label["en"]) if sign else sid
            await self._ask(t("danger_confirm_q", lang, sign=label), f"danger:{sid}")
            return
        notes = self.meta.get("_notes", {})
        if notes.get("ambiguous_name") and not self.record.get("beneficiary_id") and "beneficiary_id" not in self.asked:
            self.asked.add("beneficiary_id")
            notes.pop("ambiguous_name", None)
            await self._ask(t("ask_name_ambiguous", lang, name=self.record.get("beneficiary_name") or ""),
                            "field:beneficiary_id")
            return
        if not self.record.get("beneficiary_id") and self.record.get("beneficiary_name") \
                and "_id_suggestion" not in self.asked:
            matches = [r for r in self.registry() if r["name"] == self.record["beneficiary_name"]]
            if len(matches) == 1:
                self.asked.add("_id_suggestion")
                from .services.numbers import speak_digits
                self.id_suggestion = {"id": matches[0]["synthetic_external_id"]}
                await self._ask(t("ask_id_suggest", lang, digits=speak_digits(matches[0]["synthetic_external_id"], lang),
                                  name=matches[0]["name"]), "id_suggestion")
                return
        missing = validation.missing_to_ask(self.record, self.asked)
        if missing:
            self.asked.add(missing)
            await self._ask(t(f"ask_{missing}", lang), f"field:{missing}")
            return
        await self._readback()

    async def _ask(self, text: str, awaiting: str) -> None:
        if self.state != "ASKING":
            await self.set_state("ASKING")
        self.awaiting = awaiting
        await self.emit("ask", awaiting=awaiting, text=text)
        await self.say(text, "question", cacheable=not any(ch.isdigit() for ch in text) and awaiting.startswith("field:"),
                       awaiting_after=awaiting, after=lambda: self.start_listening(awaiting, "auto"))

    async def _readback(self) -> None:
        await self.set_state("READBACK")
        self.awaiting = "confirmation"
        self.last_read_field = None
        meta = dict(self.meta)
        meta["_today"] = self.today().isoformat()
        labels = [d["label"].get(self.language, d["label"]["en"]) for d in self.danger.values()
                  if d["status"] == "POSITIVE"]
        text = readback_text(self.record, meta, self.language, labels)
        slow = any((self.meta.get(f) or {}).get("confidence") == "confirm" for f in FIELD_ORDER)
        await self.emit("readback", text=text)
        await self.say(text, "readback", speed=0.92 if slow else None, awaiting_after="confirmation",
                       after=lambda: self._enter_confirming())

    async def _enter_confirming(self) -> None:
        if self.state in ("READBACK", "ASKING", "ALERTING", "CORRECTING"):
            await self.set_state("CONFIRMING")
        if self.state == "CONFIRMING":
            await self.start_listening("confirmation" if self.awaiting != "correction" else "correction", "auto")

    # ---------------------------------------------------------------- confirmation / correction
    async def _confirmation_turn(self, text: str) -> None:
        intent = classify(text, self.today(), RuleExtractor(self.registry()))
        await self.set_state("SAFETY_CHECK")
        alerted = await self._run_danger(text)
        lang = self.language
        if intent.kind == "YES" and self.awaiting == "confirmation" and not alerted:
            await self.set_state("CONFIRMING")
            await self.save(via="voice")
            return
        if intent.kind == "PATCH":
            await self.set_state("CORRECTING")
            patch = dict(intent.patch)
            changed = self._apply(patch, mode="replace")
            if intent.remove_given:
                before = list(self.record["vaccinations_given"])
                self.record["vaccinations_given"] = [v for v in before
                                                     if v.split("-")[0].split(" booster")[0] not in intent.remove_given]
                if before != self.record["vaccinations_given"]:
                    self.history.append([{"field": "vaccinations_given", "old": before,
                                          "new": self.record["vaccinations_given"], "old_meta": self.meta.get("vaccinations_given")}])
                    changed.append("vaccinations_given")
            for f in changed:
                # the worker said it deliberately; validation below re-flags anything implausible
                self.meta.setdefault(f, {})["confidence"] = "high"
                self.meta[f]["corrected"] = True
                await self.audit("field_corrected", field_name_=f)
            self.draft_version += 1
            await self.send_draft(changed)
            if not changed:
                await self._ask_which_field()
                return
            self.last_read_field = changed[0] if len(changed) == 1 else None
            phrases = [field_phrase(f, self.record.get(f), lang, self.record) for f in changed
                       if f != "beneficiary_name" or len(changed) == 1]
            await self._corrected_reply(phrases, "corrected")
            return
        if intent.kind == "BARE":
            target = bare_target(intent.bare_value, self.last_read_field, self.record)
            if target:
                await self.set_state("CORRECTING")
                value = str(int(intent.bare_value)) if target == "beneficiary_id" else round(float(intent.bare_value), 3)
                changed = self._apply({target: FieldValue(value, str(intent.bare_value), "high",
                                                          note="corrected by voice")}, "replace")
                self.meta.setdefault(target, {})["corrected"] = True
                await self.audit("field_corrected", field_name_=target, reason="bare_value_last_field")
                self.draft_version += 1
                await self.send_draft(changed)
                await self._corrected_reply([field_phrase(target, self.record[target], lang)], "corrected")
            else:
                await self._ask_which_field()
            return
        if intent.kind == "UNDO":
            await self._undo_and_reply()
            return
        if intent.kind == "REPEAT":
            await self._readback()
            return
        if intent.kind == "NO" or (intent.kind == "YES" and self.awaiting == "correction"):
            # "correction" context + a bare field name ("weight") -> ask that field
            for f, words in FIELD_WORDS.items():
                if find_phrases(match_form(text), [match_form(w) for w in words]):
                    self.asked.discard(f)
                    await self._ask(t(f"ask_{f}", lang) if f in ("beneficiary_id", "visit_type", "weight_kg",
                                                                  "next_visit_date") else t("ask_which_field", lang),
                                    f"field:{f}" if f in ("beneficiary_id", "visit_type", "weight_kg", "next_visit_date")
                                    else "correction")
                    return
            await self._ask_which_field()
            return
        if alerted:
            await self._reprompt()
            return
        await self.set_state("ASKING")
        await self.say(t("not_understood", lang), "question", cacheable=True)
        await self.say(t("confirm_q", lang), "confirm_prompt", cacheable=True, awaiting_after=self.awaiting,
                       after=lambda: self._enter_confirming())

    async def _ask_which_field(self) -> None:
        await self._ask(t("ask_which_field", self.language), "correction")

    async def _corrected_reply(self, phrases: list[str], key: str) -> None:
        lang = self.language
        if self.state not in ("CORRECTING", "READBACK"):
            await self.set_state("CORRECTING")
        await self.set_state("READBACK")
        self.awaiting = "confirmation"
        text = t(key, lang, phrase=". ".join(phrases)) + " " + t("now_correct_q", lang)
        await self.say(text, "correction_ack", awaiting_after="confirmation", after=lambda: self._enter_confirming())

    async def _undo_and_reply(self) -> None:
        lang = self.language
        if not self.history:
            if self.state not in ("ASKING",):
                with contextlib.suppress(Exception):
                    await self.set_state("ASKING")
            await self.say(t("nothing_to_undo", lang), "ack", cacheable=True)
            await self.say(t("confirm_q", lang), "confirm_prompt", cacheable=True, awaiting_after="confirmation",
                           after=lambda: self._enter_confirming())
            self.awaiting = "confirmation"
            return
        group = self.history.pop()
        restored = []
        for ch in reversed(group):
            self.record[ch["field"]] = ch["old"]
            if ch.get("old_meta") is None:
                self.meta.pop(ch["field"], None)
            else:
                self.meta[ch["field"]] = ch["old_meta"]
            restored.append(ch["field"])
        await self.audit("undo", field_name_=",".join(restored))
        self.draft_version += 1
        await self.send_draft(restored)
        self.last_read_field = restored[0] if len(restored) == 1 else None
        if self.state not in ("CORRECTING",):
            with contextlib.suppress(Exception):
                await self.set_state("CORRECTING")
        await self._corrected_reply([field_phrase(f, self.record.get(f), lang) for f in restored
                                     if f != "beneficiary_name"] or [t("nothing_to_undo", lang)], "undo_done")

    # ================================================================== save
    async def save(self, via: str) -> None:
        lang = self.language
        if self.saved_visit_id:
            await self.emit("saved", visit_id=self.saved_visit_id, duplicate=True)
            return
        if not validation.can_save(self.record):
            await self.say(t("need_id_before_save", lang), "question", cacheable=True)
            self.asked.discard("beneficiary_id")
            self.asked.discard("visit_type")
            if self.state == "CONFIRMING":
                await self.set_state("ASKING")
            await self.next_step()
            return
        if not await self.set_state("SAVING"):
            return
        today = self.today()
        record = dict(self.record)
        record["session_id"] = self.id
        if not record.get("visit_date"):
            record["visit_date"] = today.isoformat()
            self.meta["visit_date"] = {"confidence": "system", "source": "system",
                                       "note": "date of recording (not spoken)"}
        record["danger_signs"] = [k for k, v in self.danger.items() if v["status"] == "POSITIVE"]
        record["danger_review"] = [k for k, v in self.danger.items() if v["status"] in ("REVIEW", "UNCERTAIN")]
        record["danger_details"] = list(self.danger.values())
        record["referral_status"] = self.referral_status()
        record["field_confidence"] = {k: (v or {}).get("confidence") for k, v in self.meta.items()
                                      if not k.startswith("_")}
        record["field_evidence"] = {k: (v or {}).get("raw") for k, v in self.meta.items() if not k.startswith("_")}
        record["confirmation_status"] = "CONFIRMED"
        record["confirmed_via"] = via
        record["language"] = self.language
        record["created_at"] = self.created_at
        record["transcript"] = [x for x in self.transcript_log if x.get("role") == "worker"]
        fus = followups_svc.generate(record, today)
        key = f"{self.id}:{self.draft_version}"
        try:
            visit_id, created = await asyncio.to_thread(
                self.m.db.save_visit, record=record, idempotency_key=key, session_id=self.id,
                source="demo" if self.mode == "demo" else "live", followups=fus)
        except Exception as exc:
            log.warning("save failed: %s", type(exc).__name__)
            await self.set_state("PENDING")
            await self.audit("save_failed", reason=type(exc).__name__)
            await self.emit("save_failed", reason="database_error", draft=self.snapshot())
            await self.say(t("save_failed", lang), "error", cacheable=True)
            return
        self.saved_visit_id = visit_id
        await self.audit("visit_saved", reason=f"{via}:{'created' if created else 'duplicate'}")
        await self.set_state("SUMMARY")
        await self.persist()
        saved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        await self.emit("saved", visit_id=visit_id, saved_at=saved_at, created=created, record=record,
                        followups=fus, referral_status=record["referral_status"])
        await self.say(t("saved", lang, actions=followups_svc.spoken_summary(fus, lang, record)), "summary")


class SessionManager:
    def __init__(self, settings: Settings, db: Database, *, stt_connect: ConnectFn | None = None,
                 tts_connect: ConnectFn | None = None):
        self.settings = settings
        self.db = db
        self.credentials = CredentialManager(settings, usage_sink=db.add_usage)
        self.tts_cache = TTSCache(settings.tts_cache_dir)
        self.llm = GeminiExtractor(settings)
        self.stt_connect = stt_connect
        self.tts_connect = tts_connect
        self.sessions: dict[str, VisitSession] = {}
        self.registry_cache: list[dict] = db.registry()
        self.registry_ids = {r["synthetic_external_id"] for r in self.registry_cache}

    def refresh_registry(self):
        self.registry_cache = self.db.registry()
        self.registry_ids = {r["synthetic_external_id"] for r in self.registry_cache}

    def create(self, language: str, mode: str) -> tuple[VisitSession, str]:
        sid = str(uuid.uuid4())
        token = secrets.token_urlsafe(24)
        sess = VisitSession(manager=self, session_id=sid, token_hash_=token_hash(token), language=language, mode=mode)
        self.sessions[sid] = sess
        self.db.save_session(sid, token, language, mode, "IDLE", sess._draft(), self.settings.session_ttl_minutes)
        return sess, token

    def get(self, session_id: str, token: str) -> VisitSession | None:
        if not token:
            return None
        th = token_hash(token)
        sess = self.sessions.get(session_id)
        if sess is not None:
            return sess if secrets.compare_digest(sess.token_hash, th) else None
        row = self.db.load_session(session_id)  # restore after backend restart
        if not row or not secrets.compare_digest(row["token_hash"], th):
            return None
        draft = row["draft"] or {}
        sess = VisitSession(manager=self, session_id=session_id, token_hash_=row["token_hash"],
                            language=row["language"], mode=row["mode"], draft=draft)
        st = draft.get("state") or row["state"]
        sess.state = st if st in ("SUMMARY", "PENDING") else ("CONFIRMING" if draft.get("record") else "IDLE")
        self.sessions[session_id] = sess
        return sess

    def drop(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
