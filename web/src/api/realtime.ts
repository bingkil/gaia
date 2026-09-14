import type { RealtimeMessage } from "./types";

type Status = "connecting" | "live" | "offline";

interface Handlers {
  onMessage: (message: RealtimeMessage) => void;
  onStatus: (status: Status) => void;
  /** The backlog could not cover the gap; local state must be refetched. */
  onResyncRequired: () => void;
}

const MAX_BACKOFF_MS = 15_000;

/**
 * Bus subscription that survives reconnects.
 *
 * The last sequence seen is replayed on reconnect. When the server cannot
 * cover the gap it says so, and we refetch rather than leaving a silent hole
 * in the map.
 */
export class RealtimeClient {
  private socket: WebSocket | null = null;
  private sequence: number | null = null;
  private backoff = 500;
  private timer: number | null = null;
  private closed = false;

  constructor(private readonly handlers: Handlers) {}

  connect(): void {
    this.closed = false;
    this.open();
  }

  close(): void {
    this.closed = true;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.socket?.close();
    this.socket = null;
  }

  private open(): void {
    this.handlers.onStatus("connecting");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const since = this.sequence === null ? "" : `?since=${this.sequence}`;
    const socket = new WebSocket(`${protocol}//${window.location.host}/v1/realtime${since}`);
    this.socket = socket;

    socket.onopen = () => {
      this.backoff = 500;
    };

    socket.onmessage = (raw) => {
      let message: RealtimeMessage;
      try {
        message = JSON.parse(raw.data as string) as RealtimeMessage;
      } catch {
        return;
      }

      if (typeof message.sequence === "number") this.sequence = message.sequence;

      if (message.type === "hello") {
        this.handlers.onStatus("live");
        if (message.resyncRequired) this.handlers.onResyncRequired();
        return;
      }
      if (message.type === "heartbeat") return;

      this.handlers.onMessage(message);
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.closed) return;
      this.handlers.onStatus("offline");
      this.timer = window.setTimeout(() => this.open(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, MAX_BACKOFF_MS);
    };

    socket.onerror = () => socket.close();
  }
}

export type { Status as RealtimeStatus };
