import type { RealtimeStatus } from "../api/realtime";
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
}

const HAZARDS = [
  { value: "", label: "All" },
  { value: "EARTHQUAKE", label: "Quake" },
  { value: "VOLCANO", label: "Volcano" },
  { value: "ASH", label: "Ash" },
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
}: Props): React.JSX.Element {
  return (
    <header className="topbar glass">
      <div className="brand">
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

      {unread > 0 ? <span className="tag">{unread} new</span> : null}

      <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
        <i className={`dot ${status} ${status === "live" ? "pulse" : ""}`} />
        {STATUS_TEXT[status]}
      </span>
    </header>
  );
}
