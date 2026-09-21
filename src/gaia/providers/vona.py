"""USGS VONA (Volcano Observatory Notice for Aviation) status feed.

USGS volcano observatories (AVO, CalVO, CVO, HVO, YVO) issue VONAs to record
changes in a volcano's alert level and aviation color code. The Volcano
Hazards Program republishes the current status of every monitored volcano,
including the most recent notice's synopsis, as plain JSON with no
authentication. US territory only — it has no Indonesian/PVMBG counterpart.

Only volcanoes with an assigned, elevated status (ADVISORY/WATCH/WARNING) are
surfaced as events; NORMAL/GREEN is the resting state for ~150 volcanoes and
would otherwise flood the event list with nothing actionable. A volcano that
settles back to NORMAL simply stops producing new observations, and its event
ages out of the active window like any other feed with no explicit "withdrawn"
signal.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from ..domain.enums import Action, HazardType
from ..domain.geo import valid_coordinates
from .base import PollingAdapter

log = logging.getLogger(__name__)

_ELEVATED_LEVELS = {"ADVISORY", "WATCH", "WARNING"}


def _parse_dt(value: Any) -> datetime | None:
    # e.g. "2019-07-11 23:36:44". The feed carries no timezone marker; USGS
    # publishes these in UTC in practice, so that is what is assumed here.
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


class VonaAdapter(PollingAdapter):
    name = "VONA"
    hazard_type = HazardType.VOLCANO
    parser_version = "vona/1.0.0"
    attribution = "U.S. Geological Survey, Volcano Observatory Notice for Aviation (VONA)"

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        raw = await self.fetch_conditional(
            client,
            self.settings.feed_url,
            params={
                "lat1": self.settings.lat1,
                "long1": self.settings.long1,
                "lat2": self.settings.lat2,
                "long2": self.settings.long2,
            },
        )
        if raw is None:
            return 0
        return await self.ingest(raw)

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        payload = json.loads(raw)
        records: list[dict[str, Any]] = []
        for item in payload:
            record = self._parse_item(item)
            if record:
                records.append(record)
        return records

    def _parse_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        alert_level = str(item.get("alertLevel") or "").upper()
        if alert_level not in _ELEVATED_LEVELS:
            return None

        volcano_code = item.get("volcanoCd") or item.get("vnum")
        if not volcano_code:
            return None

        lon, lat = item.get("long"), item.get("lat")
        if not valid_coordinates(lon, lat):
            lon = lat = None

        issued = _parse_dt(item.get("colorDate")) or _parse_dt(item.get("alertDate"))
        # A notice's own timestamp is the natural revision key: an unchanged
        # status re-polled every cycle is deduplicated by the store, and a real
        # change (or a corrected/re-issued notice) gets a new one.
        if issued is not None:
            revision = item.get("noticeId") or issued.isoformat()
        else:
            revision = alert_level

        return {
            "source_id": str(volcano_code),
            "source_revision": str(revision),
            "hazard_type": HazardType.VOLCANO,
            "action": Action.UPSERT,
            "source_issued_at": issued,
            "observed_at": issued,
            "normalized": {
                "longitude": float(lon) if lon is not None else None,
                "latitude": float(lat) if lat is not None else None,
                "volcano_name": item.get("vName"),
                "place": item.get("region"),
                "alert_level": alert_level,
                "color_code": item.get("colorCode"),
                "notice_id": item.get("noticeId"),
                "synopsis": item.get("noticeSynopsis"),
                "observatory": item.get("obs"),
                # An observatory's own notice is an analyst statement, not a
                # raw automated reading.
                "reviewed": True,
                "attribution": self.attribution,
            },
        }
