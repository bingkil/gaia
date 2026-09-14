import type { Map as MapLibreMap } from "maplibre-gl";
import { SEVERITY_COLOURS, type Shape } from "./severity";

const SIZE = 48;
const SHAPES: Shape[] = ["circle", "triangle", "diamond"];

function drawShape(ctx: CanvasRenderingContext2D, shape: Shape, r: number): void {
  const c = SIZE / 2;
  ctx.beginPath();
  switch (shape) {
    case "circle":
      ctx.arc(c, c, r, 0, Math.PI * 2);
      break;
    case "triangle": {
      const h = r * 1.15;
      ctx.moveTo(c, c - h);
      ctx.lineTo(c + h * 0.92, c + h * 0.72);
      ctx.lineTo(c - h * 0.92, c + h * 0.72);
      break;
    }
    case "diamond":
      ctx.moveTo(c, c - r * 1.2);
      ctx.lineTo(c + r * 1.2, c);
      ctx.lineTo(c, c + r * 1.2);
      ctx.lineTo(c - r * 1.2, c);
      break;
  }
  ctx.closePath();
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

      ctx.shadowColor = fill;
      ctx.shadowBlur = 14;
      drawShape(ctx, shape, radius);
      ctx.fillStyle = `${fill}cc`;
      ctx.fill();

      ctx.shadowBlur = 0;
      drawShape(ctx, shape, radius);
      ctx.lineWidth = 2;
      ctx.strokeStyle = "#ffffff";
      ctx.globalAlpha = 0.92;
      ctx.stroke();

      map.addImage(name, ctx.getImageData(0, 0, SIZE, SIZE), { pixelRatio: 2 });
    }
  }
}
