/** Microphone capture: getUserMedia -> AudioWorklet (16 kHz, 512-sample PCM16 frames). */
import { audioContext } from "./audioContext.js";
export class MicCapture {
    constructor() {
        this.stream = null;
        this.node = null;
        this.source = null;
        this.sink = null;
        this.onFrame = () => { };
        this.running = false;
    }
    async start() {
        if (this.running)
            return;
        if (!navigator.mediaDevices?.getUserMedia)
            throw new Error("unsupported");
        const ctx = audioContext();
        if (ctx.state !== "running")
            await ctx.resume();
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        await ctx.audioWorklet.addModule("/audio/pcm-capture-worklet.js");
        this.source = ctx.createMediaStreamSource(this.stream);
        this.node = new AudioWorkletNode(ctx, "pcm-capture", {
            numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
            processorOptions: { inputSampleRate: ctx.sampleRate },
        });
        this.node.port.onmessage = (ev) => {
            const d = ev.data;
            if (d && d.frame)
                this.onFrame(d.frame, d.rms);
        };
        // Keep the graph pulling without making the mic audible.
        this.sink = ctx.createGain();
        this.sink.gain.value = 0;
        this.source.connect(this.node);
        this.node.connect(this.sink);
        this.sink.connect(ctx.destination);
        this.running = true;
    }
    stop() {
        this.running = false;
        try {
            this.source?.disconnect();
            this.node?.disconnect();
            this.sink?.disconnect();
        }
        catch { /* ignore */ }
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.node = null;
        this.source = null;
    }
}
export function isPermissionError(err) {
    const name = err?.name || "";
    return name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError";
}
