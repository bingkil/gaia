"""NOAA National Hurricane Center active tropical cyclones.

NHC's CurrentStorms.json lists every active Atlantic, East Pacific and Central
Pacific storm with its advisory position and intensity, and links the forecast
products as KMZ files (a zip holding one KML). The forecast track, the cone of
uncertainty and the current wind extents are fetched for each storm and kept
alongside the listing in one stored payload, so the geometry can be replayed
from disk like every other provider response.

These are the agency's own advisories, so an event backed by this feed is an
official notice. The cone is the uncertainty of the *track* only: it is not
the area that will see damaging wind, and the map must never present it as such.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from ..db import from_iso, to_iso
from ..domain.enums import Action, FrameKind, GeometryType, HazardType
from ..domain.geo import valid_coordinates
from .base import PollingAdapter

log = logging.getLogger(__name__)

# The listing names the URLs it wants fetched, so they are held to NHC's own host.
_ALLOWED_PREFIX = "https://www.nhc.noaa.gov/"

# A real product is tens of kilobytes. The caps stop a hostile or broken
# response from exhausting memory, either as a download or once unzipped.
_MAX_DOWNLOAD_BYTES = 2_000_000
_MAX_KML_BYTES = 5_000_000

_BASINS = {"AL": "Atlantic", "EP": "Eastern Pacific", "CP": "Central Pacific"}

# Offsets from UTC, in hours, for the zone abbreviations NHC and CPHC print.
_ZONE_HOURS = {
    "AST": -4, "ADT": -3,
    "EST": -5, "EDT": -4,
    "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6,
    "PST": -8, "PDT": -7,
    "AKST": -9, "AKDT": -8,
    "HST": -10, "HDT": -9,
    "UTC": 0, "GMT": 0,
}  # fmt: skip

_PRODUCTS = {
    "track": "forecastTrack",
    "cone": "trackCone",
    "radii": "initialWindExtent",
}


class NhcAdapter(PollingAdapter):
    name = "NHC"
    hazard_type = HazardType.CYCLONE
    parser_version = "nhc/1.0.0"
    attribution = "NOAA National Hurricane Center"

    def __init__(self, ctx: Any, settings: Any) -> None:
        super().__init__(ctx, settings)
        # A storm is re-fetched only when its advisory moves on. The store
        # deduplicates too, but this saves the three product downloads.
        self._seen: dict[str, str] = {}

    async def poll_once(self, client: httpx.AsyncClient) -> int:
        response = await client.get(self.settings.feed_url)
        response.raise_for_status()
        storms = (json.loads(response.content) or {}).get("activeStorms") or []

        entries: list[dict[str, Any]] = []
        for storm in storms:
            storm_id, revision = storm.get("id"), storm.get("lastUpdate")
            if not storm_id or self._seen.get(storm_id) == revision:
                continue
            files = {}
            for key, field in _PRODUCTS.items():
                data = await self._fetch_product(client, storm.get(field))
                if data is not None:
                    files[key] = base64.b64encode(data).decode("ascii")
            entries.append({"storm": storm, "kmz": files})

        if not entries:
            return 0

        bundle = {"fetchedAt": to_iso(datetime.now(UTC)), "storms": entries}
        count = await self.ingest(json.dumps(bundle).encode("utf-8"))
        for entry in entries:
            self._seen[entry["storm"]["id"]] = entry["storm"].get("lastUpdate")
        return count

    async def _fetch_product(self, client: httpx.AsyncClient, product: Any) -> bytes | None:
        url = product.get("kmzFile") if isinstance(product, dict) else None
        if not url or not url.startswith(_ALLOWED_PREFIX):
            return None
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # A missing product should not lose the storm's position and intensity.
            log.warning("NHC product fetch failed for %s: %s", url, exc)
            return None
        if len(response.content) > _MAX_DOWNLOAD_BYTES:
            log.warning("NHC product %s is %d bytes; skipped", url, len(response.content))
            return None
        return response.content

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        bundle = json.loads(raw)
        records: list[dict[str, Any]] = []
        for entry in bundle.get("storms") or []:
            record = self._parse_storm(entry.get("storm") or {}, entry.get("kmz") or {})
            if record:
                records.append(record)
        return records

    def _parse_storm(self, storm: dict[str, Any], kmz: dict[str, str]) -> dict[str, Any] | None:
        storm_id = storm.get("id")
        lon, lat = storm.get("longitudeNumeric"), storm.get("latitudeNumeric")
        if not storm_id or not valid_coordinates(lon, lat):
            return None

        issued = from_iso(storm.get("lastUpdate"))
        warnings: list[str] = []
        frames = _frames(kmz, issued, warnings)

        public = storm.get("publicAdvisory")
        report_url = public.get("url") if isinstance(public, dict) else None
        storm_id = str(storm_id).upper()

        return {
            "source_id": storm_id,
            "source_revision": str(storm.get("lastUpdate") or "1"),
            "hazard_type": HazardType.CYCLONE,
            "action": Action.UPSERT,
            "source_issued_at": issued,
            "observed_at": issued,
            "warnings": warnings,
            "normalized": {
                "longitude": float(lon),
                "latitude": float(lat),
                "storm_name": storm.get("name"),
                "storm_class": storm.get("classification"),
                "max_wind_kt": _as_float(storm.get("intensity")),
                "place": _BASINS.get(storm_id[:2]),
                # An agency advisory is the analyst's own statement.
                "reviewed": True,
                "report_url": report_url,
                "frames": frames,
                "attribution": self.attribution,
            },
        }


def _frames(
    kmz: dict[str, str], issued: datetime | None, warnings: list[str]
) -> list[dict[str, Any]]:
    issued_iso = to_iso(issued)
    issued_ms = issued.timestamp() * 1000 if issued else None
    frames: list[dict[str, Any]] = []

    def add(kind: GeometryType, frame_kind: FrameKind, geometry: dict[str, Any], **props: Any) -> None:
        valid = props.pop("valid_time", None) or issued_iso
        if valid is None:
            return
        frames.append(
            {
                "geometry_type": kind.value,
                "frame_kind": frame_kind.value,
                "valid_time": valid,
                "lead_hours": props.get("leadHours"),
                "geometry": geometry,
                "properties": {"issuedAtMs": issued_ms, **props},
            }
        )

    for key, extract in (("cone", _cone), ("track", _track), ("radii", _radii)):
        if key not in kmz:
            continue
        try:
            root = _kml_root(base64.b64decode(kmz[key]))
            for item in extract(root):
                add(*item[:3], **item[3])
        except Exception as exc:  # noqa: BLE001 - one bad product must not drop the rest
            warnings.append(f"{key.upper()}_UNREADABLE: {exc}")
    return frames


def _kml_root(data: bytes) -> ET.Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        name = next((n for n in archive.namelist() if n.lower().endswith(".kml")), None)
        if name is None:
            raise ValueError("no KML in archive")
        if archive.getinfo(name).file_size > _MAX_KML_BYTES:
            raise ValueError("KML too large")
        xml = archive.read(name)
    # ElementTree expands entities, so a document that declares any is refused.
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("KML declares a DTD")
    return ET.fromstring(xml)


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _placemarks(root: ET.Element) -> list[ET.Element]:
    return [e for e in root.iter() if _local(e.tag) == "Placemark"]


def _coordinates(element: ET.Element) -> list[list[float]]:
    """KML 'lon,lat,alt' triples to [lon, lat], rounded to roughly 100 m."""
    out: list[list[float]] = []
    for triple in (element.text or "").split():
        parts = triple.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if valid_coordinates(lon, lat):
            out.append([round(lon, 3), round(lat, 3)])
    return out


def _geometry(placemark: ET.Element) -> dict[str, Any] | None:
    for element in placemark.iter():
        kind = _local(element.tag)
        if kind == "Point":
            coords = _first_coordinates(element)
            return {"type": "Point", "coordinates": coords[0]} if coords else None
        if kind == "LineString":
            coords = _first_coordinates(element)
            return {"type": "LineString", "coordinates": coords} if len(coords) >= 2 else None
        if kind == "Polygon":
            rings = [
                _coordinates(c) for c in element.iter() if _local(c.tag) == "coordinates"
            ]
            rings = [ring for ring in rings if len(ring) >= 4]
            return {"type": "Polygon", "coordinates": rings} if rings else None
    return None


def _first_coordinates(element: ET.Element) -> list[list[float]]:
    for child in element.iter():
        if _local(child.tag) == "coordinates":
            return _coordinates(child)
    return []


def _cone(root: ET.Element) -> list[tuple[Any, ...]]:
    for placemark in _placemarks(root):
        geometry = _geometry(placemark)
        if geometry and geometry["type"] == "Polygon":
            return [(GeometryType.CYCLONE_CONE, FrameKind.FORECAST, geometry, {})]
    return []


def _extended(placemark: ET.Element) -> dict[str, str]:
    data: dict[str, str] = {}
    for element in placemark.iter():
        if _local(element.tag) == "Data" and element.get("name"):
            value = next((v.text for v in element if _local(v.tag) == "value"), None)
            data[element.get("name", "")] = (value or "").strip()
    return data


def _track(root: ET.Element) -> list[tuple[Any, ...]]:
    items: list[tuple[Any, ...]] = []
    longest: tuple[int, dict[str, Any]] | None = None

    for placemark in _placemarks(root):
        geometry = _geometry(placemark)
        if geometry is None:
            continue
        if geometry["type"] == "LineString":
            # NHC ships a 72 h and a 120 h line; the longer one contains the other.
            hours = int(_extended(placemark).get("fcstpd") or 0)
            if longest is None or hours > longest[0]:
                longest = (hours, geometry)
        elif geometry["type"] == "Point":
            point = _forecast_point(placemark)
            if point:
                items.append((GeometryType.CYCLONE_POSITION, FrameKind.FORECAST, geometry, point))

    if longest:
        items.insert(0, (GeometryType.CYCLONE_TRACK, FrameKind.FORECAST, longest[1], {}))
    return items


def _radii(root: ET.Element) -> list[tuple[Any, ...]]:
    items: list[tuple[Any, ...]] = []
    for placemark in _placemarks(root):
        name = next((e.text for e in placemark if _local(e.tag) == "name"), None)
        geometry = _geometry(placemark)
        if geometry and geometry["type"] == "Polygon" and (name or "").strip().isdigit():
            items.append(
                (
                    GeometryType.CYCLONE_WIND_RADII,
                    FrameKind.OBSERVED,
                    geometry,
                    {"windKt": int(name.strip())},
                )
            )
    return items


_TAG = re.compile(r"<[^>]+>")
_LEAD = re.compile(r"(\d+)\s*hr\s+Forecast", re.IGNORECASE)
_WIND = re.compile(r"Maximum Wind:\s*(\d+)\s*knots", re.IGNORECASE)
_VALID = re.compile(
    r"Valid at:\s*(\d{1,2}:\d{2}\s*[AP]M)\s+([A-Z]{2,4})\s+([A-Za-z]+\s+\d{1,2},\s*\d{4})"
)


def _forecast_point(placemark: ET.Element) -> dict[str, Any] | None:
    """Lead time, wind and valid time from a forecast point's description."""
    description = next((e.text for e in placemark if _local(e.tag) == "description"), None)
    text = _TAG.sub(" ", description or "")
    lead = _LEAD.search(text)
    if lead is None:
        # The current-position point has no lead time and the event marker covers it.
        return None

    props: dict[str, Any] = {"leadHours": int(lead.group(1))}
    wind = _WIND.search(text)
    if wind:
        props["maxWindKt"] = int(wind.group(1))
    valid = _VALID.search(text)
    if valid:
        valid_time = _local_to_utc(*valid.groups())
        if valid_time:
            props["valid_time"] = to_iso(valid_time)
            props["validTimeMs"] = valid_time.timestamp() * 1000
    return props


def _local_to_utc(clock: str, zone: str, date: str) -> datetime | None:
    hours = _ZONE_HOURS.get(zone)
    if hours is None:
        return None
    try:
        stamp = f"{' '.join(clock.split())} {' '.join(date.split())}"
        local = datetime.strptime(stamp, "%I:%M %p %B %d, %Y")
    except ValueError:
        return None
    return (local - timedelta(hours=hours)).replace(tzinfo=UTC)


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
