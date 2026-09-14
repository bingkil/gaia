import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { HazardEvent } from "./api/types";
import { ClockBar } from "./components/ClockBar";
import { EventDetail } from "./components/EventDetail";
import { EventList } from "./components/EventList";
import { Legend } from "./components/Legend";
import { NotificationFeed } from "./components/NotificationFeed";
import { ProviderHealthPanel } from "./components/ProviderHealthPanel";
import { TopBar } from "./components/TopBar";
import { VaaIngestPanel } from "./components/VaaIngestPanel";
import { WatchAreaPanel } from "./components/WatchAreaPanel";
import { type MapFocus, MapView } from "./map/MapView";
import { useMapClock } from "./map/useMapClock";
import { type Filters, useGaiaData } from "./state/useGaiaData";

const LOCATION_KEY = "gaia.location";

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
  const [filters, setFilters] = useState<Filters>({ hazardType: "", minMagnitude: undefined });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [pickMode, setPickMode] = useState(false);
  const [location, setLocation] = useState<Location | null>(loadLocation);

  const data = useGaiaData(filters);
  const clock = useMapClock(data.meta?.activeWindowHours ?? 48);

  useEffect(() => {
    if (location) window.localStorage.setItem(LOCATION_KEY, JSON.stringify(location));
  }, [location]);

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

  const model = data.meta?.seismicModel;

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
        />
      ) : null}

      <TopBar
        filters={filters}
        onFilters={setFilters}
        status={data.status}
        unread={unread}
        pickMode={pickMode}
        onPickMode={setPickMode}
        hasLocation={location !== null}
        onUseMyLocation={onUseMyLocation}
      />

      <div className="rail left">
        <EventList events={data.events} selectedId={selectedId} onSelect={onSelectEvent} />
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

      <ClockBar clock={clock} />

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
