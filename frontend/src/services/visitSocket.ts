/** Visit WebSocket client with bounded exponential backoff (recovery layer 1). */
export type ServerEvent = { type: string; seq?: number; [k: string]: any };
export type ConnStatus = "connecting" | "open" | "reconnecting" | "offline" | "closed";

export class VisitSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private closedByUser = false;
  private seq = 0;
  private everOpened = false;
  onEvent: (e: ServerEvent) => void = () => {};
  onAudio: (uid: number, data: ArrayBuffer, offset: number) => void = () => {};
  onStatus: (s: ConnStatus) => void = () => {};

  constructor(private sessionId: string, private token: string, private maxAttempts = 6) {}

  connect(): void {
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
        try { this.onEvent(JSON.parse(ev.data)); } catch { /* ignore malformed */ }
      } else if (ev.data instanceof ArrayBuffer && ev.data.byteLength > 5) {
        const view = new DataView(ev.data);
        if (view.getUint8(0) === 1) this.onAudio(view.getUint32(1, true), ev.data, 5);
      }
    };
    ws.onclose = (ev) => {
      this.ws = null;
      if (this.closedByUser) { this.onStatus("closed"); return; }
      if (ev.code === 4401) { this.onStatus("offline"); return; } // session gone / bad token
      if (this.attempts >= this.maxAttempts) { this.onStatus("offline"); return; }
      const delay = Math.min(8000, 500 * 2 ** this.attempts) + Math.random() * 300;
      this.attempts += 1;
      this.onStatus("reconnecting");
      window.setTimeout(() => this.connect(), delay);
    };
  }

  /** Manual reconnect after the automatic backoff gave up (recovery layer 1, user-triggered). */
  retry(): void {
    if (this.ws) return;
    this.attempts = 0;
    this.connect();
  }

  get isOpen(): boolean {
    return !!this.ws && this.ws.readyState === WebSocket.OPEN;
  }

  send(obj: Record<string, unknown>): void {
    if (!this.isOpen) return;
    this.seq += 1;
    this.ws!.send(JSON.stringify({ ...obj, seq: this.seq }));
  }

  sendAudio(frame: ArrayBuffer): void {
    if (this.isOpen && this.ws!.bufferedAmount < 256 * 1024) this.ws!.send(frame); // backpressure guard
  }

  close(): void {
    this.closedByUser = true;
    this.ws?.close(1000);
  }
}
