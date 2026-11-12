"""Explicit conversation states (build plan 2.2) and the allowed transitions.
`awaiting` (kept by the session) says what the next utterance answers; the state says
which step of the pipeline is running. Invalid transitions are rejected and reported."""
from __future__ import annotations

STATES = ("IDLE", "CONNECTING", "LISTENING", "TRANSCRIBING", "EXTRACTING", "VALIDATING", "SAFETY_CHECK",
          "ALERTING", "ASKING", "READBACK", "CORRECTING", "CONFIRMING", "SAVING", "SUMMARY", "RECOVERY",
          "RECONNECTING", "PENDING")

_ANY_SPEECH_PHASE = {"ALERTING", "ASKING", "READBACK", "CONFIRMING"}

ALLOWED: dict[str, set[str]] = {
    "IDLE": {"CONNECTING", "LISTENING", "RECOVERY", "PENDING", "READBACK", "ASKING", "CONFIRMING"},
    "CONNECTING": {"IDLE", "LISTENING", "RECOVERY"},
    "LISTENING": {"TRANSCRIBING", "IDLE", "RECOVERY", "RECONNECTING"} | _ANY_SPEECH_PHASE,
    "TRANSCRIBING": {"EXTRACTING", "CORRECTING", "SAVING", "LISTENING", "IDLE", "RECOVERY", "SAFETY_CHECK"}
                    | _ANY_SPEECH_PHASE,
    "EXTRACTING": {"VALIDATING", "RECOVERY", "ALERTING"},
    "VALIDATING": {"SAFETY_CHECK", "ASKING"},
    "SAFETY_CHECK": {"ALERTING", "ASKING", "READBACK", "CONFIRMING", "CORRECTING"},
    "ALERTING": {"ASKING", "READBACK", "LISTENING", "CONFIRMING", "SUMMARY", "EXTRACTING", "VALIDATING",
                 "SAFETY_CHECK", "RECOVERY", "IDLE", "CORRECTING"},
    "ASKING": {"LISTENING", "IDLE", "READBACK", "RECOVERY", "ALERTING", "CONFIRMING"},
    "READBACK": {"CONFIRMING", "LISTENING", "CORRECTING", "ALERTING", "RECOVERY", "IDLE"},
    "CORRECTING": {"READBACK", "ASKING", "CONFIRMING", "SAFETY_CHECK", "ALERTING"},
    "CONFIRMING": {"LISTENING", "SAVING", "CORRECTING", "READBACK", "ASKING", "RECOVERY", "ALERTING",
                   "PENDING"},
    "SAVING": {"SUMMARY", "PENDING", "CONFIRMING"},
    "SUMMARY": {"IDLE"},
    "RECOVERY": {"RECONNECTING", "PENDING", "IDLE", "CONFIRMING", "READBACK"},
    "RECONNECTING": {"IDLE", "LISTENING", "CONFIRMING", "READBACK", "RECOVERY", "PENDING", "ASKING"},
    "PENDING": {"RECONNECTING", "CONFIRMING", "SAVING", "IDLE", "READBACK"},
}


class InvalidTransition(Exception):
    pass


def check(current: str, new: str) -> None:
    if new == current:
        return
    if new not in STATES:
        raise InvalidTransition(f"unknown state {new}")
    if new not in ALLOWED.get(current, set()):
        raise InvalidTransition(f"{current} -> {new} is not allowed")
