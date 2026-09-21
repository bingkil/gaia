# Webcams

## Purpose

Webcams give people looking at a hazard event a way to see the area with
their own eyes. Each webcam is matched to nearby events by hazard type and
distance (`WebcamSettings.match_radius_km`, default 300 km) and shown on the
event detail view alongside official hazard maps.

## Data model

`Webcam` (`src/gaia/domain/models.py`) has three fallback tiers, tried in
this order by the client (`web/src/components/WebcamPlayer.tsx`):

1. `stream_url` — live video.
2. `image_url` — a periodically refreshed still image.
3. `thumbnail_url` — a static image / pure link-out.

`source_url` and `attribution` are independent of the tier used and are
always rendered as a "Source" link, so a webcam with no `stream_url`,
`image_url`, or `thumbnail_url` at all is a valid "link out only" entry —
useful for cameras whose live image can't be hotlinked (see below).

Webcams are otherwise a fully user-managed CRUD resource
(`WebcamRepo`, `POST/PUT/DELETE /v1/webcams`, `WebcamAdminPanel.tsx`).

## Right-rail panel (`WebcamAdminPanel.tsx`)

- Opens as a wide right rail (`.app.right-wide`, `min(640px, 44vw)`) via the
  "Webcams" toolbar toggle, same mechanism as other right-rail panels.
- Each row is clickable (`.webcam-row.clickable`) and pans/centres the map
  on that webcam's location via the `onFocus` prop, without affecting the
  row's action buttons (all four stop propagation).
- A "Source ↗" link is shown inline in the row when `source_url` is set,
  opening the source page in a new tab.
- The 👁 button opens a modal (`createPortal` to `document.body`) showing
  the live `WebcamPlayer` for that webcam — the same visual/interaction
  pattern as the KRB hazard-map modal in `EventDetail.tsx` (`.modal-scrim`
  click-to-close, `Escape` to close, `role="dialog"`/`aria-modal`). Only
  one webcam preview can be open at a time (`previewWebcam` state).

## Seeded catalogue

Unlike volcanoes (`providers/catalogue.py`) and KRB hazard maps
(`providers/krb_maps.py`), webcams originally had no seed data at all —
every entry had to be added by hand. `providers/webcams_seed.py` now
provides a small starter catalogue of real, verified public volcano
webcams, inserted once by `Runtime.seed_webcams()` (called from the app's
`lifespan()` alongside the existing volcano seeding).

**Seeding is gated on the webcam table being empty**, exactly like the
volcano catalogue: it runs only if `WebcamRepo.count() == 0`. This means an
operator who deletes a seeded webcam does not have it silently reappear on
the next restart. It also means the seed only ever applies to a fresh
install — it will not "top up" an existing install with new entries.

### Indonesia — MAGMA Indonesia (PVMBG), link-out only

MAGMA Indonesia's CCTV pages (`https://magma.esdm.go.id/v1/gunung-api/cctv`)
require a session/CSRF token to load the actual camera image — the "View"
link on each camera is JS-driven with no plain image URL behind it (checked
by fetching individual camera pages and inspecting the rendered DOM; this is
the same limitation already noted in `krb_maps.py` for KRB hazard maps).
So these 11 entries are link-out only: `source_url` points at the volcano's
MAGMA CCTV page, `image_url`/`stream_url` are left unset.

| Volcano | MAGMA code | Cameras |
|---|---|---|
| Bromo | BRO | 5 |
| Dempo | DEM | 2 |
| Dieng | DIE | 2 |
| Guntur | GUN | 1 |
| Ibu | IBU | 4 |
| Ijen | IJE | 3 |
| Kerinci | KER | 1 |
| Anak Krakatau | KRA | 6 |
| Papandayan | PAP | 1 |
| Sinabung | SIN | 4 |
| Semeru | SMR | 5 |

Attribution: PVMBG (Pusat Vulkanologi dan Mitigasi Bencana Geologi), Badan
Geologi, Kementerian ESDM.

### Hawaii — USGS Hawaiian Volcano Observatory (HVO), direct image

HVO publishes plain, unauthenticated JPEG stills
(`https://volcanoes.usgs.gov/cams/{code}/images/M.jpg`), confirmed
reachable via HTTP HEAD requests. One flagship camera is seeded per
volcano to avoid clutter:

| Volcano | Camera | View |
|---|---|---|
| Kilauea | K2cam | Kīlauea Caldera from Uēkahuna bluff |
| Mauna Loa | MOcam | Mokuʻāweoweo Caldera from South Rim |

`source_url` points at the volcano's official USGS webcams page
(e.g. `https://www.usgs.gov/volcanoes/kilauea/webcams`). Attribution: U.S.
Geological Survey, Hawaiian Volcano Observatory (HVO).

## Other sources considered, not yet integrated

- **Alaska Volcano Observatory (AVO)** — no working public webcam source
  found. `volcanoes.usgs.gov/observatories/avo/cams/` 404s,
  `usgs.gov/observatories/avo/multimedia/webcams` returns HTTP 403, and
  `avo.alaska.edu`'s own navigation has no webcam link.
- **Cascades Volcano Observatory (CVO)** — same `volcanoes.usgs.gov`
  pattern as HVO/AVO also 404s.
- **Iceland (IMO), Italy/Etna (INGV), Philippines (PHIVOLCS), Japan (JMA)**
  — named as candidate "other countries" but not yet researched/verified.

Adding any of these should follow the same rule used above: verify with a
real HTTP request (not just a documentation page) whether the camera image
is directly hotlinkable before deciding between an `image_url` entry and a
link-out-only entry.

## Tests

`tests/test_api.py::TestWebcams`:
- `test_catalogue_is_seeded_on_startup` — 13 webcams exist on a fresh
  database; spot-checks one link-out (Bromo) and one direct-image
  (Kilauea) entry.
- `test_seeding_does_not_resurrect_a_deleted_webcam` — deleting a seeded
  webcam and re-running `seed_webcams()` does not bring it back.
- Existing CRUD/nearby-matching tests were updated to diff against the
  seeded baseline instead of assuming an empty table.
