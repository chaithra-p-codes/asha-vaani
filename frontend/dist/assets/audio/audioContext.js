/** One shared AudioContext, created/resumed only from a user gesture (mobile autoplay rules). */
let ctx = null;
export function audioContext() {
    if (!ctx) {
        const Ctor = (window.AudioContext || window.webkitAudioContext);
        ctx = new Ctor({ latencyHint: "interactive" });
    }
    return ctx;
}
export async function unlockAudio() {
    const c = audioContext();
    if (c.state !== "running") {
        try {
            await c.resume();
        }
        catch { /* resumed later on next gesture */ }
    }
    return c;
}
