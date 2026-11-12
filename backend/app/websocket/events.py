"""Application WebSocket protocol (browser <-> backend).

Binary frames  client->server : raw PCM s16le mono 16 kHz audio (any length; backend
                                re-chunks to Prisma's 1024-byte frames). Audio only.
Binary frames  server->client : [0x01][uint32 LE utterance_id][PCM16 mono @ tts_sample_rate]
Text frames                   : JSON control events, validated below. Every server event
                                carries `type`, `session_id`, `seq` (monotonic) and `ts`.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")
    seq: Optional[int] = None


class Hello(_Base):
    type: Literal["hello"]
    client: str = Field(default="pwa", max_length=40)
    resume: bool = False


class StartListening(_Base):
    type: Literal["start_listening"]
    reason: Literal["user", "barge_in", "auto"] = "user"


class StopListening(_Base):
    type: Literal["stop_listening"]


class BargeIn(_Base):
    type: Literal["barge_in"]


class CancelTTS(_Base):
    type: Literal["cancel_tts"]


class PlaybackStarted(_Base):
    type: Literal["playback_started"]
    utterance_id: int


class PlaybackEnded(_Base):
    type: Literal["playback_ended"]
    utterance_id: int
    interrupted: bool = False


class ClientMetric(_Base):
    type: Literal["client_metric"]
    name: Literal["client_ttfa_ms", "client_first_audio_ms", "mic_open_ms"]
    value_ms: float = Field(ge=0, le=120000)


class ButtonAction(_Base):
    """Accessible fallbacks for the voice flow (never required for the primary flow)."""
    type: Literal["action"]
    action: Literal["confirm", "undo", "repeat", "skip", "new_visit", "dismiss_alert", "retry_save"]


class DemoUtterance(_Base):
    """Only accepted in the clearly-labelled DEMO mode (Layer-4 fallback)."""
    type: Literal["demo_utterance"]
    text: str = Field(min_length=1, max_length=600)


class Ping(_Base):
    type: Literal["ping"]


CLIENT_EVENTS = {
    "hello": Hello, "start_listening": StartListening, "stop_listening": StopListening, "barge_in": BargeIn,
    "cancel_tts": CancelTTS, "playback_started": PlaybackStarted, "playback_ended": PlaybackEnded,
    "client_metric": ClientMetric, "action": ButtonAction, "demo_utterance": DemoUtterance, "ping": Ping,
}


def parse_client_event(data: dict):
    """Return a validated event model, or raise ValueError with a safe message."""
    if not isinstance(data, dict):
        raise ValueError("event must be a JSON object")
    etype = data.get("type")
    model = CLIENT_EVENTS.get(etype)
    if model is None:
        raise ValueError(f"unknown event type: {str(etype)[:40]}")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"invalid {etype} event: {exc.errors()[0].get('msg', 'bad payload')}") from None


AUDIO_FRAME_TAG = 0x01
