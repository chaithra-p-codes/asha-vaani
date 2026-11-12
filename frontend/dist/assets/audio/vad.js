/** Adaptive energy VAD on 32 ms frames (RMS 0..1). Used for the level meter, the
 * end-of-speech timestamp (time-to-first-audio metric) and barge-in detection. */
export class ClientVAD {
    constructor(minThreshold = 0.012, ratio = 3.2) {
        this.minThreshold = minThreshold;
        this.ratio = ratio;
        this.floor = 0.004;
        this.run = 0;
        this.silenceRun = 0;
        this.lastVoiceAt = 0;
    }
    threshold(strict = false) {
        return strict ? Math.max(0.03, this.floor * 4.5) : Math.max(this.minThreshold, this.floor * this.ratio);
    }
    /** Returns true when the frame counts as voice. */
    update(rms, strict = false, now = performance.now()) {
        const voiced = rms > this.threshold(strict);
        if (voiced) {
            this.run += 1;
            this.silenceRun = 0;
            this.lastVoiceAt = now;
        }
        else {
            this.run = 0;
            this.silenceRun += 1;
            this.floor = Math.min(0.05, Math.max(0.0005, 0.95 * this.floor + 0.05 * rms));
        }
        return voiced;
    }
}
/** Fixed-size ring buffer of recent frames (pre-roll sent after a barge-in). */
export class FrameRing {
    constructor(size = 10) {
        this.size = size;
        this.buf = [];
    }
    push(f) {
        this.buf.push(f);
        if (this.buf.length > this.size)
            this.buf.shift();
    }
    drain() {
        const out = this.buf;
        this.buf = [];
        return out;
    }
}
