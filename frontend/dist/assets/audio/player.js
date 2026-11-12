/** Gapless playback of streamed Timbre PCM16 chunks, per utterance, with instant stop. */
import { audioContext } from "./audioContext.js";
export function pcm16ToFloat32(bytes, offset = 0) {
    const view = new DataView(bytes, offset);
    const n = Math.floor(view.byteLength / 2);
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++)
        out[i] = view.getInt16(i * 2, true) / 32768;
    return out;
}
export class PcmPlayer {
    constructor() {
        this.utts = new Map();
        this.nextTime = 0;
        this.onStarted = () => { };
        this.onEnded = () => { };
    }
    get playing() {
        for (const u of this.utts.values())
            if (u.pending > 0)
                return true;
        return false;
    }
    begin(uid, sampleRate) {
        if (!this.utts.has(uid))
            this.utts.set(uid, { sampleRate, pending: 0, ended: false, started: false, sources: [], carry: [] });
    }
    push(uid, data, offset) {
        const u = this.utts.get(uid);
        if (!u)
            return;
        const ctx = audioContext();
        const samples = pcm16ToFloat32(data, offset);
        if (samples.length === 0)
            return;
        const buffer = ctx.createBuffer(1, samples.length, u.sampleRate);
        buffer.getChannelData(0).set(samples);
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        src.connect(ctx.destination);
        const startAt = Math.max(ctx.currentTime + 0.04, this.nextTime);
        src.start(startAt);
        this.nextTime = startAt + buffer.duration;
        u.pending += 1;
        u.sources.push(src);
        if (!u.started) {
            u.started = true;
            const delayMs = Math.max(0, (startAt - ctx.currentTime) * 1000);
            window.setTimeout(() => this.onStarted(uid, performance.now()), delayMs);
        }
        src.onended = () => {
            u.pending -= 1;
            this.maybeEnd(uid);
        };
    }
    end(uid) {
        const u = this.utts.get(uid);
        if (!u) {
            this.onEnded(uid);
            return;
        }
        u.ended = true;
        this.maybeEnd(uid);
    }
    maybeEnd(uid) {
        const u = this.utts.get(uid);
        if (u && u.ended && u.pending <= 0) {
            this.utts.delete(uid);
            this.onEnded(uid);
        }
    }
    /** Stop everything immediately (barge-in). Returns interrupted utterance ids. */
    stopAll() {
        const ids = [];
        for (const [uid, u] of this.utts) {
            ids.push(uid);
            for (const s of u.sources) {
                s.onended = null;
                try {
                    s.stop();
                }
                catch { /* already stopped */ }
            }
        }
        this.utts.clear();
        this.nextTime = 0;
        return ids;
    }
    drop(uids) {
        for (const uid of uids) {
            const u = this.utts.get(uid);
            if (!u)
                continue;
            for (const s of u.sources) {
                s.onended = null;
                try {
                    s.stop();
                }
                catch { /* ignore */ }
            }
            this.utts.delete(uid);
        }
    }
}
