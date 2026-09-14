import type { EventFeatureProperties, HazardEvent, HazardType } from "../api/types";

/**
 * Severity ramp. Blue through amber to magenta, with no green and no
 * red/green pairing, so it survives the common colour vision deficiencies.
 * Colour is never the only channel: shape encodes hazard and the list always
 * carries the words.
 */
export const SEVERITY_COLOURS = [
  "#4361ee",
  "#00a5d4",
  "#f0b429",
  "#f2681c",
  "#e8336d",
] as const;

export type Severity = 1 | 2 | 3 | 4 | 5;
export type Shape = "circle" | "volcano" | "diamond" | "flame";

/**
 * Flame silhouette on a 12x12 box, shared by the map canvas and the list SVG.
 * A symmetric teardrop reads as water at marker size, so the tip leans right
 * and a second tongue rises on the left to break the droplet silhouette.
 */
export const FLAME_PATH =
  "M7.0 0.4 C7.3 2.3 8.4 3.2 9.2 4.4 C10.2 5.9 10.0 8.2 8.6 9.7 " +
  "C7.2 11.2 4.6 11.5 2.9 10.2 C1.3 9.0 0.9 6.7 1.9 5.0 " +
  "C2.4 4.2 3.1 3.7 3.8 3.0 C3.7 4.3 3.9 5.2 4.4 5.9 " +
  "C5.3 4.3 6.0 2.3 7.0 0.4 Z";

/**
 * Cone with a crater notch on a 12x12 box. The flat rim is what separates it
 * from a plain triangle once the marker is down to a few pixels.
 */
export const VOLCANO_PATH = "M3 1.6 H4.9 L6 3.2 L7.1 1.6 H9 L11.7 10.4 H0.3 Z";

export const SHAPE_BY_HAZARD = {
  EARTHQUAKE: "circle",
  VOLCANO: "volcano",
  ASH: "diamond",
  WILDFIRE: "flame",
} as const satisfies Record<HazardType, Shape>;

/** Text stand-ins. The drawn shapes have no character that reads as them. */
export const GLYPH_BY_SHAPE: Record<Exclude<Shape, "flame" | "volcano">, string> = {
  circle: "\u25cf",
  diamond: "\u25c6",
};

export function severityColour(severity: Severity): string {
  return SEVERITY_COLOURS[severity - 1] ?? SEVERITY_COLOURS[0];
}

function magnitudeSeverity(magnitude: number | null): Severity {
  if (magnitude === null) return 1;
  if (magnitude >= 7) return 5;
  if (magnitude >= 6) return 4;
  if (magnitude >= 4.5) return 3;
  if (magnitude >= 3) return 2;
  return 1;
}

function alertLevelSeverity(level: string | null): Severity {
  switch ((level ?? "").toUpperCase()) {
    case "RED":
      return 5;
    case "ORANGE":
      return 4;
    case "YELLOW":
      return 3;
    default:
      return 2;
  }
}

/**
 * Severity is a display ranking for sorting and symbol size. It is explicitly
 * not an intensity estimate and never claims one.
 */
export function severityOf(
  hazardType: HazardType,
  magnitude: number | null,
  alertLevel: string | null,
): Severity {
  switch (hazardType) {
    case "EARTHQUAKE":
      return magnitudeSeverity(magnitude);
    case "VOLCANO":
      return alertLevelSeverity(alertLevel);
    case "ASH":
      return 4;
    // GDACS grades a fire on the same green/orange/red scale as a volcano.
    case "WILDFIRE":
      return alertLevelSeverity(alertLevel);
  }
}

export function severityOfEvent(event: HazardEvent): Severity {
  return severityOf(event.hazard_type, event.summary.magnitude, event.summary.alert_level);
}

/**
 * Presentation properties are attached here rather than served by the API, so
 * the backend stays free of styling concerns.
 */
export function decorateEventFeatures(
  collection: GeoJSON.FeatureCollection,
): GeoJSON.FeatureCollection {
  return {
    ...collection,
    features: collection.features.map((feature) => {
      const props = feature.properties as unknown as EventFeatureProperties;
      const severity = severityOf(props.hazardType, props.magnitude, props.alertLevel);
      return {
        ...feature,
        properties: {
          ...props,
          severity,
          colour: severityColour(severity),
          shape: SHAPE_BY_HAZARD[props.hazardType],
          icon: `gaia-${SHAPE_BY_HAZARD[props.hazardType]}-${severity}`,
          retracted: props.state === "RETRACTED",
          sizeScale: 0.7 + severity * 0.18,
        },
      };
    }),
  };
}
