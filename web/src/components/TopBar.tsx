import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { RealtimeStatus } from "../api/realtime";
import type { HazardType } from "../api/types";
import type { Basemap } from "../map/MapView";
import { AIRCRAFT_PATH } from "../map/icons";
import type { Filters } from "../state/useGaiaData";
import { HazardIcon } from "./EventList";

interface Props {
  filters: Filters;
  onFilters: (filters: Filters) => void;
  status: RealtimeStatus;
  unread: number;
  alertsTotal: number;
  alertsOpen: boolean;
  onAlerts: () => void;
  watchAreaOpen: boolean;
  onWatchArea: () => void;
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
  showFlights: boolean;
  onFlights: (showFlights: boolean) => void;
  showFlightTrails: boolean;
  onFlightTrails: (showFlightTrails: boolean) => void;
  flightsLoading: boolean;
}

const HAZARDS: { value: HazardType; label: string }[] = [
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

/** Double-peak silhouette: sharp, static aerial imagery. */
function AerialIcon(): React.JSX.Element {
  return (
    <svg className="layer-icon" viewBox="0 0 12 12" aria-hidden="true">
      <polygon points="1,10 4.5,4 6,6.5 7.5,3.5 11,10" fill="currentColor" />
    </svg>
  );
}

/** Orbit rings: a satellite pass, standing in for daily true-colour imagery. */
function SatelliteIcon(): React.JSX.Element {
  return (
    <svg className="layer-icon" viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="6" r="2" fill="currentColor" />
      <ellipse cx="6" cy="6" rx="5.2" ry="2" fill="none" stroke="currentColor" strokeWidth="1" />
    </svg>
  );
}

function FlightsIcon(): React.JSX.Element {
  return (
    <svg className="layer-icon" viewBox="0 0 12 12" aria-hidden="true">
      <path d={AIRCRAFT_PATH} fill="currentColor" transform="rotate(45 6 6)" />
    </svg>
  );
}

/** A bell: alerts, badged with the unread count when there is one. */
function BellIcon(): React.JSX.Element {
  return (
    <svg className="layer-icon" viewBox="0 0 12 12" aria-hidden="true">
      <path
        d="M6 1a2.6 2.6 0 0 0-2.6 2.6v1.3c0 .5-.2 1-.5 1.4L1.9 7.6c-.3.3 0 .9.4.9h7.4c.4 0 .7-.6.4-.9L9.1 6.3c-.3-.4-.5-.9-.5-1.4V3.6A2.6 2.6 0 0 0 6 1Z"
        fill="currentColor"
      />
      <path d="M4.8 9.2a1.2 1.2 0 0 0 2.4 0Z" fill="currentColor" />
    </svg>
  );
}

/** Concentric rings: the radius a watch area alerts within. */
function WatchAreaIcon(): React.JSX.Element {
  return (
    <svg className="layer-icon" viewBox="0 0 12 12" aria-hidden="true">
      <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="6" cy="6" r="2.4" fill="none" stroke="currentColor" strokeWidth="1" />
      <circle cx="6" cy="6" r="1" fill="currentColor" />
    </svg>
  );
}

export function TopBar({
  filters,
  onFilters,
  status,
  unread,
  alertsTotal,
  alertsOpen,
  onAlerts,
  watchAreaOpen,
  onWatchArea,
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
  showFlights,
  onFlights,
  showFlightTrails,
  onFlightTrails,
  flightsLoading,
}: Props): React.JSX.Element {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState<string | null>(null);
  const [flightsMenuOpen, setFlightsMenuOpen] = useState(false);
  const flightsMenuRef = useRef<HTMLDivElement | null>(null);
  const [viewsMenuOpen, setViewsMenuOpen] = useState(false);
  const viewsMenuRef = useRef<HTMLDivElement | null>(null);
  const [locationMenuOpen, setLocationMenuOpen] = useState(false);
  const locationMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!flightsMenuOpen) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!flightsMenuRef.current?.contains(event.target as Node)) setFlightsMenuOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [flightsMenuOpen]);

  useEffect(() => {
    if (!viewsMenuOpen) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!viewsMenuRef.current?.contains(event.target as Node)) setViewsMenuOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [viewsMenuOpen]);

  useEffect(() => {
    if (!locationMenuOpen) return;
    const onPointerDown = (event: PointerEvent): void => {
      if (!locationMenuRef.current?.contains(event.target as Node)) setLocationMenuOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [locationMenuOpen]);

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
        {HAZARDS.map((hazard) => {
          const checked = filters.hazardTypes.includes(hazard.value);
          return (
            <button
              key={hazard.value}
              className={`btn ${checked ? "on" : ""}`}
              onClick={() =>
                onFilters({
                  ...filters,
                  hazardTypes: checked
                    ? filters.hazardTypes.filter((value) => value !== hazard.value)
                    : [...filters.hazardTypes, hazard.value],
                })
              }
              type="button"
              role="checkbox"
              aria-checked={checked}
            >
              <HazardIcon hazardType={hazard.value} />
              {hazard.label}
            </button>
          );
        })}
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

      <div className="btn-group" ref={viewsMenuRef}>
        <button
          className={`btn ${basemap !== "dark" ? "on" : ""}`}
          onClick={() => setViewsMenuOpen((open) => !open)}
          type="button"
          aria-expanded={viewsMenuOpen}
        >
          Views ▾
        </button>
        {viewsMenuOpen ? (
          <div className="dropdown glass">
            <button
              className={`dropdown-item ${basemap === "aerial" ? "on" : ""}`}
              onClick={() => {
                onBasemap(basemap === "aerial" ? "dark" : "aerial");
                setViewsMenuOpen(false);
              }}
              type="button"
              title="Sharp satellite imagery, but flown months or years ago"
            >
              <AerialIcon />
              Aerial
            </button>
            <button
              className={`dropdown-item ${basemap === "live" ? "on" : ""}`}
              onClick={() => {
                onBasemap(basemap === "live" ? "dark" : "live");
                setViewsMenuOpen(false);
              }}
              type="button"
              title={`True colour from VIIRS NOAA-21 for ${imageryDate} UTC, flown that day. Coarse, but it shows smoke and ash rather than a cloudless mosaic.`}
            >
              <SatelliteIcon />
              Satellite
            </button>
          </div>
        ) : null}
      </div>

      <div className="btn-group" ref={locationMenuRef}>
        <button
          className={`btn ${pickMode ? "on" : ""}`}
          onClick={() => setLocationMenuOpen((open) => !open)}
          type="button"
          aria-expanded={locationMenuOpen}
          title="Click the map to set the location used for arrival estimates"
        >
          {pickMode ? "Click the map…" : hasLocation ? "Move location" : "Set location"} ▾
        </button>
        {locationMenuOpen ? (
          <div className="dropdown glass">
            <button
              className="dropdown-item"
              onClick={() => {
                onPickMode(!pickMode);
                setLocationMenuOpen(false);
              }}
              type="button"
            >
              Mark on the map
            </button>
            <button
              className="dropdown-item"
              onClick={() => {
                onUseMyLocation();
                setLocationMenuOpen(false);
              }}
              type="button"
            >
              Use my location
            </button>
          </div>
        ) : null}
      </div>

      <button
        className={`btn icon-only ${watchAreaOpen ? "on" : ""}`}
        onClick={onWatchArea}
        type="button"
        aria-pressed={watchAreaOpen}
        title="Watch areas"
      >
        <WatchAreaIcon />
      </button>
      <button className="btn" onClick={onLogs} type="button" title="Logs">
        ▤
      </button>

      <div className="btn-group" ref={flightsMenuRef}>
        <button
          className={`btn ${showFlights ? "on" : ""}`}
          onClick={() => onFlights(!showFlights)}
          type="button"
          aria-pressed={showFlights}
          title="Live aircraft positions from OpenSky Network"
        >
          <FlightsIcon />
          Flights
          {showFlights && flightsLoading ? <i className="spinner" aria-label="Loading" /> : null}
        </button>
        <button
          className={`btn btn-caret ${showFlightTrails ? "on" : ""}`}
          onClick={() => setFlightsMenuOpen((open) => !open)}
          type="button"
          disabled={!showFlights}
          aria-expanded={flightsMenuOpen}
          title="Trail options"
        >
          ▾
        </button>
        {flightsMenuOpen ? (
          <div className="dropdown glass">
            <label className="dropdown-item">
              <input
                type="checkbox"
                checked={showFlightTrails}
                onChange={(event) => onFlightTrails(event.target.checked)}
              />
              Show trails
            </label>
          </div>
        ) : null}
      </div>

      <div className="topbar-divider" />

      <button className="btn" onClick={onSettings} type="button" title="Settings">
        ⚙
      </button>
      <button
        className={`btn icon-only alert-btn ${alertsOpen ? "on" : ""} ${
          unread > 0 ? "unread" : alertsTotal > 0 ? "read" : "none"
        }`}
        onClick={onAlerts}
        type="button"
        aria-pressed={alertsOpen}
        title={
          unread > 0
            ? `${unread} unread alert${unread === 1 ? "" : "s"}`
            : alertsTotal > 0
              ? "All alerts read"
              : "No alerts"
        }
      >
        <BellIcon />
        {unread > 0 ? <span className="badge">{unread}</span> : null}
      </button>
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
      <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
        <i className={`dot ${status} ${status === "live" ? "pulse" : ""}`} />
        {STATUS_TEXT[status]}
      </span>
    </header>
  );
}
