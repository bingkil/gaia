import type {
  ExpressionSpecification,
  FilterSpecification,
  GeoJSONSource,
  LayerSpecification,
  Map as MapLibreMap,
} from "maplibre-gl";

export const SRC_EVENTS = "gaia-events";
export const SRC_FRAMES = "gaia-frames";
export const SRC_WAVEFRONT = "gaia-wavefront";
export const SRC_WATCH = "gaia-watch";
export const SRC_AERIAL = "gaia-aerial";
export const LAYER_EVENT_ICONS = "gaia-event-icons";
export const LAYER_EVENT_HALO = "gaia-event-halo";
export const LAYER_QUAKE_PULSE = "gaia-quake-pulse";
export const LAYER_AERIAL = "gaia-aerial-raster";

/** How long a quake keeps pulsing. By the end the ring has faded to nothing. */
export const PULSE_WINDOW_SECONDS = 3600;

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

const OBSERVED: FilterSpecification = ["==", ["get", "frameKind"], "OBSERVED"];
const FORECAST: FilterSpecification = ["!=", ["get", "frameKind"], "OBSERVED"];

const LAYERS: LayerSpecification[] = [
  {
    id: "gaia-watch-fill",
    type: "fill",
    source: SRC_WATCH,
    paint: { "fill-color": "#45d9c0", "fill-opacity": 0.05 },
  },
  {
    id: "gaia-watch-line",
    type: "line",
    source: SRC_WATCH,
    paint: {
      "line-color": "#45d9c0",
      "line-width": 1,
      "line-opacity": 0.5,
      "line-dasharray": [3, 3],
    },
  },
  // Observed and forecast ash are drawn by separate layers so the forecast can
  // stay dashed and dimmer. They are never given the same visual weight.
  {
    id: "gaia-frames-forecast-fill",
    type: "fill",
    source: SRC_FRAMES,
    filter: FORECAST,
    paint: { "fill-color": "#6c5ce7", "fill-opacity": 0.13 },
  },
  {
    id: "gaia-frames-forecast-line",
    type: "line",
    source: SRC_FRAMES,
    filter: FORECAST,
    paint: {
      "line-color": "#6c5ce7",
      "line-width": 1.2,
      "line-opacity": 0.8,
      "line-dasharray": [2, 2],
    },
  },
  {
    id: "gaia-frames-observed-fill",
    type: "fill",
    source: SRC_FRAMES,
    filter: OBSERVED,
    paint: { "fill-color": "#b388ff", "fill-opacity": 0.3 },
  },
  {
    id: "gaia-frames-observed-line",
    type: "line",
    source: SRC_FRAMES,
    filter: OBSERVED,
    paint: { "line-color": "#b388ff", "line-width": 1.8 },
  },
  {
    id: "gaia-wavefront-line",
    type: "line",
    source: SRC_WAVEFRONT,
    paint: {
      "line-color": ["case", ["==", ["get", "phase"], "P"], "#00a5d4", "#f2681c"],
      "line-width": ["case", ["==", ["get", "phase"], "P"], 1.2, 2],
      "line-opacity": ["get", "opacity"],
    },
  },
  {
    id: LAYER_QUAKE_PULSE,
    type: "circle",
    source: SRC_EVENTS,
    filter: [
      "all",
      ["==", ["get", "hazardType"], "EARTHQUAKE"],
      ["has", "originTimeMs"],
      ["!", ["get", "retracted"]],
    ],
    paint: {
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": ["get", "colour"],
      "circle-stroke-width": 1.6,
      "circle-radius": 0,
      "circle-stroke-opacity": 0,
    },
  },
  {
    id: LAYER_EVENT_HALO,
    type: "circle",
    source: SRC_EVENTS,
    filter: ["==", ["get", "eventId"], "__none__"],
    paint: {
      "circle-radius": 20,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": "#45d9c0",
      "circle-stroke-width": 1.5,
      "circle-stroke-opacity": 0.9,
    },
  },
  {
    id: LAYER_EVENT_ICONS,
    type: "symbol",
    source: SRC_EVENTS,
    layout: {
      "icon-image": ["get", "icon"],
      "icon-size": ["get", "sizeScale"],
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      "symbol-sort-key": ["-", 0, ["get", "severity"]],
    },
    paint: { "icon-opacity": ["case", ["get", "retracted"], 0.35, 1] },
  },
];

export function addLayers(map: MapLibreMap): void {
  for (const id of [SRC_WATCH, SRC_FRAMES, SRC_WAVEFRONT, SRC_EVENTS]) {
    if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: EMPTY });
  }
  for (const layer of LAYERS) {
    if (!map.getLayer(layer.id)) map.addLayer(layer);
  }
}

/**
 * Imagery sits above the basemap's terrain but below its labels, so switching
 * view does not cost the place names. Held just short of full brightness and
 * slightly desaturated: the markers are saturated and ringed, so they still
 * read, but raw imagery at 1.0 pulls the eye away from the severity ramp.
 */
export function addAerial(map: MapLibreMap): void {
  if (map.getLayer(LAYER_AERIAL)) return;
  map.addSource(SRC_AERIAL, {
    type: "raster",
    tiles: [
      "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    ],
    tileSize: 256,
    maxzoom: 19,
    attribution: "Imagery &copy; Esri, Maxar, Earthstar Geographics",
  });
  const firstSymbol = map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
  map.addLayer(
    {
      id: LAYER_AERIAL,
      type: "raster",
      source: SRC_AERIAL,
      layout: { visibility: "none" },
      paint: { "raster-brightness-max": 0.95, "raster-saturation": -0.08 },
    },
    firstSymbol,
  );
}

/**
 * A ring that expands and fades on each event's own clock, quickly when the
 * quake is minutes old and slowly near the end of the window, so recency reads
 * as a rate. Age drives the phase rather than wall time, which would jump every
 * time the period changed. Paint only: animating icon-size would re-lay out
 * every symbol on the map each frame.
 */
export function pulsePaint(
  nowMs: number,
  animate: boolean,
): { radius: ExpressionSpecification; opacity: ExpressionSpecification } {
  const age: ExpressionSpecification = ["/", ["-", nowMs, ["get", "originTimeMs"]], 1000];
  const period: ExpressionSpecification = [
    "interpolate",
    ["linear"],
    age,
    0,
    0.9,
    PULSE_WINDOW_SECONDS,
    4,
  ];
  // Held at mid-swell under reduced motion: the ring still marks the event and
  // still fades with age, it just does not move.
  const wave: ExpressionSpecification | number = animate
    ? ["+", 0.5, ["*", 0.5, ["sin", ["*", 6.2831853, ["%", ["/", age, period], 1]]]]]
    : 0.5;
  // The leading stop at -1s keeps a scrubbed-past event from pulsing.
  const fade: ExpressionSpecification = [
    "interpolate",
    ["linear"],
    age,
    -1,
    0,
    0,
    0.9,
    PULSE_WINDOW_SECONDS,
    0,
  ];

  return {
    radius: ["+", 5, ["*", 1.8, ["get", "severity"]], ["*", 16, wave]],
    opacity: ["*", fade, ["-", 1, ["*", 0.75, wave]]],
  };
}

export function setData(
  map: MapLibreMap,
  sourceId: string,
  data: GeoJSON.FeatureCollection,
): void {
  const source = map.getSource(sourceId) as GeoJSONSource | undefined;
  source?.setData(data);
}
