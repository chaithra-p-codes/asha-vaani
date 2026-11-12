/** Adaptive energy VAD on 32 ms frames (RMS 0..1). Used for the level meter, the
 * end-of-speech timestamp (time-to-first-audio metric) and barge-in detection. */
export class ClientVAD {
  floor = 0.004;
  run = 0;
  silenceRun = 0;
  lastVoiceAt = 0;

  constructor(private minThreshold = 0.012, private ratio = 3.2) {}

  threshold(strict = false): number {
    return strict ? Math.max(0.03, this.floor * 4.5) : Math.max(this.minThreshold, this.floor * this.ratio);
  }

  /** Returns true when the frame counts as voice. */
  update(rms: number, strict = false, now = performance.now()): boolean {
    const voiced = rms > this.threshold(strict);
    if (voiced) {
      this.run += 1;
      this.silenceRun = 0;
      this.lastVoiceAt = now;
    } else {
      this.run = 0;
      this.silenceRun += 1;
      this.floor = Math.min(0.05, Math.max(0.0005, 0.95 * this.floor + 0.05 * rms));
    }
    return voiced;
  }
}

/** Fixed-size ring buffer of recent frames (pre-roll sent after a barge-in). */
export class FrameRing {
  private buf: ArrayBuffer[] = [];
  constructor(private size = 10) {}
  push(f: ArrayBuffer): void {
    this.buf.push(f);
    if (this.buf.length > this.size) this.buf.shift();
  }
  drain(): ArrayBuffer[] {
    const out = this.buf;
    this.buf = [];
    return out;
  }
}
