import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { HazardEvent } from "./api/types";
import { ClockBar } from "./components/ClockBar";
import { EventDetail } from "./components/EventDetail";
import { EventList } from "./components/EventList";
import { FlightList } from "./components/FlightList";
import { ImageryAgeBadge } from "./components/ImageryAgeBadge";
import { Legend } from "./components/Legend";
import { LogsPanel } from "./components/LogsPanel";
import { NotificationFeed } from "./components/NotificationFeed";
import { ProviderHealthPanel } from "./components/ProviderHealthPanel";
import { SettingsModal } from "./components/SettingsModal";
import { TopBar } from "./components/TopBar";
import { WatchAreaPanel } from "./components/WatchAreaPanel";
import { type Basemap, type MapFocus, MapView } from "./map/MapView";
import type { AerialCapture } from "./map/imagery";
import { useMapClock } from "./map/useMapClock";
import { DEFAULT_RANGE, type TimeRange, imageryDate, rangeSummary } from "./state/timeRange";
import { useTimeZone } from "./state/timeZone";
import { ALL_HAZARD_TYPES, type Filters, useGaiaData } from "./state/useGaiaData";

const LOCATION_KEY = "gaia.location";
const BASEMAP_KEY = "gaia.basemap";
const AERIAL_KEY = "gaia.aerial";
const FLIGHTS_KEY = "gaia.flights";
const FLIGHT_TRAILS_KEY = "gaia.flightTrails";

function loadBasemap(): Basemap {
  const stored = window.localStorage.getItem(BASEMAP_KEY);
  if (stored === "dark" || stored === "aerial" || stored === "live") return stored;
  return window.localStorage.getItem(AERIAL_KEY) === "1" ? "aerial" : "dark";
}

interface Location {
  longitude: number;
  latitude: number;
}

function loadLocation(): Location | null {
  try {
    const raw = window.localStorage.getItem(LOCATION_KEY);
    return raw ? (JSON.parse(raw) as Location) : null;
  } catch {
    return null;
  }
}

export function App(): React.JSX.Element {
  const { zone } = useTimeZone();
  const [filters, setFilters] = useState<Filters>({
    hazardTypes: [...ALL_HAZARD_TYPES],
    minMagnitude: undefined,
    range: DEFAULT_RANGE,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [pickMode, setPickMode] = useState(false);
  const [inView, setInView] = useState(false);
  const [visibleIds, setVisibleIds] = useState<Set<string> | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [watchAreaOpen, setWatchAreaOpen] = useState(false);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>(loadBasemap);
  const [aerialCapture, setAerialCapture] = useState<AerialCapture | null | undefined>(undefined);
  const [location, setLocation] = useState<Location | null>(loadLocation);
  const [showFlights, setShowFlights] = useState(
    () => window.localStorage.getItem(FLIGHTS_KEY) === "1",
  );
  const [showFlightTrails, setShowFlightTrails] = useState(
    () => window.localStorage.getItem(FLIGHT_TRAILS_KEY) === "1",
  );
  const [flights, setFlights] = useState<GeoJSON.FeatureCollection>({
    type: "FeatureCollection",
    features: [],
  });
  const [flightsStatus, setFlightsStatus] = useState<{ loading: boolean; error: string | null }>({
    loading: false,
    error: null,
  });
  const [listTab, setListTab] = useState<"events" | "flights">("events");

  const data = useGaiaData(filters, zone);
  const clock = useMapClock(data.meta?.activeWindowHours ?? 48);

  useEffect(() => {
    if (location) window.localStorage.setItem(LOCATION_KEY, JSON.stringify(location));
  }, [location]);

  useEffect(() => {
    window.localStorage.setItem(BASEMAP_KEY, basemap);
  }, [basemap]);

  useEffect(() => {
    window.localStorage.setItem(FLIGHTS_KEY, showFlights ? "1" : "0");
  }, [showFlights]);

  useEffect(() => {
    window.localStorage.setItem(FLIGHT_TRAILS_KEY, showFlightTrails ? "1" : "0");
  }, [showFlightTrails]);

  // A fresh object every time, so clicking the same row twice re-centres.
  const onSelectEvent = useCallback((event: HazardEvent) => {
    setSelectedId(event.id);
    if (event.longitude !== null && event.latitude !== null) {
      setFocus({ longitude: event.longitude, latitude: event.latitude });
    }
  }, []);

  const onIngested = useCallback(
    (event: HazardEvent) => {
      onSelectEvent(event);
      data.reloadEvents();
    },
    [onSelectEvent, data.reloadEvents],
  );

  const onPickLocation = useCallback((longitude: number, latitude: number) => {
    setLocation({ longitude, latitude });
    setPickMode(false);
  }, []);

  const onUseMyLocation = useCallback(() => {
    navigator.geolocation?.getCurrentPosition(
      (position) =>
        setLocation({
          longitude: position.coords.longitude,
          latitude: position.coords.latitude,
        }),
      () => setPickMode(true),
    );
  }, []);

  const onMarkRead = useCallback(
    (id: string) => {
      void api.markRead(id).then(data.reloadNotifications);
    },
    [data.reloadNotifications],
  );

  const onArchive = useCallback(
    (id: string) => {
      void api.archiveNotification(id).then(data.reloadNotifications);
    },
    [data.reloadNotifications],
  );

  // Alerts reference an event that may sit outside the current filters, so
  // the map only re-centres when that event's coordinates are actually loaded.
  const onSelectNotification = useCallback(
    (eventId: string) => {
      setSelectedId(eventId);
      const event = data.events.find((candidate) => candidate.id === eventId);
      if (event && event.longitude !== null && event.latitude !== null) {
        setFocus({ longitude: event.longitude, latitude: event.latitude });
      }
    },
    [data.events],
  );

  const unread = useMemo(
    () => data.notifications.filter((notification) => notification.readAt === null).length,
    [data.notifications],
  );

  const listedEvents = useMemo(
    () =>
      inView && visibleIds
        ? data.events.filter((event) => visibleIds.has(event.id))
        : data.events,
    [inView, visibleIds, data.events],
  );

  const model = data.meta?.seismicModel;

  // The clock spans the server's active window and drives the wavefront
  // animation, so it does not follow the filter. Say when the two differ.
  const windowHours = data.meta?.activeWindowHours ?? 48;
  const clockNote =
    filters.range.kind === "rolling" && filters.range.hours === windowHours
      ? null
      : `Filtered to ${rangeSummary(filters.range)}`;

  const rightRailOpen = selectedId !== null || alertsOpen || watchAreaOpen;

  return (
    <div className={`app${rightRailOpen ? "" : " no-right"}${leftCollapsed ? " no-left" : ""}`}>
      {model ? (
        <MapView
          events={data.eventFeatures}
          frames={data.frames}
          watchAreas={data.watchAreas}
          selectedId={selectedId}
          focus={focus}
          model={model}
          clock={clock}
          onSelect={setSelectedId}
          onPickLocation={onPickLocation}
          pickMode={pickMode}
          basemap={basemap}
          imageryDate={imageryDate(filters.range)}
          onAerialCapture={setAerialCapture}
          trackVisible={inView}
          onVisibleChange={setVisibleIds}
          showFlights={showFlights}
          showFlightTrails={showFlightTrails}
          showAsh={filters.hazardTypes.includes("ASH")}
          onFlightsData={setFlights}
          onFlightsStatus={setFlightsStatus}
        />
      ) : null}

      <ImageryAgeBadge
        basemap={basemap}
        imageryDate={imageryDate(filters.range)}
        aerialCapture={aerialCapture}
      />

      <TopBar
        filters={filters}
        onFilters={setFilters}
        status={data.status}
        unread={unread}
        alertsTotal={data.notifications.length}
        alertsOpen={alertsOpen}
        onAlerts={() => setAlertsOpen((open) => !open)}
        watchAreaOpen={watchAreaOpen}
        onWatchArea={() => setWatchAreaOpen((open) => !open)}
        pickMode={pickMode}
        onPickMode={setPickMode}
        hasLocation={location !== null}
        onUseMyLocation={onUseMyLocation}
        basemap={basemap}
        onBasemap={setBasemap}
        imageryDate={imageryDate(filters.range)}
        onReload={data.reloadEvents}
        onSettings={() => setSettingsOpen(true)}
        onLogs={() => setLogsOpen(true)}
        showFlights={showFlights}
        onFlights={setShowFlights}
        showFlightTrails={showFlightTrails}
        onFlightTrails={setShowFlightTrails}
        flightsLoading={flightsStatus.loading}
      />

      {settingsOpen ? (
        <SettingsModal onClose={() => setSettingsOpen(false)} onIngested={onIngested} />
      ) : null}
      {logsOpen ? <LogsPanel onClose={() => setLogsOpen(false)} /> : null}

      <button
        className="btn rail-toggle"
        onClick={() => setLeftCollapsed((collapsed) => !collapsed)}
        type="button"
        title={leftCollapsed ? "Show sidebar" : "Hide sidebar"}
        style={{ left: leftCollapsed ? 10 : 350 }}
      >
        {leftCollapsed ? "›" : "‹"}
      </button>

      <div className={`rail left${leftCollapsed ? " collapsed" : ""}`}>
        <section className="panel glass grow">
          <header className="panel-head">
            <div className="tab-bar">
              <button
                className={`tab-btn${listTab === "events" ? " on" : ""}`}
                onClick={() => setListTab("events")}
                type="button"
              >
                Active events
              </button>
              <button
                className={`tab-btn${listTab === "flights" ? " on" : ""}`}
                onClick={() => setListTab("flights")}
                type="button"
              >
                Flights
              </button>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              {listTab === "events" ? (
                <button
                  className={`btn${inView ? " on" : ""}`}
                  onClick={() => setInView(!inView)}
                  type="button"
                  aria-pressed={inView}
                  title="Limit the list to events drawn in the current map view"
                >
                  In view
                </button>
              ) : null}
              <span className="tag">
                {listTab === "events" ? listedEvents.length : flights.features.length}
              </span>
            </div>
          </header>

          {listTab === "events" ? (
            <EventList
              events={listedEvents}
              selectedId={selectedId}
              onSelect={onSelectEvent}
              inView={inView}
              range={filters.range}
              onRange={(range: TimeRange) => setFilters({ ...filters, range })}
            />
          ) : (
            <FlightList flights={flights} enabled={showFlights} status={flightsStatus} />
          )}
        </section>
        <ProviderHealthPanel providers={data.providers} />
        <Legend meta={data.meta} />
      </div>

      <div className={`rail right${rightRailOpen ? "" : " collapsed"}`}>
        {selectedId ? (
          <EventDetail
            eventId={selectedId}
            location={location}
            clock={clock}
            onClose={() => setSelectedId(null)}
          />
        ) : alertsOpen ? (
          <NotificationFeed
            notifications={data.notifications}
            onSelect={onSelectNotification}
            onMarkRead={onMarkRead}
            onArchive={onArchive}
            onClose={() => setAlertsOpen(false)}
          />
        ) : null}
        {watchAreaOpen ? (
          <WatchAreaPanel
            watchAreas={data.watchAreas}
            location={location}
            onChanged={data.reloadWatchAreas}
            onClose={() => setWatchAreaOpen(false)}
          />
        ) : null}
      </div>

      <ClockBar clock={clock} note={clockNote} />

      {data.error ? (
        <div
          className="alert solid"
          style={{ position: "absolute", bottom: 92, left: "50%", transform: "translateX(-50%)" }}
        >
          <span className="alert-title">Cannot reach the local service</span>
          <span className="alert-body">{data.error}</span>
        </div>
      ) : null}
    </div>
  );
}
