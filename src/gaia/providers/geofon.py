"""GEOFON FDSN event service.

Requests the FDSN ``text`` format rather than JSON: the pipe-delimited columns
are fixed by the FDSN specification, so the parser does not have to guess at
implementation-specific JSON key names.

GEOFON documents ``updatedafter`` as unsupported, so revisions are picked up by
re-requesting a moving window and comparing content.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any

import httpx

from ..db import from_iso, utcnow
from ..domain.enums import Action, HazardType
from ..domain.geo import valid_coordinates
from .base import PollingAdapter

# #EventID|Time|Latitude|Longitude|Depth/km|Author|Catalog|Contributor|
# ContributorID|MagType|Magnitude|MagAuthor|EventLocationName
_COLUMNS = 13


class GeofonAdapter(PollingAdapter):
    name = "GEOFON"
    hazard_type = HazardType.EARTHQUAKE
    parser_version = "geofon/1.0.0"
    attribution = "GEOFON / GFZ Potsdam"
    raw_extension = "txt"

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        start = utcnow() - timedelta(minutes=self.settings.lookback_minutes)
        response = await client.get(
            self.settings.base_url,
            params={
                "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
                "format": "text",
                "limit": 200,
                "orderby": "time",
            },
        )
        # An empty catalogue window is a normal 204/404 for FDSN services.
        if response.status_code in (204, 404):
            return 0
        response.raise_for_status()
        return await self.ingest(response.content, source_hint="window")

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        text = raw.decode("utf-8", errors="replace")
        records: list[dict[str, Any]] = []

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < _COLUMNS:
                continue

            event_id, time_str, lat_str, lon_str, depth_str = parts[:5]
            magtype, magnitude_str = parts[9], parts[10]
            place = parts[12]

            lon, lat = _as_float(lon_str), _as_float(lat_str)
            if not event_id or not valid_coordinates(lon, lat):
                continue

            origin_time = from_iso(time_str)
            if origin_time is None:
                continue

            # No revision counter is exposed, so hash the row: any change to the
            # solution produces a new revision, an identical row is deduplicated.
            revision = hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]

            records.append(
                {
                    "source_id": event_id,
                    "source_revision": revision,
                    "hazard_type": HazardType.EARTHQUAKE,
                    "action": Action.UPSERT,
                    "source_issued_at": None,
                    "observed_at": origin_time,
                    "warnings": [],
                    "normalized": {
                        "longitude": lon,
                        "latitude": lat,
                        "depth_km": _as_float(depth_str),
                        "magnitude": _as_float(magnitude_str),
                        "magnitude_type": magtype or None,
                        "place": place or None,
                        "author": parts[5] or None,
                        "catalog": parts[6] or None,
                        "attribution": self.attribution,
                    },
                }
            )
        return records


def _as_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
