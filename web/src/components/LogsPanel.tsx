import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { LogEntry } from "../api/types";
import { utcStamp } from "./format";

const LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"];
const POLL_MS = 4000;

const LEVEL_CLASS: Record<string, string> = {
  DEBUG: "log-debug",
  INFO: "log-info",
  WARNING: "log-warning",
  ERROR: "log-error",
  CRITICAL: "log-error",
};

export function LogsPanel({ onClose }: { onClose: () => void }): React.JSX.Element {
  const [level, setLevel] = useState("INFO");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = (): void => {
      api
        .logs({ level, limit: 500 })
        .then((response) => {
          if (!cancelled) {
            setLogs(response.logs);
            setError(null);
          }
        })
        .catch((cause: unknown) => {
          if (!cancelled) setError(cause instanceof Error ? cause.message : "failed");
        });
    };
    load();
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [level]);

  useEffect(() => {
    if (autoScroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-scrim" onClick={onClose} role="presentation">
      <div
        className="modal solid logs-modal"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Logs"
      >
        <header className="panel-head">
          <span className="panel-title">Logs</span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <select
              aria-label="Minimum log level"
              value={level}
              onChange={(event) => setLevel(event.target.value)}
            >
              {LEVELS.map((value) => (
                <option key={value} value={value}>
                  {value}+
                </option>
              ))}
            </select>
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}>
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(event) => setAutoScroll(event.target.checked)}
              />
              Follow
            </label>
            <button className="btn ghost" onClick={onClose} type="button" aria-label="Close">
              ✕
            </button>
          </span>
        </header>

        <div className="modal-body logs-body" ref={bodyRef}>
          {error ? <p className="legend-note">Could not read logs: {error}</p> : null}
          {!error && logs.length === 0 ? <p className="legend-note">No log entries yet.</p> : null}
          {logs.map((entry, index) => (
            <div className={`log-line ${LEVEL_CLASS[entry.level] ?? ""}`} key={index}>
              <span className="log-ts">{utcStamp(entry.ts)}</span>
              <span className="log-level">{entry.level}</span>
              <span className="log-logger">{entry.logger}</span>
              <span className="log-message">{entry.message}</span>
            </div>
          ))}
        </div>
        <p className="legend-note" style={{ padding: "0 14px 12px" }}>
          Only this process's own recent log lines are kept in memory (this view resets when
          GAIA restarts). Polling every {POLL_MS / 1000}s.
        </p>
      </div>
    </div>
  );
}
