"""NHC payloads shaped from a live CurrentStorms.json and its KMZ products."""

from __future__ import annotations

import base64
import io
import json
import zipfile

KML_OPEN = '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
KML_CLOSE = "</Document></kml>"


def kmz(kml: str, name: str = "product.kml") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, kml)
    return buffer.getvalue()


def _line(hours: int, coordinates: str) -> str:
    return (
        f"<Placemark><LineString><coordinates>{coordinates}</coordinates></LineString>"
        f'<ExtendedData><Data name="fcstpd"><value>{hours}</value></Data></ExtendedData></Placemark>'
    )


def _point(text: str, lon: float, lat: float) -> str:
    return (
        f"<Placemark><description><![CDATA[<table><tr><td>{text}</td></tr></table>]]></description>"
        f"<Point><coordinates>{lon},{lat},0</coordinates></Point></Placemark>"
    )


def track_kml(zone: str = "CDT") -> str:
    return (
        KML_OPEN
        + _line(72, " -87.2,28.4,0 -86.8,29.7,0 -87.1,32.1,0 ")
        + _line(120, " -87.2,28.4,0 -86.8,29.7,0 -87.1,32.1,0 -87.2,34.2,0 ")
        + _point(
            f"Advisory #12A Advisory Information Valid at: 1:00 PM {zone} October 09, 2026 "
            "Maximum Wind: 105 knots (120 mph)",
            -87.2,
            28.4,
        )
        + _point(
            f"Advisory #12A 12 hr Forecast Valid at: 7:00 PM {zone} October 09, 2026 "
            "Location: 29.7 N, -86.8 W Maximum Wind: 100 knots (115 mph)",
            -86.8,
            29.7,
        )
        + _point(
            f"Advisory #12A 24 hr Forecast Valid at: 7:00 AM {zone} October 10, 2026 "
            "Location: 32.1 N, -87.1 W Maximum Wind: 55 knots (65 mph)",
            -87.1,
            32.1,
        )
        + KML_CLOSE
    )


CONE_KML = (
    KML_OPEN
    + "<Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
    + "-87.5,28.0 -86.0,29.5 -86.5,33.0 -88.5,32.0 -87.5,28.0"
    + "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
    + KML_CLOSE
)


def _radius(knots: int, ring: str) -> str:
    return (
        f"<Placemark><name>{knots}</name><Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{ring}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
    )


RADII_KML = (
    KML_OPEN
    + _radius(34, "-87.0,28.0 -86.0,28.4 -87.0,29.5 -88.0,28.4 -87.0,28.0")
    + _radius(64, "-87.1,28.2 -86.7,28.4 -87.1,28.8 -87.5,28.4 -87.1,28.2")
    + KML_CLOSE
)

DTD_KML = '<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY a "boom">]><kml><Document/></kml>'


def storm(
    storm_id: str = "al092026",
    name: str = "Isaias",
    lon: float | None = -87.2,
    lat: float | None = 28.4,
    wind: str = "105",
    updated: str = "2026-10-09T18:00:00.000Z",
) -> dict:
    return {
        "id": storm_id,
        "name": name,
        "classification": "HU",
        "intensity": wind,
        "latitudeNumeric": lat,
        "longitudeNumeric": lon,
        "lastUpdate": updated,
        "publicAdvisory": {"url": "https://www.nhc.noaa.gov/text/MIATCPAT4.shtml"},
    }


def bundle(files: dict[str, bytes] | None = None, **storm_kwargs) -> bytes:
    """A stored NHC payload. ``files`` defaults to a full set of products."""
    if files is None:
        files = {
            "track": kmz(track_kml()),
            "cone": kmz(CONE_KML),
            "radii": kmz(RADII_KML),
        }
    entry = {
        "storm": storm(**storm_kwargs),
        "kmz": {key: base64.b64encode(data).decode("ascii") for key, data in files.items()},
    }
    return json.dumps({"fetchedAt": "2026-10-09T18:05:00Z", "storms": [entry]}).encode()
