# Tropical cyclones

## Purpose

Show active tropical cyclones (hurricanes, typhoons, cyclones) on the map and in
the event list, with the issuing agency's forecast track, cone of uncertainty and
current wind extents. The UI calls the hazard "Cyclone" so one word covers every
basin.

GAIA does **not** raise alerts for cyclones. See [Alerts](#alerts).

## Sources

| Source | Coverage | Role |
|---|---|---|
| NOAA National Hurricane Center (`CurrentStorms.json`) | Atlantic, East Pacific, Central Pacific | Official advisories: position, wind, track, cone, wind radii |
| GDACS (`eventlist=TC`) | Global | Position and wind for every basin, including ones NHC does not cover |

Not included: JTWC (West Pacific / Indian Ocean) has no clean machine-readable
feed and would need text-bulletin parsing. GDACS already lists those storms, so
they appear, but without track or cone.

## Data flow

```
CurrentStorms.json ──┐
  per storm: track,  │  NhcAdapter ──► one stored payload ──► Observation(frames=[…])
  cone, radii KMZ ───┘                                              │
GDACS TC list ──► GdacsAdapter ───────────────────────────────────►│
                                                                    ▼
                                       Pipeline._process_cyclone ─► HazardEvent (CYCLONE)
                                                                    └► hazard_geometry_frame
```

- `providers/nhc.py` polls every 10 minutes (`GAIA_PROVIDERS__NHC__POLL_SECONDS`).
  A storm's three KMZ products are downloaded only when its `lastUpdate` changes.
- The listing and the three KMZ files are stored together as **one raw payload**
  (KMZ base64-encoded), so a parser fix can be replayed from disk like any other
  provider. Replay works because `parse()` is a pure function over that payload.
- A KMZ is a zip holding one KML. It is read with the standard library: the
  archive size is capped, a KML that declares a DTD or entity is refused
  (billion-laughs defence), and product URLs are restricted to
  `https://www.nhc.noaa.gov/`.
- A product that fails to download or parse is dropped with a warning; the
  storm's position and wind are still recorded.

## Event model

- New `HazardType.CYCLONE`. `EventSummary` gains `storm_name` and `max_wind_kt`.
- **Identity**: NHC uses its own id (`AL092026`); GDACS ids are namespaced
  `TC_<id>` because GDACS numbers each event type separately.
- **Fusion** (`Pipeline._open_cyclone_event`): an NHC and a GDACS report of the
  same storm become one event. They match when the names are equal
  (case-insensitive, GDACS's `-26` year suffix stripped) and the positions are
  within 300 km (GDACS lags NHC by tens of km). If either name is missing the
  radius drops to 100 km, because two unnamed depressions in one basin are not
  the same storm. Different names never merge.
- **Field authority**: NHC outranks GDACS for position, place, name and wind.
- **Provenance**: an NHC-backed event is `AUTHORITATIVE_NOTICE`, labelled
  "Official tropical cyclone advisory". GDACS alone is `SINGLE_SOURCE_RAPID`,
  labelled "Preliminary tropical cyclone report". No label mentions an
  earthquake.
- **GDACS revisions** follow the advisory episode (plus an `:ended` marker). The
  GDACS alert score barely changes while a storm moves, so using it would
  discard every position update after the first.
- **Ending**: GDACS marks a finished storm ended. An NHC-only storm has no end
  signal, so its geometry simply expires (below) and the event leaves the list
  with the time window.

## Geometry

Stored as `hazard_geometry_frame` rows; each new advisory replaces the previous
set for that event (`replace_for_event`).

| `geometry_type` | Shape | Kind | Properties |
|---|---|---|---|
| `CYCLONE_CONE` | Polygon | FORECAST | |
| `CYCLONE_TRACK` | LineString (the 120 h line, else 72 h) | FORECAST | |
| `CYCLONE_POSITION` | Point per forecast time | FORECAST | `leadHours`, `maxWindKt`, `validTimeMs` |
| `CYCLONE_WIND_RADII` | Polygon per 34/50/64 kt | OBSERVED | `windKt` |

Every frame carries `issuedAtMs` (advisory issue time). Coordinates are rounded
to 3 decimals (~100 m).

- NHC prints forecast times in local time ("7:00 PM CDT October 09, 2026").
  They are converted with a fixed table of the abbreviations NHC/CPHC use. An
  unrecognised abbreviation drops that point's time rather than guessing it; the
  point is still drawn and the detail panel shows "—".
- `/v1/map/frames.geojson` returns ash and cyclone frames together. Cyclone
  frames have `styleClass: "cyclone"`; the client filters on `geometryType`.

## Map and UI

- Marker: a two-blade pinwheel with a hollow eye (`CYCLONE_PATH`), shared by the
  canvas marker, list icon, tooltip and legend. A spiral outline vanishes at
  marker size; the pinwheel keeps its eye and an S-shaped silhouette no other
  hazard shares.
- Severity is the **Saffir–Simpson step from maximum sustained wind alone**
  (`cycloneStep` in `web/src/map/severity.ts`): <34 kt, 34–63 kt, Cat 1–2,
  Cat 3, Cat 4–5. It ignores surge, rain and flooding, which the legend says.
- Layers (`web/src/map/layers.ts`), all toggled by the Cyclone checkbox:
  wind radii (filled, nested), cone (translucent, dashed outline), forecast
  track (dashed), forecast position dots coloured by forecast wind.
- Dashed means forecast, solid means current estimate, matching the ash layers.
- Cyclone frames are shown from their advisory's issue time until a newer
  advisory replaces them, and dropped after **12 hours** (`cycloneFramesAt`), so
  a feed that went quiet does not leave a stale forecast on the map.
- Each forecast dot is labelled `+hh` (lead hours from the advisory's forecast base
  time). The label uses "Montserrat Regular", a font stack the Carto basemap style
  already loads. The detail panel adds the valid time and wind for each dot.
- The event detail shows current wind and that forecast table, with a standing
  note that the cone is only track uncertainty and damage can fall outside it.

## Alerts

`should_alert` returns `CYCLONE_ALERTS_NOT_SUPPORTED` for every cyclone. No
reviewed alert wording exists, and the fallback copy in `policy.compose` is
written for a volcano, so a cyclone that got through would produce a "Volcanic
activity reported" notification. Cyclones are map and list only.

The UI creates watch areas with the server's default hazard types (earthquake,
volcano, ash), so a cyclone can only reach `should_alert` through a watch area
created directly via the API with `CYCLONE` in `hazardTypes`. The guard exists for
that case.

## Tests

- `tests/test_engine.py`: `TestGdacsCyclone` (id space, name suffix, km/h→kt,
  unknown unit, revisions, ended), `TestNhcParsing` (all three products,
  longer track line chosen, lead time and wind, CDT→UTC, unknown zone, issue
  time on every frame, DTD refusal, no products, no position, revisions),
  `TestCycloneLanguage` (provenance, labels, NHC outranks a newer GDACS report).
- `tests/test_api.py`: `TestCycloneIngest` through the real pipeline (official
  event, map feed fields and label, geometry served with cyclone style class,
  newer advisory replaces rather than stacks, fusion in both arrival orders,
  different name stays separate, unnamed report must be close, no alerts).
- `tests/nhc_samples.py` builds KMZ payloads shaped from the live feed.
- Live check (2026-10-09): the real adapter against `CurrentStorms.json` ingested
  3 storms (Isaias, Rachel, Simon) with cone, track, forecast points and wind
  radii; an immediate second poll fetched nothing.
- Full suite: 126 passed. Frontend: `tsc -b` clean.

**Not verified**: the map layers and marker were not viewed in a browser. The
pinwheel was checked only as a rasterised image at 96, 24 and 12 px.

## Known limitations

- NHC-only storms never receive an explicit end; they age out.
- Forecast wind radii (per forecast hour) are not drawn: the KMZ has no times and
  the mapping from placemark to hour is ambiguous.
- Watches and warnings (coastline segments), the past track and storm surge
  products are not shown.
- No link to the official advisory page, although the adapter records its URL.
- West Pacific and Indian Ocean storms (GDACS only) have no track or cone.
- Wind-based category is derived from one number; GDACS and NHC may use different
  averaging periods for sustained wind.
- Noticed, not changed: `policy.compose` also falls back to volcano wording for
  wildfire. As with cyclones, only a watch area created through the API with
  `WILDFIRE` in `hazardTypes` could reach it.
