# Day/night shading & timezone layers

## Purpose

Two optional map overlays, toggled from the "Views" dropdown in the top bar,
alongside the existing basemap/hazard toggles:

- **Day/night** — shades the night side of the globe, with a soft twilight
  gradient at the terminator.
- **Timezones** — draws timezone boundary polygons; clicking a zone shows a
  popup with its name and current local time/offset.

Both are off by default and their on/off state persists in the same
`localStorage` mechanism already used for the other view toggles (see
`web/src/App.tsx`).

## Day/night shading

- Implementation: `web/src/map/dayNight.ts` computes the sun's sub-solar
  point (declination + longitude) using the standard low-precision solar
  position formula (accurate to ~0.01°, the same approximation behind most
  day/night map overlays). No external dependency or dataset — pure math,
  recomputed on demand.
- Rendered as **four nested polygons** (civil, nautical, astronomical
  twilight, then full night), each covering the region of the globe darker
  than that band's sun-altitude threshold (0°, -6°, -12°, -18°). Drawn as
  stacked translucent fills (`web/src/map/layers.ts`,
  `DAYNIGHT_BAND_LAYERS`/`DAYNIGHT_BAND_OPACITY`), which darken progressively
  toward full night — approximating a smooth gradient without a raster tile
  layer.
- Recomputed periodically while visible (not just once on toggle) so the
  terminator advances as time passes during a session.
- Handles polar day/polar night meridians correctly (a meridian that never
  crosses a given altitude threshold resolves to fully in/out of that band
  based on which side of the equator it's on).

## Timezone layer

- Data source: Natural Earth's `ne_10m_time_zones` dataset, simplified and
  stored at `web/public/data/timezones.geojson` (~280 KB). Chosen over the
  much larger (multi-MB) timezone-boundary-builder dataset for bundle-size
  reasons.
- Rendered as a fill + line layer (`LAYER_TIMEZONES_FILL` /
  `LAYER_TIMEZONES_LINE` in `web/src/map/layers.ts`), colored by a
  categorical expression over the zone's raw UTC offset so adjacent zones are
  visually distinguishable.
- **DST handling**: the dataset's `time_zone`/`places` fields are static
  standard-time offsets and ignore daylight saving. The click popup does
  **not** use those fields for the displayed offset — instead
  `web/src/map/MapView.tsx` derives the zone's IANA-ish region from the
  feature and asks `Intl.DateTimeFormat(..., { timeZoneName: "longOffset" })`
  for the live, DST-aware offset plus the current local clock time. This
  means the popup always reflects today's actual offset (e.g. `UTC+2:00`
  during CEST rather than the dataset's fixed `UTC+1:00`), while the fill
  color (a static per-band color) does not shift with DST — only the popup
  text is live.

## UI wiring

- Toggles live in `web/src/components/TopBar.tsx`'s "Views" dropdown, wired
  through `web/src/App.tsx` (`showDayNight`, `showTimezones` state +
  localStorage persistence) down to `web/src/map/MapView.tsx`, which calls
  `addDayNight`/`setDayNightVisible` and `addTimezones`/`setTimezonesVisible`
  on the MapLibre style.

## Tests / verification

- `npx tsc -b` — clean compile.
- Manually verified in-browser: layer toggles on/off correctly, terminator
  bands render and shift over time, timezone click popup shows a live
  DST-aware offset for zones currently observing DST (verified against a
  region in CEST) vs. an unchanged offset for non-DST regions (e.g. Arizona,
  Japan).

## Known limitations / future work

- The day/night terminator uses a simplified sun-position model (no
  atmospheric refraction correction); fine for a visual overlay, not for
  precise sunrise/sunset calculations.
- The timezone fill color does not change with DST, only the popup text —
  a static per-standard-offset palette was kept for simplicity rather than
  re-coloring twice a year as regions enter/exit DST.
- No attribution/legend UI has been added for either layer yet.
