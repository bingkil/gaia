"""EMSC SeismicPortal near-real-time WebSocket.

Lowest-latency global programmable feed. Data are documented as CC BY 4.0, so
the attribution travels with every observation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import httpx
from websockets.asyncio.client import connect

from ..db import from_iso, utcnow
from ..domain.enums import Action, HazardType
from ..domain.geo import valid_coordinates
from .base import USER_AGENT, ParseFailure, StreamingAdapter

log = logging.getLogger(__name__)


class EmscAdapter(StreamingAdapter):
    name = "EMSC"
    hazard_type = HazardType.EARTHQUAKE
    parser_version = "emsc/1.0.0"
    attribution = "EMSC-CSEM, CC BY 4.0"

    async def connect_and_consume(self) -> None:
        url = self.settings.websocket_url
        log.info("EMSC connecting to %s", url)
        async with connect(
            url,
            user_agent_header=USER_AGENT,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
        ) as socket:
            await asyncio.to_thread(self.ctx.health.set_state, self.name, "HEALTHY")
            log.info("EMSC stream connected")

            # Close any gap opened while the stream was down before trusting live data.
            async with httpx.AsyncClient(
                timeout=30.0, headers={"User-Agent": USER_AGENT}
            ) as client:
                try:
                    filled = await self.backfill(client)
                    if filled:
                        log.info("EMSC backfilled %d events after reconnect", filled)
                except Exception as exc:
                    log.warning("EMSC backfill failed: %s", exc)

            async for message in socket:
                raw = message.encode("utf-8") if isinstance(message, str) else message
                try:
                    count = await self.ingest(raw, source_hint="ws")
                except ParseFailure as exc:
                    # One malformed frame must not take down the stream.
                    log.warning("%s", exc)
                    await asyncio.to_thread(
                        self.ctx.health.record_error, self.name, str(exc)
                    )
                    continue
                await asyncio.to_thread(self.ctx.health.record_success, self.name, count)

    async def backfill(self, client: httpx.AsyncClient) -> int:
        start = (utcnow() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        response = await client.get(
            self.settings.backfill_url,
            params={"limit": 200, "format": "json", "start": start},
        )
        response.raise_for_status()
        return await self.ingest(response.content, source_hint="backfill")

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        payload = json.loads(raw)

        # The socket sends one action-wrapped feature; FDSN backfill sends a collection.
        if isinstance(payload, dict) and "action" in payload:
            action = str(payload.get("action", "")).lower()
            features = [payload.get("data") or {}]
        else:
            action = "update"
            features = payload.get("features", []) if isinstance(payload, dict) else []

        records: list[dict[str, Any]] = []
        for feature in features:
            record = self._parse_feature(feature, action)
            if record:
                records.append(record)
        return records

    def _parse_feature(self, feature: dict[str, Any], action: str) -> dict[str, Any] | None:
        props = feature.get("properties") or {}
        unid = props.get("unid") or props.get("source_id") or feature.get("id")
        if not unid:
            return None

        lon, lat = props.get("lon"), props.get("lat")
        if lon is None or lat is None:
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]

        warnings: list[str] = []
        if not valid_coordinates(lon, lat):
            # Reject the record but never tear down the stream over one bad message.
            log.warning("EMSC rejected %s: invalid coordinates %s,%s", unid, lon, lat)
            return None

        origin_time = from_iso(props.get("time"))
        if origin_time is None:
            warnings.append("MISSING_ORIGIN_TIME")
        elif origin_time > utcnow() + timedelta(minutes=5):
            log.warning("EMSC rejected %s: origin time in the future", unid)
            return None

        last_update = props.get("lastupdate") or props.get("time") or "1"
        magnitude = _as_float(props.get("mag"))
        depth = _as_float(props.get("depth"))
        if depth is not None and depth < 0:
            depth = abs(depth)
            warnings.append("NEGATIVE_DEPTH_NORMALISED")

        return {
            "source_id": str(unid),
            "source_revision": str(last_update),
            "hazard_type": HazardType.EARTHQUAKE,
            "action": Action.DELETE if action == "delete" else Action.UPSERT,
            "source_issued_at": from_iso(props.get("lastupdate")),
            "observed_at": origin_time,
            "warnings": warnings,
            "normalized": {
                "longitude": float(lon),
                "latitude": float(lat),
                "depth_km": depth,
                "magnitude": magnitude,
                "magnitude_type": props.get("magtype"),
                "place": props.get("flynn_region"),
                "event_type": props.get("evtype"),
                "author": props.get("auth"),
                "source_catalog": props.get("source_catalog"),
                "attribution": self.attribution,
            },
        }


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
