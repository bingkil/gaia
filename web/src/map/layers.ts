import type {
  ExpressionSpecification,
  FilterSpecification,
  GeoJSONSource,
  LayerSpecification,
  Map as MapLibreMap,
  RasterTileSource,
} from "maplibre-gl";

export const SRC_EVENTS = "gaia-events";
export const SRC_FRAMES = "gaia-frames";
export const SRC_WAVEFRONT = "gaia-wavefront";
export const SRC_WATCH = "gaia-watch";
export const SRC_AERIAL = "gaia-aerial";
export const SRC_LIVE = "gaia-live";
export const SRC_FLIGHTS = "gaia-flights";
export const SRC_FLIGHT_TRAILS = "gaia-flight-trails";
export const LAYER_EVENT_ICONS = "gaia-event-icons";
export const LAYER_EVENT_HALO = "gaia-event-halo";
export const LAYER_QUAKE_PULSE = "gaia-quake-pulse";
export const LAYER_AERIAL = "gaia-aerial-raster";
export const LAYER_LIVE = "gaia-live-raster";
export const LAYER_FLIGHTS = "gaia-flights-icons";
export const LAYER_FLIGHT_TRAILS = "gaia-flight-trails-line";
const ASH_FRAME_LAYERS = [
  "gaia-frames-forecast-fill",
  "gaia-frames-forecast-line",
  "gaia-frames-observed-fill",
  "gaia-frames-observed-line",
];

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
  // Drawn before the aircraft icons, so a plane's own marker sits on top of its trail.
  {
    id: LAYER_FLIGHT_TRAILS,
    type: "line",
    source: SRC_FLIGHT_TRAILS,
    layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
    paint: {
      "line-width": 1.6,
      "line-gradient": [
        "interpolate",
        ["linear"],
        ["line-progress"],
        0,
        "rgba(240,180,41,0)",
        1,
        "rgba(240,180,41,0.8)",
      ],
    },
  },
  {
    id: LAYER_FLIGHTS,
    type: "symbol",
    source: SRC_FLIGHTS,
    layout: {
      "icon-image": "gaia-aircraft",
      "icon-size": 0.55,
      "icon-rotate": ["get", "heading"],
      "icon-rotation-alignment": "map",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
      visibility: "none",
    },
  },
];

export function addLayers(map: MapLibreMap): void {
  for (const id of [SRC_WATCH, SRC_FRAMES, SRC_WAVEFRONT, SRC_EVENTS, SRC_FLIGHTS]) {
    if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: EMPTY });
  }
  // line-gradient requires per-vertex distance, which only lineMetrics computes.
  if (!map.getSource(SRC_FLIGHT_TRAILS)) {
    map.addSource(SRC_FLIGHT_TRAILS, { type: "geojson", data: EMPTY, lineMetrics: true });
  }
  for (const layer of LAYERS) {
    if (!map.getLayer(layer.id)) map.addLayer(layer);
  }
}

export function setFlightsVisible(map: MapLibreMap, visible: boolean): void {
  map.setLayoutProperty(LAYER_FLIGHTS, "visibility", visible ? "visible" : "none");
}

export function setFlightTrailsVisible(map: MapLibreMap, visible: boolean): void {
  map.setLayoutProperty(LAYER_FLIGHT_TRAILS, "visibility", visible ? "visible" : "none");
}

// Frame data (the ash polygons) is always fetched and kept warm; only its
// visibility follows the Ash checkbox, so re-enabling it is instant.
export function setAshFramesVisible(map: MapLibreMap, visible: boolean): void {
  for (const id of ASH_FRAME_LAYERS) {
    map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
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

/** Same VIIRS satellite the fire detections come from, so plume and marker agree. */
const GIBS_LAYER = "VIIRS_NOAA21_CorrectedReflectance_TrueColor";

function liveTiles(date: string): string[] {
  return [
    `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_LAYER}/default/${date}` +
      "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
  ];
}

/**
 * Daily true colour, published within 3.5 hours of the overpass. Coarse next to
 * the Esri imagery, but it shows today's smoke rather than a cloudless mosaic
 * from some past year. GIBS stops at zoom 9, so tiles are stretched past that.
 */
export function addLiveImagery(map: MapLibreMap, date: string): void {
  if (map.getLayer(LAYER_LIVE)) return;
  map.addSource(SRC_LIVE, {
    type: "raster",
    tiles: liveTiles(date),
    tileSize: 256,
    maxzoom: 9,
    attribution: "Imagery &copy; NASA EOSDIS GIBS &mdash; VIIRS NOAA-21",
  });
  const firstSymbol = map.getStyle().layers.find((layer) => layer.type === "symbol")?.id;
  map.addLayer(
    {
      id: LAYER_LIVE,
      type: "raster",
      source: SRC_LIVE,
      layout: { visibility: "none" },
      paint: { "raster-brightness-max": 0.95, "raster-saturation": -0.08 },
    },
    firstSymbol,
  );
}

export function setLiveImageryDate(map: MapLibreMap, date: string): void {
  const source = map.getSource(SRC_LIVE) as RasterTileSource | undefined;
  source?.setTiles(liveTiles(date));
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
