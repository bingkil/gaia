"""GDACS volcanic and wildfire event feed.

GDACS states that its volcano information derives largely from VAAs and
Smithsonian weekly reports and is indicative only, so events from here are
never promoted above an official-notice provenance and never treated as
sole grounds for a life-safety decision. The same caution applies to its
wildfire list, which is modelled burnt-area reporting rather than a ground
observation of a fire front.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from ..db import from_iso, utcnow
from ..domain.enums import Action, HazardType
from ..domain.geo import valid_coordinates
from .base import PollingAdapter

log = logging.getLogger(__name__)

_ALERT_LEVELS = {"green": "GREEN", "orange": "ORANGE", "red": "RED"}

_HAZARD_BY_EVENT_TYPE = {"VO": HazardType.VOLCANO, "WF": HazardType.WILDFIRE}


class GdacsAdapter(PollingAdapter):
    name = "GDACS"
    hazard_type = HazardType.VOLCANO
    parser_version = "gdacs/1.0.0"
    attribution = "Global Disaster Awareness and Coordination System, GDACS"

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        # Date filtering makes this endpoint answer 204, so the current list is
        # fetched whole and deduplicated downstream by source id and revision.
        total = 0
        for event_type in _HAZARD_BY_EVENT_TYPE:
            response = await client.get(
                self.settings.event_list_url, params={"eventlist": event_type}
            )
            response.raise_for_status()

            if response.status_code == 204 or not response.content.strip():
                continue
            total += await self.ingest(response.content, source_hint=f"eventlist_{event_type}")
        return total

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        payload = json.loads(raw)
        features = payload.get("features") if isinstance(payload, dict) else None
        if features is None:
            features = payload if isinstance(payload, list) else []

        records: list[dict[str, Any]] = []
        for feature in features:
            record = self._parse_feature(feature)
            if record:
                records.append(record)
        return records

    def _parse_feature(self, feature: dict[str, Any]) -> dict[str, Any] | None:
        props = feature.get("properties") or feature
        event_id = props.get("eventid") or props.get("eventId") or feature.get("id")
        if not event_id:
            return None

        hazard = _HAZARD_BY_EVENT_TYPE.get(str(props.get("eventtype") or "").upper())
        if hazard is None:
            return None

        coords = (feature.get("geometry") or {}).get("coordinates") or []
        lon = props.get("longitude") if props.get("longitude") is not None else None
        lat = props.get("latitude") if props.get("latitude") is not None else None
        if (lon is None or lat is None) and len(coords) >= 2:
            lon, lat = coords[0], coords[1]
        if not valid_coordinates(_as_float(lon), _as_float(lat)):
            return None

        episode = props.get("episodeid") or props.get("episodeId") or ""
        from_date = from_iso(_clean_time(props.get("fromdate")))
        to_date = from_iso(_clean_time(props.get("todate")))
        alert_level = _ALERT_LEVELS.get(str(props.get("alertlevel") or "").lower())
        is_current = str(props.get("iscurrent", "")).lower() == "true"

        severity = props.get("severitydata") or {}
        country = props.get("country")
        # "name" is a headline such as "Eruption Krakatau"; "eventname" is the
        # volcano itself, which is what the catalogue is keyed on.
        name = props.get("eventname") or props.get("name") or "Unnamed volcano"

        if hazard is HazardType.WILDFIRE:
            # GDACS numbers each event type in its own sequence, so a bare id
            # could fuse a fire into a volcano. Only the newer type is
            # namespaced, which leaves existing volcano keys untouched.
            source_id = f"WF_{event_id}"
            # A fire has no catalogue identity; naming one would let the
            # volcano resolver match it by name further down the pipeline.
            volcano_name = None
            place = country or props.get("name") or "Wildfire"
            # GDACS keeps burnt-out fires on the list and restamps them on
            # every poll, so without this they would look perpetually current.
            # Volcanoes are deliberately left standing: an alert level holds
            # until the agency withdraws it.
            ended = not is_current and to_date is not None and to_date < utcnow()
        else:
            source_id = f"{event_id}"
            volcano_name = name
            place = country or name
            ended = False

        return {
            "source_id": source_id,
            "source_revision": str(props.get("episodealertscore") or episode or "1"),
            "hazard_type": hazard,
            "action": Action.UPSERT,
            "source_issued_at": from_iso(_clean_time(props.get("datemodified"))),
            "observed_at": from_date,
            "warnings": [],
            "normalized": {
                "longitude": float(lon),
                "latitude": float(lat),
                "depth_km": None,
                "magnitude": None,
                "volcano_name": volcano_name,
                "country": country,
                "alert_level": alert_level,
                "event_name": props.get("eventname"),
                "episode_id": str(episode) if episode else None,
                "from_date": from_date.isoformat() if from_date else None,
                "to_date": to_date.isoformat() if to_date else None,
                "severity_text": severity.get("severitytext"),
                "is_current": is_current,
                "ended": ended,
                "place": place,
                "report_url": props.get("url", {}).get("report")
                if isinstance(props.get("url"), dict)
                else None,
                "attribution": self.attribution,
            },
        }


def _clean_time(value: Any) -> str | None:
    """GDACS emits several timestamp shapes; normalise the common ones."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    # e.g. "2026-09-13T19:41:17" or "2026-09-13 19:41:17"
    return text.replace(" ", "T")


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
