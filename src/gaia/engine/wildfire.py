"""Wildfire clustering rules for satellite thermal detections.

Deterministic only, and deliberately stricter than the volcanic path. A
volcano is a cataloged point, so heat beside one is already half explained;
a fire has no such prior, and gas flares, industrial heat and agricultural
burning all produce the same signature as one pixel. Nothing here asserts a
fire — it only decides whether a cluster is worth showing as a possibility.
"""

from __future__ import annotations

from dataclasses import dataclass

# A fire front spans kilometres, so detections this far apart still belong to
# one fire. FIRMS pixels are 375 m for VIIRS and about 1 km for MODIS.
FIRE_CLUSTER_RADIUS_KM = 5.0

# GDACS reports a centroid for a burnt area that can reach hundreds of square
# kilometres, so corroboration has to be generous about distance.
FIRE_FUSION_RADIUS_KM = 50.0

# A lone pixel is never a fire. Nor are two.
FIRE_MIN_DETECTIONS = 5

# Fire radiative power high enough that a single satellite is still worth
# reporting. Agricultural burns and flares rarely sustain this.
FIRE_STRONG_FRP_MW = 100.0

# Both VIIRS satellites overfly the same ground daily, so agreement between
# them separates a real surface fire from a sensor artefact but not from a
# field being cleared. Pair it with power a managed burn seldom holds.
FIRE_MIN_FRP_MW = 50.0


@dataclass
class FireCluster:
    detection_count: int
    distinct_satellites: int
    max_frp: float
    longitude: float
    latitude: float


def classify_fire(
    cluster: FireCluster,
    has_official_event: bool = False,
) -> tuple[bool, list[str]]:
    """Decide whether a thermal cluster may surface as a wildfire event."""
    reasons = [
        f"DETECTIONS_{cluster.detection_count}",
        f"MAX_FRP_{cluster.max_frp:.0f}",
    ]

    if has_official_event:
        reasons.append("OFFICIAL_EVENT_FEED_AGREES")
        return True, reasons

    if cluster.detection_count < FIRE_MIN_DETECTIONS:
        reasons.append("CLUSTER_TOO_SMALL")
        return False, reasons

    # Two satellites seeing the same ground rules out most sensor artefacts.
    if cluster.distinct_satellites >= 2 and cluster.max_frp >= FIRE_MIN_FRP_MW:
        reasons.append("MULTI_SATELLITE")
        return True, reasons

    if cluster.max_frp >= FIRE_STRONG_FRP_MW:
        reasons.append("STRONG_RADIATIVE_POWER")
        return True, reasons

    reasons.append("WEAK_RADIATIVE_POWER")
    return False, reasons
