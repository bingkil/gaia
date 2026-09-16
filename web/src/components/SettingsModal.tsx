import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type {
  FirmsKeyStatus,
  HazardEvent,
  OpenSkyCredentialsStatus,
  SettingsResponse,
} from "../api/types";
import { DEVICE_ZONE, TIME_ZONES, useTimeZone } from "../state/timeZone";

function cadence(seconds: number | null): string {
  if (seconds === null) return "continuous";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

interface VaaResult {
  frameCount: number;
  warnings: string[];
}

export function SettingsModal({
  onClose,
  onIngested,
}: {
  onClose: () => void;
  onIngested: (event: HazardEvent) => void;
}): React.JSX.Element {
  const { zone, setZone } = useTimeZone();
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [firmsKey, setFirmsKey] = useState("");
  const [firmsStatus, setFirmsStatus] = useState<FirmsKeyStatus | null>(null);
  const [firmsBusy, setFirmsBusy] = useState(false);
  const [firmsError, setFirmsError] = useState<string | null>(null);
  const [openSkyClientId, setOpenSkyClientId] = useState("");
  const [openSkyClientSecret, setOpenSkyClientSecret] = useState("");
  const [openSkyStatus, setOpenSkyStatus] = useState<OpenSkyCredentialsStatus | null>(null);
  const [openSkyBusy, setOpenSkyBusy] = useState(false);
  const [openSkyError, setOpenSkyError] = useState<string | null>(null);
  const [bulletin, setBulletin] = useState("");
  const [vaaBusy, setVaaBusy] = useState(false);
  const [vaaResult, setVaaResult] = useState<VaaResult | null>(null);
  const [vaaError, setVaaError] = useState<string | null>(null);


  useEffect(() => {
    api
      .settings()
      .then((value) => {
        setSettings(value);
        setFirmsStatus(value.firmsKey);
        setOpenSkyStatus(value.openSky);
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

  const saveOpenSkyCredentials = async (): Promise<void> => {
    setOpenSkyBusy(true);
    setOpenSkyError(null);
    try {
      setOpenSkyStatus(
        await api.setOpenSkyCredentials(openSkyClientId.trim(), openSkyClientSecret.trim()),
      );
      setOpenSkyClientId("");
      setOpenSkyClientSecret("");
    } catch (cause: unknown) {
      setOpenSkyError(cause instanceof Error ? cause.message : "could not save the credentials");
    } finally {
      setOpenSkyBusy(false);
    }
  };

  const removeOpenSkyCredentials = async (): Promise<void> => {
    setOpenSkyBusy(true);
    setOpenSkyError(null);
    try {
      setOpenSkyStatus(await api.clearOpenSkyCredentials());
    } catch (cause: unknown) {
      setOpenSkyError(cause instanceof Error ? cause.message : "could not remove the credentials");
    } finally {
      setOpenSkyBusy(false);
    }
  };

  const submitVaa = (): void => {
    setVaaBusy(true);
    setVaaError(null);
    setVaaResult(null);
    api
      .ingestVaa(bulletin)
      .then((response) => {
        setVaaResult({ frameCount: response.frameCount, warnings: response.parserWarnings });
        setBulletin("");
        onIngested(response.event);
      })
      .catch((cause: unknown) => {
        setVaaError(
          cause instanceof ApiError ? cause.message : "Could not reach the local service.",
        );
      })
      .finally(() => setVaaBusy(false));
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
          <div className="settings-section">
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
                className={`btn${zone === DEVICE_ZONE ? " on" : ""}`}
                onClick={() => setZone(DEVICE_ZONE)}
                type="button"
              >
                This device ({DEVICE_ZONE})
              </button>
            </div>
            <select
              aria-label="Choose a time zone"
              value={zone}
              onChange={(event) => setZone(event.target.value)}
              style={{ width: "100%", margin: "0 0 8px" }}
            >
              <option value="UTC">UTC</option>
              {TIME_ZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
            <p className="legend-note">
              Every feed reports in UTC and volcanic ash advisories are read in UTC by the
              people who issue them, so UTC is the default. Local times always carry their
              offset, and the full UTC timestamp stays on the event detail whichever you pick.
            </p>
          </div>

          <div className="settings-section">
            <div className="panel-title">Feeds</div>
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
                        <td>
                          {provider.mode === "STREAM" ? "stream" : cadence(provider.pollSeconds)}
                        </td>
                        <td>{cadence(provider.staleAfterSeconds)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="legend-note">
                  Cadence is owned by the server process that holds the connections, so it is
                  shown here rather than edited here. Change it with an environment variable,
                  for example <code>GAIA_PROVIDERS__GDACS__POLL_SECONDS=120</code>, and restart.
                  Refresh is rate limited to one manual poll per source every{" "}
                  {settings.manualPollMinSeconds}s, because these are public feeds.
                </p>
              </>
            ) : error ? null : (
              <p className="legend-note">Reading…</p>
            )}
          </div>

          <div className="settings-section">
            <div className="panel-title">NASA FIRMS key</div>
            <p className="legend-note">
              Satellite heat detections need a free key from NASA FIRMS. Without one, fires are
              reported from GDACS alone and cannot reach satellite-confirmed confidence.
            </p>
            <p className="legend-note">New to FIRMS? Get a key in under a minute:</p>
            <ol className="legend-note" style={{ margin: "0 0 8px", paddingLeft: 18 }}>
              <li>
                Open{" "}
                <a
                  href="https://firms.modaps.eosdis.nasa.gov/api/map_key/"
                  target="_blank"
                  rel="noreferrer"
                >
                  firms.modaps.eosdis.nasa.gov/api/map_key
                </a>
              </li>
              <li>Enter your email address and submit the form.</li>
              <li>NASA emails you a MAP_KEY — copy it.</li>
              <li>Paste it below and click Save.</li>
            </ol>
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
              Stored on this machine beside the database, never in the repository, and never
              sent back to this page.
            </p>
          </div>

          <div className="settings-section">
            <div className="panel-title">OpenSky credentials</div>
            <p className="legend-note">
              Live flight positions are rate-limited to 400 requests/day for anonymous access.
              Adding free OpenSky credentials raises that to 4,000/day.
            </p>
            <ol className="legend-note" style={{ margin: "0 0 8px", paddingLeft: 18 }}>
              <li>
                Open{" "}
                <a
                  href="https://opensky-network.org/my-opensky/account"
                  target="_blank"
                  rel="noreferrer"
                >
                  opensky-network.org/my-opensky/account
                </a>
              </li>
              <li>Create a new API client.</li>
              <li>Paste the client ID and secret below and click Save.</li>
            </ol>
            {openSkyStatus?.configured ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "8px 0" }}>
                <span className="tag">client {openSkyStatus.hint}</span>
                {openSkyStatus.fromEnvironment ? (
                  <span className="legend-note">set by environment variable</span>
                ) : (
                  <button
                    className="btn"
                    onClick={() => void removeOpenSkyCredentials()}
                    type="button"
                    disabled={openSkyBusy}
                  >
                    Remove
                  </button>
                )}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6, margin: "8px 0" }}>
                <input
                  type="text"
                  autoComplete="off"
                  spellCheck={false}
                  placeholder="Client ID"
                  aria-label="OpenSky client ID"
                  value={openSkyClientId}
                  onChange={(event) => setOpenSkyClientId(event.target.value)}
                />
                <div style={{ display: "flex", gap: 6 }}>
                  <input
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="Client secret"
                    aria-label="OpenSky client secret"
                    value={openSkyClientSecret}
                    onChange={(event) => setOpenSkyClientSecret(event.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button
                    className="btn"
                    onClick={() => void saveOpenSkyCredentials()}
                    type="button"
                    disabled={
                      openSkyBusy ||
                      openSkyClientId.trim() === "" ||
                      openSkyClientSecret.trim() === ""
                    }
                  >
                    {openSkyBusy ? "Saving…" : "Save"}
                  </button>
                </div>
              </div>
            )}
            {openSkyError ? <p className="legend-note">{openSkyError}</p> : null}
            <p className="legend-note">
              Stored on this machine beside the database, never in the repository, and never
              sent back to this page.
            </p>
          </div>

          <div className="settings-section">
            <div className="panel-title">Paste ash advisory</div>
            <p className="legend-note">
              Paste a VAA bulletin as issued by a Volcanic Ash Advisory Centre. Each frame is
              drawn only at its own valid time — scrub the clock to reach a forecast frame.
            </p>
            <div className="field">
              <label htmlFor="vaa-bulletin">VAA bulletin text</label>
              <textarea
                id="vaa-bulletin"
                rows={7}
                value={bulletin}
                spellCheck={false}
                style={{ fontFamily: "var(--mono)", fontSize: 10, resize: "vertical" }}
                onChange={(event) => setBulletin(event.target.value)}
                placeholder={"VA ADVISORY\nDTG: …\nVAAC: …\nVOLCANO: …\nOBS VA CLD: …"}
              />
            </div>
            <button
              className="btn"
              onClick={submitVaa}
              disabled={vaaBusy || bulletin.trim() === ""}
              type="button"
            >
              {vaaBusy ? "Reading…" : "Ingest advisory"}
            </button>
            {vaaError ? (
              <p className="disclaimer solid" style={{ marginTop: 10 }}>
                {vaaError}
              </p>
            ) : null}
            {vaaResult ? (
              <div style={{ marginTop: 10 }}>
                <p className="disclaimer solid">
                  {vaaResult.frameCount} ash {vaaResult.frameCount === 1 ? "frame" : "frames"}{" "}
                  stored.
                </p>
                {vaaResult.warnings.length > 0 ? (
                  <>
                    <div className="panel-title" style={{ margin: "10px 0 4px" }}>
                      Parser warnings
                    </div>
                    <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "var(--warn)" }}>
                      {vaaResult.warnings.map((warning) => (
                        <li key={warning}>{warning}</li>
                      ))}
                    </ul>
                  </>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="settings-section">
            <p className="legend-note">
              © {new Date().getFullYear()} bingkil.com ·{" "}
              <a href="https://bingkil.com" target="_blank" rel="noreferrer">
                bingkil.com
              </a>{" "}
              ·{" "}
              <a href="/TERMS_OF_SERVICE.md" target="_blank" rel="noreferrer">
                Terms of Service
              </a>{" "}
              ·{" "}
              <a href="/PRIVACY.md" target="_blank" rel="noreferrer">
                Privacy Policy
              </a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
