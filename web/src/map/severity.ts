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
export type Shape = "circle" | "volcano" | "diamond" | "flame" | "cyclone";

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

/**
 * Two broad blades round a hollow eye on a 12x12 box. A spiral outline vanishes
 * at marker size, but the pinwheel keeps its eye and its S-shaped silhouette,
 * which no other hazard shape shares.
 */
export const CYCLONE_PATH =
  "M6.0 0.6 C9.3 0.6 11.4 3.0 11.4 5.6 C11.4 6.4 11.2 7.0 11.0 7.4 " +
  "C10.2 5.6 8.6 4.8 6.9 4.8 C5.6 4.8 4.8 5.2 4.2 5.8 C3.6 4.2 4.0 2.0 6.0 0.6 Z " +
  "M6.0 11.4 C2.7 11.4 0.6 9.0 0.6 6.4 C0.6 5.6 0.8 5.0 1.0 4.6 C1.8 6.4 3.4 7.2 5.1 7.2 " +
  "C6.4 7.2 7.2 6.8 7.8 6.2 C8.4 7.8 8.0 10.0 6.0 11.4 Z";

export const SHAPE_BY_HAZARD = {
  EARTHQUAKE: "circle",
  VOLCANO: "volcano",
  ASH: "diamond",
  WILDFIRE: "flame",
  CYCLONE: "cyclone",
} as const satisfies Record<HazardType, Shape>;

/** Text stand-ins. The drawn shapes have no character that reads as them. */
export const GLYPH_BY_SHAPE: Record<Exclude<Shape, "flame" | "volcano" | "cyclone">, string> = {
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
 * Saffir-Simpson steps from sustained wind alone, in knots. Below 64 kt the
 * scale does not apply, so those two steps are named for the storm class.
 * It is a ranking by wind, not by surge, rain or any other way a storm hurts.
 */
const CYCLONE_STEPS: { minKt: number; severity: Severity; text: string }[] = [
  { minKt: 137, severity: 5, text: "Category 5" },
  { minKt: 113, severity: 5, text: "Category 4" },
  { minKt: 96, severity: 4, text: "Category 3" },
  { minKt: 83, severity: 3, text: "Category 2" },
  { minKt: 64, severity: 3, text: "Category 1" },
  { minKt: 34, severity: 2, text: "Tropical storm" },
  { minKt: 0, severity: 1, text: "Tropical depression" },
];

export function cycloneStep(maxWindKt: number | null | undefined): {
  severity: Severity;
  text: string;
} {
  const wind = typeof maxWindKt === "number" ? maxWindKt : 0;
  const step = CYCLONE_STEPS.find((s) => wind >= s.minKt) ?? CYCLONE_STEPS[CYCLONE_STEPS.length - 1];
  return { severity: step?.severity ?? 1, text: step?.text ?? "Tropical depression" };
}

/**
 * Severity is a display ranking for sorting and symbol size. It is explicitly
 * not an intensity estimate and never claims one.
 */
export function severityOf(
  hazardType: HazardType,
  magnitude: number | null,
  alertLevel: string | null,
  maxWindKt: number | null = null,
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
    case "CYCLONE":
      return cycloneStep(maxWindKt).severity;
  }
}

export function severityOfEvent(event: HazardEvent): Severity {
  return severityOf(
    event.hazard_type,
    event.summary.magnitude,
    event.summary.alert_level,
    event.summary.max_wind_kt,
  );
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
      const severity = severityOf(
        props.hazardType,
        props.magnitude,
        props.alertLevel,
        props.maxWindKt,
      );
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
