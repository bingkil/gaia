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
export type Shape = "circle" | "triangle" | "diamond";

export const SHAPE_BY_HAZARD: Record<HazardType, Shape> = {
  EARTHQUAKE: "circle",
  VOLCANO: "triangle",
  ASH: "diamond",
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
          shape: SHAPE_BY_HAZARD[props.hazardType],
          icon: `gaia-${SHAPE_BY_HAZARD[props.hazardType]}-${severity}`,
          retracted: props.state === "RETRACTED",
          sizeScale: 0.7 + severity * 0.18,
        },
      };
    }),
  };
}
