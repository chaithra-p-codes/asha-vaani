// Frontend unit tests (Node's built-in test runner; run `npm test` after `npm install`).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.document = { documentElement: {} };

function loadWorklet(inputRate) {
  const src = readFileSync(join(root, "public/audio/pcm-capture-worklet.js"), "utf8");
  let Klass = null;
  const posted = [];
  const ctx = {
    sampleRate: inputRate,
    AudioWorkletProcessor: class { constructor() { this.port = { postMessage: (m) => posted.push(m) }; } },
    registerProcessor: (_name, k) => { Klass = k; },
  };
  vm.runInNewContext(src, ctx);
  const proc = new Klass({ processorOptions: { inputSampleRate: inputRate } });
  return { proc, posted };
}

test("worklet emits exact Prisma frames: 512 samples PCM16 @16 kHz from 48 kHz input", () => {
  const { proc, posted } = loadWorklet(48000);
  const block = 128;
  const seconds = 1;
  let k = 0;
  for (let b = 0; b < (48000 * seconds) / block; b++) {
    const ch = new Float32Array(block);
    for (let i = 0; i < block; i++, k++) ch[i] = 0.5 * Math.sin((2 * Math.PI * 440 * k) / 48000);
    proc.process([[ch]]);
  }
  // 1 s at 16 kHz = 16000 samples = 31.25 frames
  assert.ok(posted.length === 31 || posted.length === 32, `frames=${posted.length}`);
  for (const m of posted) assert.equal(m.frame.byteLength, 1024);
  const pcm = new Int16Array(posted[10].frame);
  // count zero crossings: 440 Hz over 32 ms ~= 28 crossings
  let zc = 0;
  for (let i = 1; i < pcm.length; i++) if ((pcm[i - 1] < 0) !== (pcm[i] < 0)) zc++;
  assert.ok(zc > 22 && zc < 34, `zero crossings ${zc}`);
  assert.ok(posted[10].rms > 0.25 && posted[10].rms < 0.4, `rms ${posted[10].rms}`);
});

test("worklet handles 44.1 kHz and stereo input", () => {
  const { proc, posted } = loadWorklet(44100);
  for (let b = 0; b < 400; b++) proc.process([[new Float32Array(128).fill(0.1), new Float32Array(128).fill(0.3)]]);
  const expected = Math.floor(((400 * 128) / 44100) * 16000 / 512);
  assert.ok(Math.abs(posted.length - expected) <= 1);
  const pcm = new Int16Array(posted[2].frame);
  assert.ok(Math.abs(pcm[100] - Math.round(0.2 * 32767)) < 50, `downmixed value ${pcm[100]}`);
});

test("client VAD adapts to noise and detects speech runs; ring buffer keeps last frames", async () => {
  const { ClientVAD, FrameRing } = await import(join(root, "dist/assets/audio/vad.js"));
  const v = new ClientVAD();
  for (let i = 0; i < 50; i++) v.update(0.01, false, i);
  assert.ok(v.floor > 0.005 && v.floor < 0.011);
  assert.equal(v.update(0.008), false);
  for (let i = 0; i < 8; i++) v.update(0.2, true, 100 + i);
  assert.equal(v.run, 8);
  const r = new FrameRing(3);
  for (let i = 0; i < 5; i++) r.push(new ArrayBuffer(i + 1));
  assert.deepEqual(r.drain().map((b) => b.byteLength), [3, 4, 5]);
});

test("PCM16 little-endian decode for Timbre chunks (with 5-byte frame header offset)", async () => {
  const { pcm16ToFloat32 } = await import(join(root, "dist/assets/audio/player.js"));
  const buf = new ArrayBuffer(5 + 4);
  const dv = new DataView(buf);
  dv.setInt16(5, 16384, true);
  dv.setInt16(7, -32768, true);
  const f = pcm16ToFloat32(buf, 5);
  assert.deepEqual(Array.from(f), [0.5, -1]);
});

test("every UI string exists in Hindi, Kannada and English", async () => {
  const { allKeys, tr } = await import(join(root, "dist/assets/i18n.js"));
  for (const k of allKeys()) for (const l of ["hi", "kn", "en"]) assert.ok(tr(k, l).length > 0, `${k}/${l}`);
});

test("html() escapes interpolated values (no injection from transcripts)", async () => {
  const { html, raw } = await import(join(root, "dist/assets/ui/dom.js"));
  const out = html`<p>${'<img src=x onerror=alert(1)>'}</p>${raw("<b>ok</b>")}`;
  assert.ok(!out.includes("<img") && out.includes("&lt;img") && out.includes("<b>ok</b>"));
});
