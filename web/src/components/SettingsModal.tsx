import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { FirmsKeyStatus, SettingsResponse } from "../api/types";
import { DEVICE_ZONE, useTimeZone } from "../state/timeZone";

function cadence(seconds: number | null): string {
  if (seconds === null) return "continuous";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export function SettingsModal({ onClose }: { onClose: () => void }): React.JSX.Element {
  const { zone, setZone } = useTimeZone();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [firmsKey, setFirmsKey] = useState("");
  const [firmsStatus, setFirmsStatus] = useState<FirmsKeyStatus | null>(null);
  const [firmsBusy, setFirmsBusy] = useState(false);
  const [firmsError, setFirmsError] = useState<string | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((value) => {
        setSettings(value);
        setFirmsStatus(value.firmsKey);
      })
      .catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "failed"));
  }, []);

  const saveFirmsKey = async (): Promise<void> => {
    setFirmsBusy(true);
    setFirmsError(null);
    try {
      setFirmsStatus(await api.setFirmsKey(firmsKey.trim()));
      setFirmsKey("");
    } catch (cause: unknown) {
      setFirmsError(cause instanceof Error ? cause.message : "could not save the key");
    } finally {
      setFirmsBusy(false);
    }
  };

  const removeFirmsKey = async (): Promise<void> => {
    setFirmsBusy(true);
    setFirmsError(null);
    try {
      setFirmsStatus(await api.clearFirmsKey());
    } catch (cause: unknown) {
      setFirmsError(cause instanceof Error ? cause.message : "could not remove the key");
    } finally {
      setFirmsBusy(false);
    }
  };

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
        className="modal solid"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
      >
        <header className="panel-head">
          <span className="panel-title">Settings</span>
          <button className="btn ghost" onClick={onClose} type="button" aria-label="Close">
            ✕
          </button>
        </header>

        <div className="modal-body">
          <div className="panel-title">Time zone</div>
          <div style={{ display: "flex", gap: 6, margin: "8px 0" }}>
            <button
              className={`btn${zone === "UTC" ? " on" : ""}`}
              onClick={() => setZone("UTC")}
              type="button"
            >
              UTC
            </button>
            <button
              className={`btn${zone === "LOCAL" ? " on" : ""}`}
              onClick={() => setZone("LOCAL")}
              type="button"
            >
              {DEVICE_ZONE}
            </button>
          </div>
          <p className="legend-note">
            Every feed reports in UTC and volcanic ash advisories are read in UTC by the people
            who issue them, so UTC is the default. Local times always carry their offset, and
            the full UTC timestamp stays on the event detail whichever you pick.
          </p>

          <div className="panel-title" style={{ marginTop: 14 }}>
            Feeds
          </div>
          {error ? <p className="legend-note">Could not read settings: {error}</p> : null}
          {settings ? (
            <>
              <table className="settings-table">
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Every</th>
                    <th>Stale after</th>
                  </tr>
                </thead>
                <tbody>
                  {settings.providers.map((provider) => (
                    <tr key={provider.provider}>
                      <td>
                        {provider.provider}
                        {provider.enabled ? null : <span className="tag">off</span>}
                      </td>
                      <td>{provider.mode === "STREAM" ? "stream" : cadence(provider.pollSeconds)}</td>
                      <td>{cadence(provider.staleAfterSeconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="legend-note">
                Cadence is owned by the server process that holds the connections, so it is
                shown here rather than edited here. Change it with an environment variable, for
                example <code>GAIA_PROVIDERS__GDACS__POLL_SECONDS=120</code>, and restart.
                Refresh is rate limited to one manual poll per source every{" "}
                {settings.manualPollMinSeconds}s, because these are public feeds.
              </p>
            </>
          ) : error ? null : (
            <p className="legend-note">Reading…</p>
          )}

          <div className="panel-title" style={{ marginTop: 14 }}>
            NASA FIRMS key
          </div>
          <p className="legend-note">
            Satellite heat detections need a free key from NASA FIRMS. Without one, fires are
            reported from GDACS alone and cannot reach satellite-confirmed confidence. Request
            one at{" "}
            <a
              href="https://firms.modaps.eosdis.nasa.gov/api/map_key/"
              target="_blank"
              rel="noreferrer"
            >
              firms.modaps.eosdis.nasa.gov
            </a>
            .
          </p>
          {firmsStatus?.configured ? (
            <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0" }}>
              <span className="tag">key {firmsStatus.hint}</span>
              {firmsStatus.fromEnvironment ? (
                <span className="legend-note">set by environment variable</span>
              ) : (
                <button
                  className="btn"
                  onClick={() => void removeFirmsKey()}
                  type="button"
                  disabled={firmsBusy}
                >
                  Remove
                </button>
              )}
            </div>
          ) : (
            <div style={{ display: "flex", gap: 6, margin: "8px 0" }}>
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder="Paste your MAP_KEY"
                aria-label="NASA FIRMS map key"
                value={firmsKey}
                onChange={(event) => setFirmsKey(event.target.value)}
                style={{ flex: 1 }}
              />
              <button
                className="btn"
                onClick={() => void saveFirmsKey()}
                type="button"
                disabled={firmsBusy || firmsKey.trim() === ""}
              >
                {firmsBusy ? "Saving…" : "Save"}
              </button>
            </div>
          )}
          {firmsError ? <p className="legend-note">{firmsError}</p> : null}
          <p className="legend-note">
            Stored on this machine beside the database, never in the repository, and never sent
            back to this page.
          </p>
        </div>
      </div>
    </div>
  );
}
