/*
 * ASHA Vaani microphone capture worklet.
 * Input: mono Float32 at the AudioContext rate (usually 48 kHz on Android).
 * Output (to main thread): exact Prisma frames - 512 samples of PCM s16le at 16 kHz
 * (1024 bytes, 32 ms) - plus the frame RMS (0..1) for VAD / level meter.
 * Resampling: box-filter anti-aliasing + linear interpolation (adequate for speech).
 */
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.inRate = opts.inputSampleRate || sampleRate;
    this.outRate = 16000;
    this.ratio = this.inRate / this.outRate;
    this.frameSamples = 512;
    this.out = new Int16Array(this.frameSamples);
    this.outIdx = 0;
    this.pos = 0; // fractional read position into the low-passed input stream
    this.prev = 0; // previous filtered sample (for interpolation across blocks)
    this.acc = 0;
    this.taps = Math.max(1, Math.round(this.ratio));
    this.hist = new Float32Array(this.taps);
    this.histIdx = 0;
    this.sumSq = 0;
  }

  lowpass(x) {
    // moving-average over `taps` samples (box filter) - removes most energy above ~8 kHz
    this.acc += x - this.hist[this.histIdx];
    this.hist[this.histIdx] = x;
    this.histIdx = (this.histIdx + 1) % this.taps;
    return this.acc / this.taps;
  }

  emit(sample) {
    const s = Math.max(-1, Math.min(1, sample));
    this.out[this.outIdx++] = s < 0 ? s * 0x8000 : s * 0x7fff;
    this.sumSq += s * s;
    if (this.outIdx === this.frameSamples) {
      const rms = Math.sqrt(this.sumSq / this.frameSamples);
      const buf = this.out.buffer.slice(0);
      this.port.postMessage({ frame: buf, rms }, [buf]);
      this.outIdx = 0;
      this.sumSq = 0;
    }
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const ch0 = input[0];
    if (!ch0) return true;
    const n = ch0.length;
    for (let i = 0; i < n; i++) {
      let x = ch0[i];
      if (input.length > 1 && input[1]) x = 0.5 * (x + input[1][i]); // downmix to mono
      const y = this.lowpass(x);
      // emit every output sample whose position falls between prev (t=-1) and y (t=0)
      while (this.pos <= 1) {
        const frac = this.pos;
        this.emit(this.prev + (y - this.prev) * frac);
        this.pos += this.ratio;
      }
      this.pos -= 1;
      this.prev = y;
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);
