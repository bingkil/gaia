"""USGS earthquake GeoJSON feed.

Independent confirmation and enrichment. The summary feeds are documented as
updated every minute, so conditional GET keeps the request cost near zero.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from ..domain.enums import Action, HazardType
from ..domain.geo import valid_coordinates
from .base import PollingAdapter


def _epoch_ms(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
    except (TypeError, ValueError, OSError):
        return None


class UsgsAdapter(PollingAdapter):
    name = "USGS"
    hazard_type = HazardType.EARTHQUAKE
    parser_version = "usgs/1.0.0"
    attribution = "U.S. Geological Survey"

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        raw = await self.fetch_conditional(client, self.settings.feed_url)
        if raw is None:
            return 0
        return await self.ingest(raw, source_hint="summary")

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        payload = json.loads(raw)
        records: list[dict[str, Any]] = []

        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            event_id = feature.get("id")
            if not event_id or len(coords) < 2:
                continue

            lon, lat = coords[0], coords[1]
            if not valid_coordinates(lon, lat):
                continue
            depth = coords[2] if len(coords) > 2 else None

            warnings: list[str] = []
            if depth is not None and depth < 0:
                # Shallow events above sea level are reported as negative depth.
                warnings.append("ABOVE_SEA_LEVEL_DEPTH")

            # 'reviewed' status means an analyst has confirmed the solution.
            status = str(props.get("status") or "").lower()

            records.append(
                {
                    "source_id": str(event_id),
                    "source_revision": str(props.get("updated") or props.get("time") or "1"),
                    "hazard_type": HazardType.EARTHQUAKE,
                    "action": Action.UPSERT,
                    "source_issued_at": _epoch_ms(props.get("updated")),
                    "observed_at": _epoch_ms(props.get("time")),
                    "warnings": warnings,
                    "normalized": {
                        "longitude": float(lon),
                        "latitude": float(lat),
                        "depth_km": float(depth) if depth is not None else None,
                        "magnitude": props.get("mag"),
                        "magnitude_type": props.get("magType"),
                        "place": props.get("place"),
                        "event_type": props.get("type"),
                        "status": status,
                        "reviewed": status == "reviewed",
                        "tsunami": bool(props.get("tsunami")),
                        "felt_reports": props.get("felt"),
                        "cdi": props.get("cdi"),
                        "mmi": props.get("mmi"),
                        "alert_level": props.get("alert"),
                        "detail_url": props.get("detail"),
                        "attribution": self.attribution,
                    },
                }
            )
        return records
