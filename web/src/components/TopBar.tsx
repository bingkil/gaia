import { useState } from "react";
import { api } from "../api/client";
import type { RealtimeStatus } from "../api/realtime";
import type { Basemap } from "../map/MapView";
import type { Filters } from "../state/useGaiaData";

interface Props {
  filters: Filters;
  onFilters: (filters: Filters) => void;
  status: RealtimeStatus;
  unread: number;
  pickMode: boolean;
  onPickMode: (on: boolean) => void;
  hasLocation: boolean;
  onUseMyLocation: () => void;
  basemap: Basemap;
  onBasemap: (basemap: Basemap) => void;
  imageryDate: string;
  onReload: () => void;
  onSettings: () => void;
  onLogs: () => void;
}

const HAZARDS = [
  { value: "", label: "All" },
  { value: "EARTHQUAKE", label: "Quake" },
  { value: "VOLCANO", label: "Volcano" },
  { value: "ASH", label: "Ash" },
  { value: "WILDFIRE", label: "Fire" },
];

const STATUS_TEXT: Record<RealtimeStatus, string> = {
  live: "Live",
  connecting: "Connecting",
  offline: "Reconnecting",
};

export function TopBar({
  filters,
  onFilters,
  status,
  unread,
  pickMode,
  onPickMode,
  hasLocation,
  onUseMyLocation,
  basemap,
  onBasemap,
  imageryDate,
  onReload,
  onSettings,
  onLogs,
}: Props): React.JSX.Element {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState<string | null>(null);

  // Two different things behind one button: ask the pollers to fetch now, and
  // re-read what the server already has. Only the first can fail.
  const refresh = async (): Promise<void> => {
    setRefreshing(true);
    setRefreshNote(null);
    try {
      const { results } = await api.refreshProviders();
      const cooling = results.filter((result) => result.status === "COOLING_DOWN");
      const requested = results.filter((result) => result.status === "REQUESTED");
      setRefreshNote(
        requested.length > 0
          ? `Polling ${requested.length}`
          : cooling.length > 0
            ? `Wait ${Math.ceil(Math.max(...cooling.map((r) => r.retryAfterSeconds ?? 0)))}s`
            : "Nothing to poll",
      );
    } catch {
      setRefreshNote("Refresh failed");
    } finally {
      onReload();
      setRefreshing(false);
      setTimeout(() => setRefreshNote(null), 4000);
    }
  };

  return (
    <header className="topbar glass">
      <div className="brand">
        <img className="brand-mark" src="/gaia-logo.png" alt="" width={26} height={26} />
        <b>GAIA</b>
        <span>Geohazard Awareness, Impact &amp; Alerting</span>
      </div>

      <div style={{ display: "flex", gap: 4 }}>
        {HAZARDS.map((hazard) => (
          <button
            key={hazard.value}
            className={`btn ${filters.hazardType === hazard.value ? "on" : ""}`}
            onClick={() => onFilters({ ...filters, hazardType: hazard.value })}
            type="button"
          >
            {hazard.label}
          </button>
        ))}
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11 }}>
        <span className="clock-label">Min M</span>
        <input
          type="range"
          min={0}
          max={7}
          step={0.5}
          style={{ width: 90 }}
          value={filters.minMagnitude ?? 0}
          onChange={(event) => {
            const value = Number(event.target.value);
            onFilters({ ...filters, minMagnitude: value === 0 ? undefined : value });
          }}
        />
        <span style={{ fontFamily: "var(--mono)", width: 24 }}>
          {filters.minMagnitude?.toFixed(1) ?? "—"}
        </span>
      </label>

      <div style={{ flex: 1 }} />

      <button
        className={`btn ${pickMode ? "on" : ""}`}
        onClick={() => onPickMode(!pickMode)}
        type="button"
        title="Click the map to set the location used for arrival estimates"
      >
        {pickMode ? "Click the map…" : hasLocation ? "Move location" : "Set location"}
      </button>
      <button className="btn" onClick={onUseMyLocation} type="button">
        Use my position
      </button>
      <button
        className={`btn ${basemap === "aerial" ? "on" : ""}`}
        onClick={() => onBasemap(basemap === "aerial" ? "dark" : "aerial")}
        type="button"
        aria-pressed={basemap === "aerial"}
        title="Sharp satellite imagery, but flown months or years ago"
      >
        Aerial
      </button>
      <button
        className={`btn ${basemap === "live" ? "on" : ""}`}
        onClick={() => onBasemap(basemap === "live" ? "dark" : "live")}
        type="button"
        aria-pressed={basemap === "live"}
        title={`True colour from VIIRS NOAA-21 for ${imageryDate} UTC, flown that day. Coarse, but it shows smoke and ash rather than a cloudless mosaic.`}
      >
        Satellite
      </button>

      {unread > 0 ? <span className="tag">{unread} new</span> : null}

      <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
        <i className={`dot ${status} ${status === "live" ? "pulse" : ""}`} />
        {STATUS_TEXT[status]}
      </span>

      {refreshNote ? <span className="tag">{refreshNote}</span> : null}
      <button
        className="btn"
        onClick={() => void refresh()}
        disabled={refreshing}
        type="button"
        title="Ask every feed to poll now, then re-read the data"
      >
        ⟳
      </button>
      <button className="btn" onClick={onSettings} type="button" title="Settings">
        ⚙
      </button>
      <button className="btn" onClick={onLogs} type="button" title="Logs">
        ▤
      </button>
    </header>
  );
}
