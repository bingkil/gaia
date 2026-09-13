"""NASA FIRMS thermal anomalies.

An automated signal only. A thermal pixel is never sufficient evidence of an
eruption: wildfires, industrial heat, gas flares, and geolocation error all
produce the same signature. Classification lives in the engine; this adapter
only reports detections and their distance to a catalogued volcano.

Requires a free FIRMS map key in ``GAIA_PROVIDERS__FIRMS__MAP_KEY``.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ..domain.enums import Action, HazardType
from ..domain.geo import valid_coordinates
from .base import PollingAdapter

log = logging.getLogger(__name__)

# Bounding boxes over the principal volcanic arcs. Querying these rather than
# the whole world keeps request volume within the free-tier limits.
VOLCANIC_REGIONS: list[tuple[str, tuple[float, float, float, float]]] = [
    ("indonesia_philippines", (94.0, -11.0, 141.0, 21.0)),
    ("japan_kuril_kamchatka", (128.0, 29.0, 165.0, 62.0)),
    ("alaska_aleutians", (-180.0, 50.0, -129.0, 66.0)),
    ("central_america", (-118.0, 8.0, -82.0, 23.0)),
    ("andes", (-80.0, -46.0, -62.0, 8.0)),
    ("mediterranean", (10.0, 34.0, 30.0, 46.0)),
    ("iceland", (-25.0, 62.0, -12.0, 67.0)),
    ("east_africa", (28.0, -13.0, 46.0, 16.0)),
    ("melanesia", (140.0, -25.0, 180.0, -1.0)),
    ("tonga_kermadec", (-180.0, -26.0, -170.0, -12.0)),
]


class FirmsAdapter(PollingAdapter):
    name = "FIRMS"
    hazard_type = HazardType.VOLCANO
    parser_version = "firms/1.0.0"
    attribution = "NASA FIRMS"
    raw_extension = "csv"

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        if not self.settings.map_key:
            raise RuntimeError("FIRMS map key not configured")

        total = 0
        for product in self.settings.products:
            for region_name, bbox in VOLCANIC_REGIONS:
                area = ",".join(str(v) for v in bbox)
                url = (
                    f"{self.settings.base_url}/{self.settings.map_key}/"
                    f"{product}/{area}/{self.settings.day_range}"
                )
                response = await client.get(url)
                if response.status_code == 401:
                    raise RuntimeError("FIRMS map key rejected")
                response.raise_for_status()

                body = response.content
                # FIRMS answers over-quota and errors with a plain-text body.
                if b"," not in body.split(b"\n", 1)[0]:
                    log.warning("FIRMS unexpected response: %s", body[:120])
                    continue
                total += await self.ingest(body, source_hint=f"{product}_{region_name}")
        return total

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        text = raw.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        records: list[dict[str, Any]] = []

        for row in reader:
            lat = _as_float(row.get("latitude"))
            lon = _as_float(row.get("longitude"))
            if not valid_coordinates(lon, lat):
                continue

            acquired = _acquisition_time(row.get("acq_date"), row.get("acq_time"))
            if acquired is None:
                continue

            instrument = row.get("instrument") or "UNKNOWN"
            satellite = row.get("satellite") or "UNKNOWN"
            # No stable per-detection identifier exists, so position plus
            # acquisition time is the natural key.
            source_id = f"{instrument}_{satellite}_{lat:.4f}_{lon:.4f}_{acquired:%Y%m%dT%H%M}"

            records.append(
                {
                    "source_id": source_id,
                    "source_revision": "1",
                    "hazard_type": HazardType.VOLCANO,
                    "action": Action.UPSERT,
                    "source_issued_at": None,
                    "observed_at": acquired,
                    "warnings": [],
                    "normalized": {
                        "longitude": lon,
                        "latitude": lat,
                        "kind": "THERMAL_ANOMALY",
                        "instrument": instrument,
                        "satellite": satellite,
                        "confidence_category": row.get("confidence"),
                        "frp": _as_float(row.get("frp")),
                        "brightness": _as_float(row.get("bright_ti4") or row.get("brightness")),
                        "daynight": row.get("daynight"),
                        "scan": _as_float(row.get("scan")),
                        "track": _as_float(row.get("track")),
                        "attribution": self.attribution,
                    },
                }
            )
        return records


def _acquisition_time(date_str: str | None, time_str: str | None) -> datetime | None:
    if not date_str:
        return None
    padded = (time_str or "0000").zfill(4)
    try:
        return datetime.strptime(f"{date_str} {padded}", "%Y-%m-%d %H%M").replace(tzinfo=UTC)
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
