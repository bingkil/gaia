"""International SIGMET feed — an automated source of volcanic ash advisories.

aviationweather.gov republishes every FIR's international SIGMET as JSON,
already carrying a parsed polygon. A record with ``hazard == "VA"`` is the
Meteorological Watch Office's aviation warning for an eruption, derived from
(but not identical to) the VAAC's own bulletin: it has one current extent and,
unlike a VAA, no fixed +6/+12/+18 hour forecast schedule, so only an observed
frame is emitted here. Pasting the full VAAC bulletin via the manual endpoint
remains the way to get forecast frames.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx

from ..db import from_iso
from ..domain.enums import Action, HazardType
from .base import PollingAdapter
from .vaac import flight_level_to_metres, parse_coordinate, parse_levels, parse_movement

log = logging.getLogger(__name__)

_PSN_RE = re.compile(r"PSN\s+([NS])\s*(\d{2,6})\s+([EW])\s*(\d{3,7})", re.IGNORECASE)


def _epoch_to_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _polygon_from_coords(coords: list[dict[str, Any]]) -> dict[str, Any] | None:
    ring: list[list[float]] = []
    for point in coords:
        lon, lat = point.get("lon"), point.get("lat")
        if lon is None or lat is None:
            continue
        ring.append([float(lon), float(lat)])
    if len(ring) < 3:
        return None
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


class IsigmetAdapter(PollingAdapter):
    name = "ISIGMET"
    hazard_type = HazardType.ASH
    parser_version = "isigmet/1.0.0"
    attribution = "NOAA Aviation Weather Center, international SIGMET"

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        raw = await self.fetch_conditional(
            client, self.settings.feed_url, params={"format": "json"}
        )
        if raw is None:
            return 0
        return await self.ingest(raw)

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        payload = json.loads(raw)
        records: list[dict[str, Any]] = []
        for item in payload:
            if item.get("hazard") != "VA" or item.get("geom") != "AREA":
                continue
            record = self._parse_item(item)
            if record:
                records.append(record)
        return records

    def _parse_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        geometry = _polygon_from_coords(item.get("coords") or [])
        if geometry is None:
            return None

        raw_sigmet = item.get("rawSigmet") or ""
        bottom_level, top_level = parse_levels(raw_sigmet)

        longitude = latitude = None
        psn_match = _PSN_RE.search(raw_sigmet)
        if psn_match:
            latitude = parse_coordinate(psn_match.group(1), psn_match.group(2))
            longitude = parse_coordinate(psn_match.group(3), psn_match.group(4))

        valid_from = _epoch_to_utc(item.get("validTimeFrom"))
        issue_time = from_iso(item.get("receiptTime")) or valid_from
        if valid_from is None:
            return None

        warnings: list[str] = []
        if longitude is None or latitude is None:
            warnings.append("MISSING_VOLCANO_POSITION")

        advisory_number = item.get("seriesId") or valid_from.strftime("%Y%m%d%H%M")
        source_id = f"{item.get('icaoId')}_{item.get('firId')}_{advisory_number}"

        return {
            "source_id": source_id,
            "source_revision": item.get("receiptTime") or "1",
            "hazard_type": HazardType.ASH,
            "action": Action.UPSERT,
            "source_issued_at": issue_time,
            "observed_at": valid_from,
            "normalized": {
                "kind": "ASH_ADVISORY",
                "vaac": item.get("firId") or item.get("icaoId"),
                "advisory_number": str(advisory_number),
                "volcano_name": item.get("qualifier"),
                "longitude": longitude,
                "latitude": latitude,
                "area": item.get("firName"),
                "issue_time": issue_time,
                "observation_time": valid_from,
                "status": "ACTIVE",
                "bottom_flight_level": bottom_level,
                "top_flight_level": top_level,
                "bottom_metres": flight_level_to_metres(bottom_level),
                "top_metres": flight_level_to_metres(top_level),
                "movement": parse_movement(raw_sigmet),
                "frames": [
                    {
                        "kind": "OBSERVED",
                        "lead_hours": 0.0,
                        "valid_time": valid_from,
                        "geometry": geometry,
                        "bottom_flight_level": bottom_level,
                        "top_flight_level": top_level,
                    }
                ],
                "raw_text": raw_sigmet,
                "parser_version": self.parser_version,
                "warnings": warnings,
            },
            "warnings": warnings,
        }
