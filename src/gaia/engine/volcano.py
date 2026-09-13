"""Volcano identity resolution and thermal-anomaly classification.

Deterministic rules only. Spec section 13.1 is explicit that a model may be
trained later, once labelled history exists and false-positive rates have been
measured per volcano type — not before.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from ..domain.enums import EruptionClassification
from ..domain.geo import haversine_km
from ..domain.models import Volcano


def _normalise(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


@dataclass
class VolcanoMatch:
    volcano: Volcano
    distance_km: float
    method: str


def match_by_position(
    longitude: float,
    latitude: float,
    volcanoes: list[Volcano],
    radius_km: float,
) -> VolcanoMatch | None:
    best: VolcanoMatch | None = None
    for volcano in volcanoes:
        distance = haversine_km(longitude, latitude, volcano.longitude, volcano.latitude)
        if distance <= radius_km and (best is None or distance < best.distance_km):
            best = VolcanoMatch(volcano=volcano, distance_km=distance, method="POSITION")
    return best


def match_by_name(name: str, volcanoes: list[Volcano]) -> VolcanoMatch | None:
    target = _normalise(name)
    if not target:
        return None

    for volcano in volcanoes:
        names = [volcano.name, *volcano.aliases]
        if any(_normalise(candidate) == target for candidate in names):
            return VolcanoMatch(volcano=volcano, distance_km=0.0, method="NAME")

    # Fall back to containment, which catches "Mount Etna" against "Etna".
    for volcano in volcanoes:
        names = [volcano.name, *volcano.aliases]
        for candidate in names:
            normalised = _normalise(candidate)
            if len(normalised) >= 5 and (normalised in target or target in normalised):
                return VolcanoMatch(volcano=volcano, distance_km=0.0, method="NAME_PARTIAL")
    return None


def resolve_volcano(
    volcanoes: list[Volcano],
    name: str | None = None,
    longitude: float | None = None,
    latitude: float | None = None,
    radius_km: float = 25.0,
) -> VolcanoMatch | None:
    """Resolve identity by name first, then position. Spec section 11.2."""
    if name:
        matched = match_by_name(name, volcanoes)
        if matched:
            return matched
    if longitude is not None and latitude is not None:
        return match_by_position(longitude, latitude, volcanoes, radius_km)
    return None


@dataclass
class ThermalCluster:
    volcano_id: str
    detection_count: int
    distinct_satellites: int
    max_frp: float
    nearest_km: float


def classify_thermal(
    cluster: ThermalCluster,
    has_official_event: bool = False,
    has_ash_advisory: bool = False,
) -> tuple[EruptionClassification, list[str]]:
    """Classify a thermal cluster. A single pixel is never an eruption."""
    reasons = [
        f"DETECTIONS_{cluster.detection_count}",
        f"NEAREST_{cluster.nearest_km:.1f}_KM",
    ]

    if has_ash_advisory:
        reasons.append("ASH_ADVISORY_PRESENT")
        return EruptionClassification.CONFIRMED_ERUPTION, reasons

    if has_official_event:
        reasons.append("OFFICIAL_EVENT_FEED_AGREES")
        return EruptionClassification.LIKELY_ERUPTION, reasons

    if cluster.detection_count == 1:
        reasons.append("SINGLE_ISOLATED_PIXEL")
        return EruptionClassification.AUTOMATED_SIGNAL, reasons

    # Persistence across separate satellites is what distinguishes sustained
    # volcanic heat from a transient wildfire detection.
    if cluster.detection_count >= 3 or cluster.distinct_satellites >= 2:
        reasons.append("CLUSTERED_OR_MULTI_SATELLITE")
        return EruptionClassification.POSSIBLE_ERUPTION, reasons

    reasons.append("WEAK_CLUSTER")
    return EruptionClassification.AUTOMATED_SIGNAL, reasons
