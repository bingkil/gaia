import { AIRLINE_NAMES } from "../data/airlineCodes";

const FLIGHTS_URL = "/v1/flights";

/** Fixed column layout of each row in OpenSky's `states` array (see their REST API docs). */
const ICAO24 = 0;
const CALLSIGN = 1;
const LONGITUDE = 5;
const LATITUDE = 6;
const ON_GROUND = 8;
const VELOCITY_MS = 9;
const TRUE_TRACK = 10;
const GEO_ALTITUDE_M = 13;

export interface FlightsBoundingBox {
  north: number;
  south: number;
  east: number;
  west: number;
}

export interface FlightFeatureProperties {
  icao24: string;
  callsign: string | null;
  heading: number;
  altitudeM: number | null;
  velocityMs: number | null;
}

/** The ICAO airline designator is the callsign's leading letters, e.g. "SIA" in "SIA321". */
export function airlineFromCallsign(callsign: string | null): string | null {
  const code = callsign?.match(/^[A-Z]{3}/)?.[0];
  return code ? (AIRLINE_NAMES[code] ?? null) : null;
}


/**
 * Anonymous access is rate-limited, so a failed/throttled request should leave
 * the caller's last-known frame on screen rather than blank the layer. Thrown
 * rather than returned empty, so callers can tell "no aircraft here" apart
 * from "the request failed".
 *
 * Goes through GAIA's own backend rather than OpenSky directly: OpenSky's
 * CORS header is locked to their own origin, so a browser fetch is rejected.
 */
export async function fetchFlights(
  bbox: FlightsBoundingBox,
  signal: AbortSignal,
): Promise<GeoJSON.FeatureCollection> {
  const params = new URLSearchParams({
    bbox: [bbox.west, bbox.south, bbox.east, bbox.north].map((n) => n.toFixed(4)).join(","),
  });

  const response = await fetch(`${FLIGHTS_URL}?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`flights ${response.status}`);


  const body = (await response.json()) as { states?: unknown[][] | null };
  const features: GeoJSON.Feature[] = [];

  for (const state of body.states ?? []) {
    const longitude = state[LONGITUDE] as number | null;
    const latitude = state[LATITUDE] as number | null;
    // Ground traffic is not relevant to hazard exposure and only adds clutter.
    if (longitude === null || latitude === null || state[ON_GROUND]) continue;

    const properties: FlightFeatureProperties = {
      icao24: state[ICAO24] as string,
      callsign: (state[CALLSIGN] as string | null)?.trim() || null,
      heading: (state[TRUE_TRACK] as number | null) ?? 0,
      altitudeM: state[GEO_ALTITUDE_M] as number | null,
      velocityMs: state[VELOCITY_MS] as number | null,
    };
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [longitude, latitude] },
      properties: properties as unknown as GeoJSON.GeoJsonProperties,
    });
  }

  return { type: "FeatureCollection", features };
}
