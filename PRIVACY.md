# Privacy Policy

**GAIA — Geohazard Awareness, Impact & Alerting**
Copyright © 2026 bingkil.com

GAIA is local-first software. This policy describes what actually happens when you run
it, because there is no bingkil.com server collecting anything to describe otherwise.

## Summary

- No account, sign-up, or login.
- No analytics, telemetry, crash reporting, or usage tracking of any kind is built into
  GAIA. (There is none in the source — this isn't a promise about a toggle, there is
  simply no such code.)
- All application data stays on your device.

## What is stored, and where

Everything GAIA stores lives in a local data directory on your own machine:

- `gaia.sqlite3` — the hazard events, observations, and alerts GAIA has ingested.
- `raw/` — the unmodified provider responses those were parsed from.
- `secrets.json` — credentials you enter yourself, such as a NASA FIRMS map key.

Nothing in this directory is transmitted to bingkil.com. bingkil.com does not operate
any server that GAIA talks to.

## Location

If you use the "use my location" feature, your device's geolocation (obtained through
your browser, which will ask your browser's own permission) is stored only in your
browser's local storage on your device and used to create "watch areas" in your local
database. It is not sent anywhere except to the GAIA server running on your own
machine.

## Outbound network requests

GAIA's backend, running on your machine, makes outbound HTTP(S) requests directly to
the third-party data providers listed in [README.md](README.md) (EMSC, USGS,
GEOFON/GFZ Potsdam, GDACS, NASA FIRMS, NASA GIBS) to fetch public hazard data. These
requests originate from your device and are visible to those providers the same way
any web request is — they can see the request and your IP address, as with any HTTP
client. bingkil.com does not receive, log, or have access to these requests; they never
pass through any bingkil.com infrastructure. Each provider's own privacy practices
govern what they do with requests they receive; GAIA does not control this.

## Changes

If GAIA's data-handling changes in a future version, this document will be updated
alongside it.

## Contact

Questions about this policy can be directed through [bingkil.com](https://bingkil.com).
