import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { HazardEvent } from "./api/types";
import { ClockBar } from "./components/ClockBar";
import { EventDetail } from "./components/EventDetail";
import { EventList } from "./components/EventList";
import { ImageryAgeBadge } from "./components/ImageryAgeBadge";
import { Legend } from "./components/Legend";
import { NotificationFeed } from "./components/NotificationFeed";
import { ProviderHealthPanel } from "./components/ProviderHealthPanel";
import { SettingsModal } from "./components/SettingsModal";
import { TopBar } from "./components/TopBar";
import { VaaIngestPanel } from "./components/VaaIngestPanel";
import { WatchAreaPanel } from "./components/WatchAreaPanel";
import { type Basemap, type MapFocus, MapView } from "./map/MapView";
import type { AerialCapture } from "./map/imagery";
import { useMapClock } from "./map/useMapClock";
import { DEFAULT_RANGE, type TimeRange, imageryDate, rangeSummary } from "./state/timeRange";
import { useTimeZone } from "./state/timeZone";
import { type Filters, useGaiaData } from "./state/useGaiaData";

const LOCATION_KEY = "gaia.location";
const BASEMAP_KEY = "gaia.basemap";
const AERIAL_KEY = "gaia.aerial";

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
    hazardType: "",
    minMagnitude: undefined,
    range: DEFAULT_RANGE,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [pickMode, setPickMode] = useState(false);
  const [inView, setInView] = useState(false);
  const [visibleIds, setVisibleIds] = useState<Set<string> | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>(loadBasemap);
  const [aerialCapture, setAerialCapture] = useState<AerialCapture | null | undefined>(undefined);
  const [location, setLocation] = useState<Location | null>(loadLocation);

  const data = useGaiaData(filters, zone);
  const clock = useMapClock(data.meta?.activeWindowHours ?? 48);

  useEffect(() => {
    if (location) window.localStorage.setItem(LOCATION_KEY, JSON.stringify(location));
  }, [location]);

  useEffect(() => {
    window.localStorage.setItem(BASEMAP_KEY, basemap);
  }, [basemap]);

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

  return (
    <div className="app">
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
        pickMode={pickMode}
        onPickMode={setPickMode}
        hasLocation={location !== null}
        onUseMyLocation={onUseMyLocation}
        basemap={basemap}
        onBasemap={setBasemap}
        imageryDate={imageryDate(filters.range)}
        onReload={data.reloadEvents}
        onSettings={() => setSettingsOpen(true)}
      />

      {settingsOpen ? <SettingsModal onClose={() => setSettingsOpen(false)} /> : null}

      <div className="rail left">
        <EventList
          events={listedEvents}
          selectedId={selectedId}
          onSelect={onSelectEvent}
          inView={inView}
          onInView={setInView}
          range={filters.range}
          onRange={(range: TimeRange) => setFilters({ ...filters, range })}
        />
        <ProviderHealthPanel providers={data.providers} />
        <Legend meta={data.meta} />
      </div>

      <div className="rail right">
        {selectedId ? (
          <EventDetail
            eventId={selectedId}
            location={location}
            clock={clock}
            onClose={() => setSelectedId(null)}
          />
        ) : (
          <NotificationFeed
            notifications={data.notifications}
            onSelect={setSelectedId}
            onMarkRead={onMarkRead}
          />
        )}
        <WatchAreaPanel
          watchAreas={data.watchAreas}
          location={location}
          onChanged={data.reloadWatchAreas}
        />
        <VaaIngestPanel onIngested={onIngested} />
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
