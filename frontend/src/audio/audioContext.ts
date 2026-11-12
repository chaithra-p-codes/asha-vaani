/** One shared AudioContext, created/resumed only from a user gesture (mobile autoplay rules). */
let ctx: AudioContext | null = null;

export function audioContext(): AudioContext {
  if (!ctx) {
    const Ctor = (window.AudioContext || (window as any).webkitAudioContext) as typeof AudioContext;
    ctx = new Ctor({ latencyHint: "interactive" });
  }
  return ctx;
}

export async function unlockAudio(): Promise<AudioContext> {
  const c = audioContext();
  if (c.state !== "running") {
    try { await c.resume(); } catch { /* resumed later on next gesture */ }
  }
  return c;
}
