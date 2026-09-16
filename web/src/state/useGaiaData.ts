import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  HazardEvent,
  HazardType,
  Meta,
  NotificationRecord,
  ProviderRecord,
  WatchArea,
} from "../api/types";
import { decorateEventFeatures } from "../map/severity";
import { type TimeRange, rangeParams } from "./timeRange";
import type { TimeZonePref } from "./timeZone";
import { useRealtime } from "./useRealtime";

export const ALL_HAZARD_TYPES: HazardType[] = ["EARTHQUAKE", "VOLCANO", "ASH", "WILDFIRE"];

export interface Filters {
  hazardTypes: HazardType[];
  minMagnitude: number | undefined;
  range: TimeRange;
}

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export interface GaiaData {
  meta: Meta | null;
  events: HazardEvent[];
  eventFeatures: GeoJSON.FeatureCollection;
  frames: GeoJSON.FeatureCollection | null;
  watchAreas: WatchArea[];
  providers: ProviderRecord[];
  notifications: NotificationRecord[];
  status: "connecting" | "live" | "offline";
  error: string | null;
  reloadWatchAreas: () => void;
  reloadNotifications: () => void;
  reloadEvents: () => void;
}

export function useGaiaData(filters: Filters, zone: TimeZonePref): GaiaData {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [events, setEvents] = useState<HazardEvent[]>([]);
  const [eventFeatures, setEventFeatures] = useState<GeoJSON.FeatureCollection>(EMPTY);
  const [frames, setFrames] = useState<GeoJSON.FeatureCollection | null>(null);
  const [watchAreas, setWatchAreas] = useState<WatchArea[]>([]);
  const [providers, setProviders] = useState<ProviderRecord[]>([]);
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  const zoneRef = useRef(zone);
  zoneRef.current = zone;

  const report = useCallback((err: unknown) => {
    setError(err instanceof Error ? err.message : String(err));
  }, []);

  const reloadEvents = useCallback(() => {
    // A checkbox row with nothing ticked means "show nothing": the API has no
    // way to ask for zero hazard types, so that case is handled without a request.
    if (filtersRef.current.hazardTypes.length === 0) {
      setEvents([]);
      setEventFeatures(EMPTY);
      setFrames(EMPTY);
      setError(null);
      return;
    }
    const query = {
      hazardType:
        filtersRef.current.hazardTypes.length === ALL_HAZARD_TYPES.length
          ? undefined
          : filtersRef.current.hazardTypes.join(","),
      minMagnitude: filtersRef.current.minMagnitude,
      ...rangeParams(filtersRef.current.range, zoneRef.current),
    };
    Promise.all([api.events(query), api.mapEvents(query), api.mapFrames()])
      .then(([list, map, frameData]) => {
        setEvents(list.events);
        setEventFeatures(decorateEventFeatures(map));
        setFrames(frameData);
        setError(null);
      })
      .catch(report);
  }, [report]);

  const reloadWatchAreas = useCallback(() => {
    api.watchAreas().then((r) => setWatchAreas(r.watchAreas)).catch(report);
  }, [report]);

  const reloadNotifications = useCallback(() => {
    api.notifications().then((r) => setNotifications(r.notifications)).catch(report);
  }, [report]);

  const reloadProviders = useCallback(() => {
    api.providerHealth().then((r) => setProviders(r.providers)).catch(report);
  }, [report]);

  useEffect(() => {
    api.meta().then(setMeta).catch(report);
    reloadWatchAreas();
    reloadNotifications();
    reloadProviders();
  }, [report, reloadWatchAreas, reloadNotifications, reloadProviders]);

  useEffect(() => {
    reloadEvents();
  }, [reloadEvents, filters.hazardTypes, filters.minMagnitude, filters.range, zone]);

  const onChange = useCallback(
    (subjects: Set<string>) => {
      if (subjects.has("provider.health")) reloadProviders();
      if (subjects.has("notification.created")) reloadNotifications();

      const touchesEvents = [...subjects].some(
        (s) => s.startsWith("canonical.event.") || s === "resync",
      );
      if (touchesEvents) reloadEvents();
      if (subjects.has("resync")) {
        reloadNotifications();
        reloadProviders();
      }
    },
    [reloadEvents, reloadNotifications, reloadProviders],
  );

  const status = useRealtime(onChange);

  // Provider staleness is time-based, so it must be re-read even when the bus
  // is quiet. A silent feed is exactly the case this has to catch.
  useEffect(() => {
    const id = window.setInterval(reloadProviders, 30_000);
    return () => window.clearInterval(id);
  }, [reloadProviders]);

  return useMemo(
    () => ({
      meta,
      events,
      eventFeatures,
      frames,
      watchAreas,
      providers,
      notifications,
      status,
      error,
      reloadWatchAreas,
      reloadNotifications,
      reloadEvents,
    }),
    [
      meta,
      events,
      eventFeatures,
      frames,
      watchAreas,
      providers,
      notifications,
      status,
      error,
      reloadWatchAreas,
      reloadNotifications,
      reloadEvents,
    ],
  );
}
