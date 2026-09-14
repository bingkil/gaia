<p align="center">
  <img src="docs/gaia-logo.png" alt="GAIA logo" width="120">
</p>

<h1 align="center">GAIA</h1>
<p align="center"><strong>Geohazard Awareness, Impact &amp; Alerting</strong></p>

<p align="center">
  <a href="LICENSE.md"><img alt="License: PolyForm Noncommercial 1.0.0" src="https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg"></a>
</p>

A local-first situational-awareness platform for earthquakes, volcanic eruptions,
volcanic ash, and satellite-detected wildfires. Everything runs on one machine:
ingestion, fusion, impact modelling, the map, and alerts. No cloud services, no
account, no data leaving the device except to query the public feeds listed below.

## What it is not

GAIA is **not** an earthquake early warning system. It ingests global catalogue feeds,
which provide rapid *detection*, not authoritative warning. The term *Early Warning* is
reserved in code for alerts originating from an approved regional EEW authority, and no
catalogue-derived event can be promoted into that class at runtime.

Arrival times shown by GAIA are modelled estimates. They are labelled as such, and they
are not a substitute for instructions from local authorities.

A satellite hotspot cluster is not a declared wildfire emergency either — it is
automated detection, labelled and coloured as preliminary until a fire/emergency
authority's own feed corroborates it.

## Features

- **Live map** of earthquakes, volcanic activity, volcanic ash advisories, and wildfire
  hotspot clusters, updated over a websocket as new observations arrive.
- **Provenance-first design**: every marker, tooltip, and list row states whether it
  came from an official authority or an automated signal, and never asserts a hazard
  the event is not.
- **Colour-blind-safe severity ramp with redundant shapes** — circle (earthquake),
  notched cone (volcano), diamond (ash), flame (wildfire) — so severity and hazard type
  are each readable on their own.
- **Three basemaps**: a dark tactical style, Esri aerial imagery, and near-real-time
  NASA satellite imagery (see below).
- **Watch areas**: a named radius around a point (e.g. your location) with its own
  minimum-magnitude threshold, so quiet-hours or local alerting can differ by place.
- **Manual VAA ingest**: paste a Volcanic Ash Advisory bulletin to parse it into ash
  geometry frames without waiting on the automated feed.
- **Selectable time zone and rolling time ranges** for reviewing what happened over the
  last hours or days, independent of the live view.
- **Replay from stored raw payloads**: every provider response is kept as received, so a
  parsing fix can be re-applied without re-fetching anything.

### Real-time satellite basemap

The "Live" basemap toggle draws daily VIIRS NOAA-21 true-colour imagery from
[NASA GIBS](https://www.earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs),
the same satellite GAIA's own fire detections come from, so a smoke plume appears
under its own fire markers. It is daily-composite imagery (not live video), typically
available within 3.5 hours of the overpass, capped at zoom level 9 by NASA's tile
service.

## Data sources

| Source | Role | Licence note |
|---|---|---|
| EMSC SeismicPortal | Fast global earthquake stream | Data documented as CC BY 4.0 |
| USGS | Independent earthquake confirmation | Review USGS terms before redistribution |
| GEOFON / GFZ Potsdam | Independent earthquake catalogue | Review GEOFON terms |
| GDACS | Volcanic events and context | Attribution required; information is indicative |
| NASA FIRMS | Satellite thermal anomalies (wildfire detection) | Free map key required |
| NASA GIBS | Satellite true-colour imagery (real-time basemap) | Public, no key required; attribution required |

A free data feed does not grant the right to rebrand its message as an official warning.

## Download

Prebuilt, double-clickable releases for Windows and macOS are produced with the
scripts in [`scripts/`](scripts/) — see [Building a release](#building-a-release)
below. No Python or Node install is required to run a built release.

## Requirements

For running from source:

- Python 3.12+
- Node.js 20+ (to build the map interface)

## Quick start

```powershell
uv venv
uv pip install -e ".[dev]"
uv run gaia init          # create the database and seed the volcano catalogue
uv run gaia serve         # start ingestion + API on http://127.0.0.1:8000
```

Build the interface once, then reload the page:

```powershell
cd web
npm install
npm run build
```

For frontend development with hot reload, run `npm run dev` alongside `gaia serve`.

## Configuration

Settings are environment variables prefixed with `GAIA_`, nested with `__`. Put them in
a `.env` file in the repository root.

```ini
GAIA_PORT=8000
GAIA_PROVIDERS__FIRMS__ENABLED=true
GAIA_PROVIDERS__FIRMS__MAP_KEY=your_firms_map_key
GAIA_ALERTS__MIN_MAGNITUDE=4.5
```

Every provider URL and polling interval is configurable without a code change. The
FIRMS map key can also be entered from the in-app Settings panel, where it is written
to `data/secrets.json` rather than the environment.

## Local data

All state lives under a data directory, git-ignored when running from source:

- `data/gaia.sqlite3` — observations, canonical events, revisions, alerts
- `data/raw/` — immutable provider payloads, written before parsing
- `data/secrets.json` — locally entered credentials (e.g. the FIRMS map key)

Because raw payloads are retained, a parser fix can be replayed against stored bytes
without refetching anything from a provider.

A built release (see below) is not run from a source checkout, so it stores this
directory per-user instead: `%LOCALAPPDATA%\GAIA` on Windows, `~/Library/Application
Support/GAIA` on macOS.

## Commands

| Command | Purpose |
|---|---|
| `gaia init` | Create the database and seed the volcano catalogue |
| `gaia serve` | Run ingestion and the API |
| `gaia replay` | Rebuild canonical events from stored raw payloads |
| `gaia status` | Show provider health and record counts |

## Building a release

Requires Python 3.12+ and Node.js 20+ on the machine doing the build — PyInstaller does
not cross-compile, so a Windows build must be produced on Windows and a macOS build on
macOS.

```powershell
# Windows -> dist/GAIA.exe
./scripts/build-release-windows.ps1
```

```bash
# macOS -> dist/GAIA.app
./scripts/build-release-macos.sh
```

Each script builds the frontend, installs the `release` extra (PyInstaller), and
packages the backend and the built UI into one artifact. Double-clicking it starts the
server and opens the app in your browser; closing the window stops it.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the process topology, module map,
and data flow: one process instead of four, SQLite instead of PostgreSQL/PostGIS, an
in-process bus instead of NATS, and the filesystem instead of object storage.

## Legal

- [Terms of Service](TERMS_OF_SERVICE.md)
- [Privacy Policy](PRIVACY.md)
- [License](LICENSE.md) — PolyForm Noncommercial 1.0.0. Free to use, modify, and share
  for noncommercial purposes; commercial use requires a separate agreement.

Copyright © 2026 [bingkil.com](https://bingkil.com). All rights reserved except as
granted under the license above.

