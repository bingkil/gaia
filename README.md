# GAIA

**Geohazard Awareness, Impact & Alerting**

A local-first situational-awareness platform for earthquakes, volcanic eruptions, and
volcanic ash. Everything runs on one machine: ingestion, fusion, impact modelling, the
map, and alerts. No cloud services, no account, no data leaving the device.

## What it is not

GAIA is **not** an earthquake early warning system. It ingests global catalogue feeds,
which provide rapid *detection*, not authoritative warning. The term *Early Warning* is
reserved in code for alerts originating from an approved regional EEW authority, and no
catalogue-derived event can be promoted into that class at runtime.

Arrival times shown by GAIA are modelled estimates. They are labelled as such, and they
are not a substitute for instructions from local authorities.

## Data sources

| Source | Role | Licence note |
|---|---|---|
| EMSC SeismicPortal | Fast global earthquake stream | Data documented as CC BY 4.0 |
| USGS | Independent earthquake confirmation | Review USGS terms before redistribution |
| GEOFON / GFZ Potsdam | Independent earthquake catalogue | Review GEOFON terms |
| GDACS | Volcanic events and context | Attribution required; information is indicative |
| NASA FIRMS | Satellite thermal anomalies | Free map key required |

A free data feed does not grant the right to rebrand its message as an official warning.

## Requirements

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

Every provider URL and polling interval is configurable without a code change.

## Local data

All state lives under `data/`, which is git-ignored:

- `data/gaia.sqlite3` — observations, canonical events, revisions, alerts
- `data/raw/` — immutable provider payloads, written before parsing

Because raw payloads are retained, a parser fix can be replayed against stored bytes
without refetching anything from a provider.

## Commands

| Command | Purpose |
|---|---|
| `gaia init` | Create the database and seed the volcano catalogue |
| `gaia serve` | Run ingestion and the API |
| `gaia replay` | Rebuild canonical events from stored raw payloads |
| `gaia status` | Show provider health and record counts |

## Architecture

See [docs/geohazard-early-warning-implementation.md](docs/geohazard-early-warning-implementation.md)
for the full specification. This repository implements the local-first reduction of it:
one process instead of four, SQLite instead of PostgreSQL/PostGIS, an in-process bus
instead of NATS, and the filesystem instead of object storage. The domain model, safety
vocabulary, provenance rules, and replay guarantees are unchanged.
