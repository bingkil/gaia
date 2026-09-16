import type { Map as MapLibreMap } from "maplibre-gl";
import { FLAME_PATH, SEVERITY_COLOURS, type Shape, VOLCANO_PATH } from "./severity";

const SIZE = 48;
const SHAPES: Shape[] = ["circle", "volcano", "diamond", "flame"];

/** Dart silhouette on a 12x12 box, nose up, so icon-rotate can point it at true track directly. */
export const AIRCRAFT_PATH = "M6 0 L11.5 10 L6 7.6 L0.5 10 Z";
export const AIRCRAFT_ICON = "gaia-aircraft";

/** Places a 12x12 authored path centred in the canvas at the given box size. */
function boxed(path: Path2D, d: string, side: number): void {
  const c = SIZE / 2;
  path.addPath(
    new Path2D(d),
    new DOMMatrix().translateSelf(c - side / 2, c - side / 2).scaleSelf(side / 12),
  );
}

function shapePath(shape: Shape, r: number): Path2D {
  const c = SIZE / 2;
  const path = new Path2D();
  switch (shape) {
    case "circle":
      path.arc(c, c, r, 0, Math.PI * 2);
      break;
    case "volcano":
      boxed(path, VOLCANO_PATH, r * 2.4);
      break;
    case "diamond":
      path.moveTo(c, c - r * 1.2);
      path.lineTo(c + r * 1.2, c);
      path.lineTo(c, c + r * 1.2);
      path.lineTo(c - r * 1.2, c);
      break;
    case "flame":
      // The silhouette tapers, so it needs more box than a solid shape to read.
      boxed(path, FLAME_PATH, r * 2.3);
      break;
  }
  path.closePath();
  return path;
}

/**
 * Symbols are drawn per hazard shape and severity step rather than tinted at
 * render time, which keeps the glow under our control and avoids SDF tinting.
 */
export function registerIcons(map: MapLibreMap): void {
  for (const shape of SHAPES) {
    for (let severity = 1; severity <= 5; severity += 1) {
      const name = `gaia-${shape}-${severity}`;
      if (map.hasImage(name)) continue;

      const canvas = document.createElement("canvas");
      canvas.width = SIZE;
      canvas.height = SIZE;
      const ctx = canvas.getContext("2d");
      if (!ctx) continue;

      const fill = SEVERITY_COLOURS[severity - 1] ?? SEVERITY_COLOURS[0];
      const radius = 8 + severity * 1.1;
      const path = shapePath(shape, radius);

      ctx.shadowColor = fill;
      ctx.shadowBlur = 14;
      ctx.fillStyle = `${fill}cc`;
      ctx.fill(path);

      ctx.shadowBlur = 0;
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffffff";
      ctx.globalAlpha = 0.92;
      ctx.stroke(path);

      map.addImage(name, ctx.getImageData(0, 0, SIZE, SIZE), { pixelRatio: 2 });
    }
  }
}

/** A single fixed marker, unlike the hazard icons: heading is carried by icon-rotate, not artwork. */
export function registerAircraftIcon(map: MapLibreMap): void {
  if (map.hasImage(AIRCRAFT_ICON)) return;

  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const path = new Path2D();
  boxed(path, AIRCRAFT_PATH, 22);

  ctx.shadowColor = "#f0b429";
  ctx.shadowBlur = 8;
  ctx.fillStyle = "#f0b429dd";
  ctx.fill(path);

  ctx.shadowBlur = 0;
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = "#ffffff";
  ctx.globalAlpha = 0.92;
  ctx.stroke(path);

  map.addImage(AIRCRAFT_ICON, ctx.getImageData(0, 0, SIZE, SIZE), { pixelRatio: 2 });
}
