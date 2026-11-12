"""Audio helpers: Prisma framing (16 kHz, s16le, mono, 512 samples = 1024 bytes),
energy-based VAD used for turn endpointing, and small PCM utilities."""
from __future__ import annotations

import math
import sys
from array import array

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
FRAME_BYTES = FRAME_SAMPLES * 2  # 1024 bytes, 32 ms at 16 kHz
FRAME_MS = FRAME_SAMPLES * 1000 / SAMPLE_RATE  # 32.0


def silence(ms: int) -> bytes:
    """Return PCM16 silence of the requested duration, rounded up to whole frames."""
    frames = max(1, math.ceil(ms / FRAME_MS))
    return bytes(FRAME_BYTES * frames)


def frame_rms(frame: bytes) -> float:
    """RMS of a little-endian PCM16 buffer (0..32768)."""
    if len(frame) < 2:
        return 0.0
    samples = array("h")
    samples.frombytes(frame[: len(frame) - (len(frame) % 2)])
    if sys.byteorder != "little":  # pragma: no cover
        samples.byteswap()
    if not samples:
        return 0.0
    acc = 0
    for s in samples:
        acc += s * s
    return math.sqrt(acc / len(samples))


class Rechunker:
    """Accepts arbitrary-length PCM16 byte strings and emits exact 1024-byte frames."""

    def __init__(self, frame_bytes: int = FRAME_BYTES):
        self.frame_bytes = frame_bytes
        self._buf = bytearray()

    def push(self, data: bytes) -> list[bytes]:
        self._buf.extend(data)
        out = []
        while len(self._buf) >= self.frame_bytes:
            out.append(bytes(self._buf[: self.frame_bytes]))
            del self._buf[: self.frame_bytes]
        return out

    def flush(self) -> bytes | None:
        """Pad any remainder with silence to a whole frame."""
        if not self._buf:
            return None
        frame = bytes(self._buf) + bytes(self.frame_bytes - len(self._buf))
        self._buf.clear()
        return frame


class EnergyVAD:
    """Adaptive energy VAD. Used only to decide *turn* endpoints (when the worker has
    finished speaking); Gnani Prisma's own server-side VAD still segments the speech."""

    def __init__(self, min_rms: float = 450.0, ratio: float = 2.6, hang_frames: int = 3):
        self.noise_floor = 250.0
        self.min_rms = min_rms
        self.ratio = ratio
        self.hang_frames = hang_frames
        self._hang = 0
        self.speech_frames = 0
        self.is_speech = False

    def threshold(self) -> float:
        return max(self.min_rms, self.noise_floor * self.ratio)

    def update(self, rms: float) -> bool:
        voiced = rms > self.threshold()
        if voiced:
            self._hang = self.hang_frames
            self.speech_frames += 1
        else:
            if self._hang > 0:
                self._hang -= 1
            # adapt the floor only on non-speech frames, slowly, and clamp
            self.noise_floor = min(4000.0, 0.95 * self.noise_floor + 0.05 * rms)
        self.is_speech = voiced or self._hang > 0
        return self.is_speech


def pcm16_duration_ms(nbytes: int, sample_rate: int) -> float:
    return (nbytes / 2) * 1000.0 / sample_rate


def wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap PCM16 mono in a WAV header (used by verification scripts)."""
    import struct

    data_len = len(pcm)
    header = b"RIFF" + struct.pack("<I", 36 + data_len) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", data_len)
    return header + pcm
