import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import react from "@vitejs/plugin-react";
import { type Plugin, defineConfig } from "vite";

const API = process.env.GAIA_API ?? "http://127.0.0.1:8000";

/**
 * MapLibre 6 loads its worker by URL, and that worker imports
 * ./maplibre-gl-shared.mjs relative to itself. Vite copies the worker verbatim
 * for a ?url import but knows nothing about the sibling, so it must be emitted
 * under that exact name alongside it. Without this the worker 404s and the map
 * fails silently: no error event, no console output, "load" never fires, and
 * no tile is ever requested. See maplibre/maplibre-gl-js#8018.
 */
function maplibreWorkerSibling(): Plugin {
  return {
    name: "maplibre-worker-sibling",
    apply: "build",
    generateBundle() {
      const require = createRequire(import.meta.url);
      this.emitFile({
        type: "asset",
        fileName: "assets/maplibre-gl-shared.mjs",
        source: readFileSync(
          require.resolve("maplibre-gl/dist/maplibre-gl-shared.mjs"),
          "utf8",
        ),
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), maplibreWorkerSibling()],
  build: {
    outDir: "dist",
    sourcemap: true,
    rollupOptions: {
      output: {
        // The worker resolves its sibling relatively, so it needs a stable name
        // in the same directory.
        assetFileNames: (asset) =>
          asset.names?.[0] === "maplibre-gl-worker.mjs"
            ? "assets/maplibre-gl-worker.mjs"
            : "assets/[name]-[hash][extname]",
      },
    },
  },
  server: {
    proxy: {
      "/v1": { target: API, changeOrigin: true, ws: true },
      "/healthz": { target: API, changeOrigin: true },
    },
  },
});
