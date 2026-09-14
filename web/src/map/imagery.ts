/**
 * Esri's World Imagery basemap is a mosaic stitched from tiles flown at
 * different times in different places, so there is no single "as of" date for
 * it — the only way to know a given view's vintage is to ask the service what
 * is actually on screen there.
 */

const IDENTIFY_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/identify";

export interface AerialCapture {
  /** ISO date (YYYY-MM-DD) the visible tile was captured. */
  iso: string;
  source: string | null;
}

interface IdentifyResponse {
  results?: { attributes?: Record<string, string> }[];
}

export async function fetchAerialCapture(
  lng: number,
  lat: number,
  signal: AbortSignal,
): Promise<AerialCapture | null> {
  const params = new URLSearchParams({
    geometry: `${lng},${lat}`,
    geometryType: "esriGeometryPoint",
    sr: "4326",
    tolerance: "2",
    mapExtent: `${lng - 0.05},${lat - 0.05},${lng + 0.05},${lat + 0.05}`,
    imageDisplay: "400,400,96",
    returnGeometry: "false",
    f: "json",
  });

  const response = await fetch(`${IDENTIFY_URL}?${params.toString()}`, { signal });
  if (!response.ok) return null;

  const body = (await response.json()) as IdentifyResponse;
  const attributes = body.results?.[0]?.attributes;
  // Coarse global coverage (no per-tile capture record) reports the literal
  // string "Null" rather than omitting the field.
  const raw = attributes?.["SRC_DATE2"] ?? attributes?.["DATE (YYYYMMDD)"];
  if (!raw || raw === "Null") return null;

  // Both formats have been observed in the field: "3/14/2024" and "20240314".
  if (/^\d{8}$/.test(raw)) {
    const iso = `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
    return { iso, source: attributes?.["SOURCE"] ?? attributes?.["SOURCE_INFO"] ?? null };
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return null;
  const iso = parsed.toISOString().slice(0, 10);

  return { iso, source: attributes?.["SOURCE"] ?? attributes?.["SOURCE_INFO"] ?? null };
}
