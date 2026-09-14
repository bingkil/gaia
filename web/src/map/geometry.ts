import type { FrameFeatureProperties } from "../api/types";

const EARTH_RADIUS_KM = 6371.0088;

/** Mirrors gaia.domain.geo.circle_geojson so map rings match server geometry. */
export function circlePolygon(
  lon: number,
  lat: number,
  radiusKm: number,
  segments = 72,
): GeoJSON.Polygon {
  const coords: GeoJSON.Position[] = [];
  const latRad = (lat * Math.PI) / 180;
  const cosLat = Math.max(Math.cos(latRad), 1e-9);

  for (let i = 0; i <= segments; i += 1) {
    const bearing = (2 * Math.PI * i) / segments;
    const dLat = (radiusKm / EARTH_RADIUS_KM) * Math.cos(bearing);
    const dLon = ((radiusKm / EARTH_RADIUS_KM) * Math.sin(bearing)) / cosLat;
    coords.push([lon + (dLon * 180) / Math.PI, lat + (dLat * 180) / Math.PI]);
  }
  return { type: "Polygon", coordinates: [coords] };
}

/** Mirrors gaia.domain.geo.surface_wave_radius_km. */
export function surfaceWaveRadiusKm(
  elapsedSeconds: number,
  depthKm: number,
  velocityKmS: number,
): number {
  const travelled = velocityKmS * Math.max(0, elapsedSeconds);
  return Math.sqrt(Math.max(0, travelled * travelled - depthKm * depthKm));
}

/**
 * Choose the ash frame to draw at a given time.
 *
 * Frames are shown discretely. Two advisory polygons are never blended into an
 * in-between shape, because that shape would be something no forecaster
 * issued. Before the first frame nothing is drawn, and a frame older than
 * MAX_FRAME_AGE_MS is dropped rather than left implying current coverage.
 */
const MAX_FRAME_AGE_MS = 6 * 3_600_000;

export function framesAt(
  collection: GeoJSON.FeatureCollection | null,
  timeMs: number,
): GeoJSON.FeatureCollection {
  const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
  if (!collection) return empty;

  const bestByEvent = new Map<string, GeoJSON.Feature>();

  for (const feature of collection.features) {
    const props = feature.properties as unknown as FrameFeatureProperties;
    if (props.validTimeMs > timeMs) continue;
    if (timeMs - props.validTimeMs > MAX_FRAME_AGE_MS) continue;

    const current = bestByEvent.get(props.eventId);
    const currentTime = current
      ? (current.properties as unknown as FrameFeatureProperties).validTimeMs
      : -Infinity;

    if (props.validTimeMs > currentTime) bestByEvent.set(props.eventId, feature);
  }

  return { type: "FeatureCollection", features: [...bestByEvent.values()] };
}

/** The next frame after the current time, so the panel can say what is coming. */
export function nextFrameAfter(
  collection: GeoJSON.FeatureCollection | null,
  timeMs: number,
): FrameFeatureProperties | null {
  if (!collection) return null;

  let best: FrameFeatureProperties | null = null;
  for (const feature of collection.features) {
    const props = feature.properties as unknown as FrameFeatureProperties;
    if (props.validTimeMs <= timeMs) continue;
    if (best === null || props.validTimeMs < best.validTimeMs) best = props;
  }
  return best;
}
