import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  ScaleControl,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { EventFeatureProperties, SeismicModel, WatchArea } from "../api/types";
import { ago, coordText, frpText, magnitudeText } from "../components/format";
import { PROVENANCE_MARKS } from "../components/ProvenanceBadge";
import { circlePolygon, framesAt, surfaceWaveRadiusKm } from "./geometry";
import { registerIcons } from "./icons";
import {
  LAYER_AERIAL,
  LAYER_EVENT_HALO,
  LAYER_EVENT_ICONS,
  LAYER_QUAKE_PULSE,
  PULSE_WINDOW_SECONDS,
  SRC_EVENTS,
  SRC_FRAMES,
  SRC_WATCH,
  SRC_WAVEFRONT,
  addAerial,
  addLayers,
  pulsePaint,
  setData,
} from "./layers";
import {
  FLAME_PATH,
  GLYPH_BY_SHAPE,
  SHAPE_BY_HAZARD,
  VOLCANO_PATH,
  severityColour,
  severityOf,
} from "./severity";
import type { MapClock } from "./useMapClock";

const BASEMAP = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

// Bundlers cannot resolve MapLibre 6's default worker path; see vite.config.ts.
setWorkerUrl(workerUrl);

/** Past this much elapsed time a wavefront has long since swept the region. */
const WAVEFRONT_MAX_SECONDS = 900;
const WAVEFRONT_MAX_RADIUS_KM = 3000;

/** A wave ring moves a few km per frame; 10 Hz is indistinguishable from 60. */
const ANIMATION_INTERVAL_MS = 100;

/** Close enough to read the shape of a coastline without losing context. */
const FOCUS_ZOOM = 5.5;

export interface MapFocus {
  longitude: number;
  latitude: number;
}

interface Props {
  events: GeoJSON.FeatureCollection;
  frames: GeoJSON.FeatureCollection | null;
  watchAreas: WatchArea[];
  selectedId: string | null;
  focus: MapFocus | null;
  model: SeismicModel;
  clock: MapClock;
  onSelect: (eventId: string) => void;
  onPickLocation: (lon: number, lat: number) => void;
  pickMode: boolean;
  aerial: boolean;
  trackVisible: boolean;
  onVisibleChange: (eventIds: Set<string>) => void;
}

/**
 * Built as DOM rather than HTML: place names come from upstream feeds, so they
 * are never parsed as markup.
 */
const SVG_NS = "http://www.w3.org/2000/svg";

function pathMark(d: string, colour: string): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 12 12");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  path.setAttribute("fill", colour);
  svg.append(path);
  return svg;
}

function tooltipContent(
  props: EventFeatureProperties,
  coordinates: [number, number],
): HTMLElement {
  const root = document.createElement("div");
  root.className = "map-tip-body";

  const head = document.createElement("div");
  head.className = "map-tip-head";

  const colour = severityColour(severityOf(props.hazardType, props.magnitude, props.alertLevel));
  const mark = document.createElement("span");
  mark.className = "map-tip-mark";
  mark.style.color = colour;
  if (props.hazardType === "WILDFIRE") {
    mark.append(pathMark(FLAME_PATH, colour));
  } else if (props.hazardType === "VOLCANO") {
    mark.append(pathMark(VOLCANO_PATH, colour));
  } else if (props.hazardType === "EARTHQUAKE") {
    mark.textContent = `M ${magnitudeText(props.magnitude)}`;
  } else {
    mark.textContent = GLYPH_BY_SHAPE[SHAPE_BY_HAZARD[props.hazardType]];
  }
  head.append(mark);

  const title = document.createElement("span");
  title.className = "map-tip-title";
  // A satellite fire has no name, so its position is the only honest title.
  title.textContent =
    props.volcanoName ??
    props.place ??
    coordText(coordinates[0], coordinates[1]) ??
    "Unknown region";
  head.append(title);
  root.append(head);

  const provenance = PROVENANCE_MARKS[props.provenanceClass];
  const label = document.createElement("div");
  label.className = `provenance ${props.provenanceClass}`;
  label.title = props.label;
  const glyph = document.createElement("span");
  glyph.className = "provenance-glyph";
  glyph.textContent = provenance.glyph;
  label.append(glyph, document.createTextNode(provenance.code));
  root.append(label);

  const meta = document.createElement("div");
  meta.className = "map-tip-meta";
  const fire = props.hazardType === "WILDFIRE";
  // The source strips null properties, so absent and null both arrive as undefined.
  meta.textContent = [
    typeof props.depthKm === "number" ? `${Math.round(props.depthKm)} km deep` : null,
    fire && typeof props.detectionCount === "number"
      ? `${props.detectionCount} detections`
      : null,
    fire ? frpText(props.maxFrpMw) : null,
    props.alertLevel,
    ago(props.dataAgeSeconds),
  ]
    .filter(Boolean)
    .join(" · ");
  root.append(meta);

  if (props.state === "RETRACTED") {
    const retracted = document.createElement("div");
    retracted.className = "map-tip-retracted";
    retracted.textContent = "Retracted by the source";
    root.append(retracted);
  }

  return root;
}

function wavefrontFeatures(
  events: GeoJSON.FeatureCollection,
  nowMs: number,
  model: SeismicModel,
): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];

  for (const feature of events.features) {
    const props = feature.properties as unknown as EventFeatureProperties;
    if (props.hazardType !== "EARTHQUAKE" || props.originTimeMs === null) continue;
    if (props.state === "RETRACTED") continue;

    const elapsed = (nowMs - props.originTimeMs) / 1000;
    if (elapsed <= 0 || elapsed > WAVEFRONT_MAX_SECONDS) continue;
    if (feature.geometry.type !== "Point") continue;

    const [lon, lat] = feature.geometry.coordinates as [number, number];
    const depth = props.depthKm ?? 10;
    const fade = 1 - elapsed / WAVEFRONT_MAX_SECONDS;

    for (const [phase, velocity] of [
      ["P", model.p_velocity_km_s],
      ["S", model.s_velocity_km_s],
    ] as const) {
      const radius = surfaceWaveRadiusKm(elapsed, depth, velocity);
      if (radius <= 1 || radius > WAVEFRONT_MAX_RADIUS_KM) continue;
      features.push({
        type: "Feature",
        geometry: circlePolygon(lon, lat, radius),
        properties: { phase, opacity: Math.max(0.12, fade * 0.85), eventId: props.eventId },
      });
    }
  }

  return { type: "FeatureCollection", features };
}

/** Repainting the pulse costs a frame, so only do it while one is running. */
function hasPulsingQuake(events: GeoJSON.FeatureCollection, nowMs: number): boolean {
  return events.features.some((feature) => {
    const props = feature.properties as unknown as EventFeatureProperties;
    if (props.hazardType !== "EARTHQUAKE" || props.originTimeMs === null) return false;
    if (props.state === "RETRACTED") return false;
    const age = (nowMs - props.originTimeMs) / 1000;
    return age >= 0 && age <= PULSE_WINDOW_SECONDS;
  });
}

function watchCollection(areas: WatchArea[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: areas
      .filter((area) => area.enabled)
      .map((area) => ({
        type: "Feature" as const,
        geometry:
          area.geometry.type === "Point" && area.radius_km > 0
            ? circlePolygon(
                (area.geometry as GeoJSON.Point).coordinates[0] ?? 0,
                (area.geometry as GeoJSON.Point).coordinates[1] ?? 0,
                area.radius_km,
              )
            : area.geometry,
        properties: { watchAreaId: area.id, name: area.name },
      })),
  };
}

export function MapView(props: Props): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const readyRef = useRef(false);
  const visibleKeyRef = useRef<string | null>(null);
  const reportVisibleRef = useRef<(() => void) | null>(null);

  // The animation loop reads these refs so that new data never restarts it.
  const latest = useRef(props);
  latest.current = props;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      style: BASEMAP,
      center: [118, -2],
      zoom: 3,
      attributionControl: { compact: true },
      maxPitch: 0,
    });
    mapRef.current = map;

    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");

    // "style.load" is the point at which sources, layers and images may be
    // added. "load" additionally waits for a complete first paint, which never
    // settles while tiles are still streaming.
    map.on("style.load", () => {
      registerIcons(map);
      addLayers(map);
      addAerial(map);
      readyRef.current = true;
      map.getContainer().dataset["mapReady"] = "true";

      setData(map, SRC_EVENTS, latest.current.events);
      setData(map, SRC_WATCH, watchCollection(latest.current.watchAreas));
      map.setLayoutProperty(
        LAYER_AERIAL,
        "visibility",
        latest.current.aerial ? "visible" : "none",
      );
      map.setFilter(LAYER_EVENT_HALO, [
        "==",
        ["get", "eventId"],
        latest.current.selectedId ?? "__none__",
      ]);
    });

    map.on("click", LAYER_EVENT_ICONS, (event) => {
      const feature = event.features?.[0];
      const eventId = feature?.properties?.["eventId"];
      if (typeof eventId === "string") {
        latest.current.onSelect(eventId);
        event.originalEvent.stopPropagation();
      }
    });

    map.on("click", (event) => {
      if (!latest.current.pickMode) return;
      latest.current.onPickLocation(event.lngLat.lng, event.lngLat.lat);
    });

    const tip = new Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 16,
      className: "map-tip",
      maxWidth: "260px",
    });

    map.on("mousemove", LAYER_EVENT_ICONS, (event) => {
      if (latest.current.pickMode) return;
      const feature = event.features?.[0];
      if (!feature || feature.geometry.type !== "Point") return;
      tip
        .setLngLat(feature.geometry.coordinates as [number, number])
        .setDOMContent(
          tooltipContent(
            feature.properties as unknown as EventFeatureProperties,
            feature.geometry.coordinates as [number, number],
          ),
        )
        .addTo(map);
    });

    for (const [type, cursor] of [
      ["mouseenter", "pointer"],
      ["mouseleave", ""],
    ] as const) {
      map.on(type, LAYER_EVENT_ICONS, () => {
        map.getCanvas().style.cursor = latest.current.pickMode ? "crosshair" : cursor;
        if (type === "mouseleave") tip.remove();
      });
    }

    map.on("error", (event) => {
      console.error("map error", event.error?.message ?? event);
    });

    // Each setData reparses the source on a worker, so it is throttled and
    // skipped when the geometry has not actually moved. Pushing every frame
    // starves the same worker pool the basemap tiles need.
    let frame = 0;
    let lastTick = 0;
    let waveKey = "";
    let frameKey = "";
    let pulsing = false;
    const animate = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // "Visible" means actually drawn, which is what the user is looking at, and
    // it costs nothing to be right about the antimeridian and the poles. Driven
    // by map events rather than the animation loop: the browser suspends
    // requestAnimationFrame on a hidden tab, and the list must still be correct
    // when the user comes back.
    const reportVisible = (): void => {
      if (!latest.current.trackVisible || !readyRef.current) return;
      const ids = new Set<string>();
      for (const feature of map.queryRenderedFeatures({ layers: [LAYER_EVENT_ICONS] })) {
        const id = feature.properties?.["eventId"];
        if (typeof id === "string") ids.add(id);
      }
      const key = [...ids].sort().join(",");
      if (key === visibleKeyRef.current) return;
      visibleKeyRef.current = key;
      latest.current.onVisibleChange(ids);
    };
    reportVisibleRef.current = reportVisible;
    map.on("moveend", reportVisible);
    map.on("idle", reportVisible);

    const tick = (time: number): void => {
      frame = requestAnimationFrame(tick);
      if (!readyRef.current || time - lastTick < ANIMATION_INTERVAL_MS) return;
      lastTick = time;

      const now = latest.current.clock.read();

      // One last push once the window closes, so the ring is cleared rather
      // than left frozen at whatever the final frame drew.
      const active = hasPulsingQuake(latest.current.events, now);
      if (active || pulsing) {
        const pulse = pulsePaint(now, animate);
        map.setPaintProperty(LAYER_QUAKE_PULSE, "circle-radius", pulse.radius);
        map.setPaintProperty(LAYER_QUAKE_PULSE, "circle-stroke-opacity", pulse.opacity);
        pulsing = active;
      }

      const waves = wavefrontFeatures(latest.current.events, now, latest.current.model);
      const nextWaveKey = `${waves.features.length}:${Math.round(now / 1000)}`;
      if (waves.features.length > 0 || waveKey !== "") {
        if (nextWaveKey !== waveKey) {
          setData(map, SRC_WAVEFRONT, waves);
          waveKey = waves.features.length > 0 ? nextWaveKey : "";
        }
      }

      const frames = framesAt(latest.current.frames, now);
      const nextFrameKey = frames.features
        .map((f) => (f.properties as { frameId?: string }).frameId ?? "")
        .join(",");
      if (nextFrameKey !== frameKey) {
        setData(map, SRC_FRAMES, frames);
        frameKey = nextFrameKey;
      }
    };
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      readyRef.current = false;
      tip.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // A new focus object is produced per request, so re-selecting the same event
  // re-centres. flyTo is non-essential, so prefers-reduced-motion turns it into
  // a jump rather than a sweep.
  useEffect(() => {
    const map = mapRef.current;
    const focus = props.focus;
    if (!map || !focus) return;
    map.flyTo({
      center: [focus.longitude, focus.latitude],
      zoom: Math.max(map.getZoom(), FOCUS_ZOOM),
      speed: 1.4,
    });
  }, [props.focus]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    setData(map, SRC_EVENTS, props.events);
  }, [props.events]);

  // Force a fresh report, so switching the list to "in view" is not waiting on
  // the map to move. Which symbols are placed is only known after a render, and
  // the map may already be idle, so ask for one rather than wait for one.
  useEffect(() => {
    const map = mapRef.current;
    visibleKeyRef.current = null;
    if (!map) return;
    map.once("render", () => reportVisibleRef.current?.());
    map.triggerRepaint();
  }, [props.trackVisible]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    setData(map, SRC_WATCH, watchCollection(props.watchAreas));
  }, [props.watchAreas]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.setFilter(LAYER_EVENT_HALO, ["==", ["get", "eventId"], props.selectedId ?? "__none__"]);
  }, [props.selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.setLayoutProperty(LAYER_AERIAL, "visibility", props.aerial ? "visible" : "none");
  }, [props.aerial]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getCanvas().style.cursor = props.pickMode ? "crosshair" : "";
  }, [props.pickMode]);

  return <div className="map-root" ref={containerRef} />;
}
