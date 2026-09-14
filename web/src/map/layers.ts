import type {
  FilterSpecification,
  GeoJSONSource,
  LayerSpecification,
  Map as MapLibreMap,
} from "maplibre-gl";

export const SRC_EVENTS = "gaia-events";
export const SRC_FRAMES = "gaia-frames";
export const SRC_WAVEFRONT = "gaia-wavefront";
export const SRC_WATCH = "gaia-watch";
export const LAYER_EVENT_ICONS = "gaia-event-icons";
export const LAYER_EVENT_HALO = "gaia-event-halo";

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

export function setData(
  map: MapLibreMap,
  sourceId: string,
  data: GeoJSON.FeatureCollection,
): void {
  const source = map.getSource(sourceId) as GeoJSONSource | undefined;
  source?.setData(data);
}
