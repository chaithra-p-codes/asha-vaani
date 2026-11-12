export class VisitSocket {
    constructor(sessionId, token, maxAttempts = 6) {
        this.sessionId = sessionId;
        this.token = token;
        this.maxAttempts = maxAttempts;
        this.ws = null;
        this.attempts = 0;
        this.closedByUser = false;
        this.seq = 0;
        this.everOpened = false;
        this.onEvent = () => { };
        this.onAudio = () => { };
        this.onStatus = () => { };
    }
    connect() {
        this.closedByUser = false;
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${proto}//${location.host}/ws/visit/${encodeURIComponent(this.sessionId)}?token=${encodeURIComponent(this.token)}`;
        this.onStatus(this.everOpened ? "reconnecting" : "connecting");
        const ws = new WebSocket(url);
        ws.binaryType = "arraybuffer";
        this.ws = ws;
        ws.onopen = () => {
            this.attempts = 0;
            this.onStatus("open");
            this.send({ type: "hello", client: "pwa/1.0", resume: this.everOpened || !!sessionStorage.getItem("asha.resume") });
            this.everOpened = true;
        };
        ws.onmessage = (ev) => {
            if (typeof ev.data === "string") {
                try {
                    this.onEvent(JSON.parse(ev.data));
                }
                catch { /* ignore malformed */ }
            }
            else if (ev.data instanceof ArrayBuffer && ev.data.byteLength > 5) {
                const view = new DataView(ev.data);
                if (view.getUint8(0) === 1)
                    this.onAudio(view.getUint32(1, true), ev.data, 5);
            }
        };
        ws.onclose = (ev) => {
            this.ws = null;
            if (this.closedByUser) {
                this.onStatus("closed");
                return;
            }
            if (ev.code === 4401) {
                this.onStatus("offline");
                return;
            } // session gone / bad token
            if (this.attempts >= this.maxAttempts) {
                this.onStatus("offline");
                return;
            }
            const delay = Math.min(8000, 500 * 2 ** this.attempts) + Math.random() * 300;
            this.attempts += 1;
            this.onStatus("reconnecting");
            window.setTimeout(() => this.connect(), delay);
        };
    }
    /** Manual reconnect after the automatic backoff gave up (recovery layer 1, user-triggered). */
    retry() {
        if (this.ws)
            return;
        this.attempts = 0;
        this.connect();
    }
    get isOpen() {
        return !!this.ws && this.ws.readyState === WebSocket.OPEN;
    }
    send(obj) {
        if (!this.isOpen)
            return;
        this.seq += 1;
        this.ws.send(JSON.stringify({ ...obj, seq: this.seq }));
    }
    sendAudio(frame) {
        if (this.isOpen && this.ws.bufferedAmount < 256 * 1024)
            this.ws.send(frame); // backpressure guard
    }
    close() {
        this.closedByUser = true;
        this.ws?.close(1000);
    }
}
