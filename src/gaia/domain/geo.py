"""Geodesic and geometry helpers.

Local-first replacement for the PostGIS operations in the spec: Shapely handles
exact predicates, and a bounding-box prefilter stands in for a spatial index.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle surface distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def hypocentral_distance_km(surface_km: float, depth_km: float) -> float:
    return math.sqrt(surface_km**2 + max(0.0, depth_km) ** 2)


def bbox_of(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    return shape(geometry).bounds


def to_shape(geometry: dict[str, Any]) -> BaseGeometry:
    return shape(geometry)


def to_geojson(geom: BaseGeometry) -> dict[str, Any]:
    return mapping(geom)  # type: ignore[return-value]


def bbox_intersects(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def point_geojson(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [lon, lat]}


def circle_geojson(lon: float, lat: float, radius_km: float, segments: int = 64) -> dict[str, Any]:
    """Approximate a geodesic circle as a polygon ring.

    Accurate enough for display and candidate filtering; exact distance checks
    still use haversine.
    """
    coords: list[list[float]] = []
    lat_rad = math.radians(lat)
    for i in range(segments + 1):
        bearing = 2 * math.pi * i / segments
        dlat = (radius_km / EARTH_RADIUS_KM) * math.cos(bearing)
        cos_lat = math.cos(lat_rad)
        dlon = (radius_km / EARTH_RADIUS_KM) * math.sin(bearing) / max(cos_lat, 1e-9)
        coords.append([lon + math.degrees(dlon), lat + math.degrees(dlat)])
    return {"type": "Polygon", "coordinates": [coords]}


def surface_wave_radius_km(elapsed_seconds: float, depth_km: float, velocity_km_s: float) -> float:
    """Radius at the surface of a wavefront expanding from the hypocentre.

    Geometric visualisation of a simplified velocity model, not a prediction of
    shaking strength. Spec section 14.6.
    """
    travelled = velocity_km_s * max(0.0, elapsed_seconds)
    return math.sqrt(max(0.0, travelled**2 - depth_km**2))


def normalise_longitude(lon: float) -> float:
    """Wrap to [-180, 180]. Guards against antimeridian artefacts in feeds."""
    return ((lon + 180.0) % 360.0) - 180.0


def valid_coordinates(lon: float | None, lat: float | None) -> bool:
    if lon is None or lat is None:
        return False
    if math.isnan(lon) or math.isnan(lat):
        return False
    return -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0
