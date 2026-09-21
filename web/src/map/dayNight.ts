/**
 * Day/night terminator, approximated from the sun's position (good to a
 * fraction of a degree of declination — plenty for a visual overlay, not a
 * navigation instrument). Four nested bands stand in for the twilight
 * gradient — civil, nautical, and astronomical twilight, then full night —
 * each covering the area of the globe darker than that band's sun-altitude
 * threshold. Rendered as stacked translucent fills (see `layers.ts`), the
 * overlaps darken progressively toward full night, approximating a soft
 * gradient without needing a raster layer.
 */

const DEG = 180 / Math.PI;
const RAD = Math.PI / 180;

/** Sun altitude, degrees, marking the edge of each band. Beyond -18° the sky is fully dark. */
const BAND_ALTITUDES_DEG = [0, -6, -12, -18] as const;

/** Longitude samples per band boundary curve — smooth without being heavy. */
const SWEEP_STEPS = 180;

/** Milliseconds between 2000-01-01T00:00:00Z and 2000-01-01T12:00:00Z (the J2000 epoch). */
const J2000_EPOCH_MS = Date.UTC(2000, 0, 1, 12, 0, 0);

interface SolarPosition {
  /** Declination of the sun, degrees — the latitude directly below it. */
  declinationDeg: number;
  /** Longitude directly below the sun, degrees. */
  subsolarLongitudeDeg: number;
}

function normalizeDeg(value: number): number {
  const wrapped = value % 360;
  return wrapped < 0 ? wrapped + 360 : wrapped;
}

/**
 * Low-precision solar position (the standard approximation behind most
 * day/night map overlays, e.g. NOAA's solar calculator). Accurate to roughly
 * 0.01° in declination.
 */
function solarPosition(date: Date): SolarPosition {
  const daysSinceJ2000 = (date.getTime() - J2000_EPOCH_MS) / 86400000;
  const meanLongitudeDeg = normalizeDeg(280.46 + 0.9856474 * daysSinceJ2000);
  const meanAnomalyDeg = normalizeDeg(357.528 + 0.9856003 * daysSinceJ2000);
  const eclipticLongitudeDeg =
    meanLongitudeDeg +
    1.915 * Math.sin(meanAnomalyDeg * RAD) +
    0.02 * Math.sin(2 * meanAnomalyDeg * RAD);
  const obliquityDeg = 23.439 - 0.0000004 * daysSinceJ2000;

  const rightAscensionDeg =
    Math.atan2(
      Math.cos(obliquityDeg * RAD) * Math.sin(eclipticLongitudeDeg * RAD),
      Math.cos(eclipticLongitudeDeg * RAD),
    ) * DEG;
  const declinationDeg =
    Math.asin(Math.sin(obliquityDeg * RAD) * Math.sin(eclipticLongitudeDeg * RAD)) * DEG;

  // Greenwich mean sidereal time, in degrees.
  const gmstDeg = normalizeDeg(280.46061837 + 360.98564736629 * daysSinceJ2000);
  const subsolarLongitudeDeg = normalizeDeg(rightAscensionDeg - gmstDeg + 180) - 180;

  return { declinationDeg, subsolarLongitudeDeg };
}

/**
 * Latitude (degrees) at which the sun's altitude equals `targetAltitudeDeg`
 * on meridian `lonDeg`. Where no such latitude exists — the whole meridian is
 * permanently above or below that altitude, i.e. polar day or polar night —
 * returns whichever pole keeps the "darker than this band" region correct.
 */
function bandBoundaryLatitudeDeg(
  lonDeg: number,
  declinationDeg: number,
  subsolarLongitudeDeg: number,
  targetAltitudeDeg: number,
  nightPoleDeg: number,
): number {
  const hourAngleDeg = lonDeg - subsolarLongitudeDeg;
  const a = Math.sin(declinationDeg * RAD);
  const b = Math.cos(declinationDeg * RAD) * Math.cos(hourAngleDeg * RAD);
  const amplitude = Math.hypot(a, b);
  const target = Math.sin(targetAltitudeDeg * RAD);

  if (Math.abs(target) > amplitude) {
    // No crossing on this meridian: altitude never reaches target, so the
    // whole meridian sits on one side of the band. `target > amplitude`
    // means it never gets that bright, i.e. it is entirely inside the band.
    return target > amplitude ? -nightPoleDeg : nightPoleDeg;
  }
  const phiRad = Math.atan2(b, a);
  const latRad = Math.asin(target / amplitude) - phiRad;
  return Math.max(-90, Math.min(90, latRad * DEG));
}

function bandRing(
  declinationDeg: number,
  subsolarLongitudeDeg: number,
  targetAltitudeDeg: number,
): GeoJSON.Position[] {
  const nightPoleDeg = declinationDeg >= 0 ? -90 : 90;
  const ring: GeoJSON.Position[] = [[-180, nightPoleDeg]];
  for (let i = 0; i <= SWEEP_STEPS; i += 1) {
    const lonDeg = -180 + (360 * i) / SWEEP_STEPS;
    ring.push([
      lonDeg,
      bandBoundaryLatitudeDeg(
        lonDeg,
        declinationDeg,
        subsolarLongitudeDeg,
        targetAltitudeDeg,
        nightPoleDeg,
      ),
    ]);
  }
  ring.push([180, nightPoleDeg]);
  ring.push([-180, nightPoleDeg]);
  return ring;
}

/**
 * Four nested polygons — one per twilight band — each covering the region of
 * the globe darker than that band's sun-altitude threshold. `band` (0-3, day
 * to night) drives which stacked fill layer picks it up; see
 * `DAYNIGHT_BAND_LAYERS` in `layers.ts`.
 */
export function computeDayNightBands(date: Date): GeoJSON.FeatureCollection {
  const { declinationDeg, subsolarLongitudeDeg } = solarPosition(date);
  return {
    type: "FeatureCollection",
    features: BAND_ALTITUDES_DEG.map((altitudeDeg, band) => ({
      type: "Feature",
      properties: { band },
      geometry: {
        type: "Polygon",
        coordinates: [bandRing(declinationDeg, subsolarLongitudeDeg, altitudeDeg)],
      },
    })),
  };
}
