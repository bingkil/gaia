"""Notification policy.

Alert copy is deterministic and template-driven. Spec section 3.3 forbids any
generative model from creating or modifying life-safety text at delivery time,
so every string here is fixed and versioned.
"""

from __future__ import annotations

import hashlib
from datetime import timedelta

from ..config import AlertSettings, ModelSettings
from ..db import to_iso, utcnow
from ..domain.enums import AlertType, HazardType, ProvenanceClass, label_for
from ..domain.geo import haversine_km, to_shape
from ..domain.models import HazardEvent, ImpactResult, WatchArea
from .impact import alert_radius_km, earthquake_impact

POLICY_VERSION = "policy/1.0.0"
TEMPLATE_VERSION = "templates/1.0.0"

FOLLOW_AUTHORITIES = "Follow local authority instructions."

# Reviewed, generic action text. Never generated, never varied per event.
_ACTION_TEXT = {
    HazardType.EARTHQUAKE: "If you feel shaking: Drop, Cover, and Hold On.",
    HazardType.VOLCANO: FOLLOW_AUTHORITIES,
    HazardType.ASH: "This is an aviation ash forecast, not a surface-ashfall forecast.",
}


def idempotency_key(
    event_id: str,
    alert_type: AlertType,
    watch_area_id: str,
    change_bucket: str,
) -> str:
    material = f"{event_id}|{alert_type.value}|{watch_area_id}|{POLICY_VERSION}|{change_bucket}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def change_bucket(reasons: list[str]) -> str:
    """Collapse reason codes so equivalent revisions share one key."""
    return ",".join(sorted(set(reasons))) or "none"


def should_alert(
    event: HazardEvent,
    area: WatchArea,
    impact: ImpactResult | None,
    alert_type: AlertType,
    config: AlertSettings,
) -> tuple[bool, list[str]]:
    """Decide whether this event warrants notifying this watch area."""
    reasons: list[str] = []

    if event.hazard_type not in area.hazard_types:
        return False, ["HAZARD_TYPE_NOT_WATCHED"]

    # A retraction always reaches anyone who was told about the event.
    if alert_type == AlertType.CANCELLATION:
        return True, ["RETRACTION_ALWAYS_DELIVERED"]

    if event.confidence < config.min_confidence:
        return False, [f"CONFIDENCE_BELOW_{config.min_confidence}"]

    if event.hazard_type == HazardType.EARTHQUAKE:
        magnitude = event.summary.magnitude
        if magnitude is None:
            return False, ["MAGNITUDE_UNAVAILABLE"]
        if magnitude < area.min_magnitude:
            return False, [f"BELOW_WATCH_THRESHOLD_{area.min_magnitude}"]

        if impact is None:
            return False, ["IMPACT_NOT_COMPUTABLE"]

        radius = min(area.radius_km, alert_radius_km(magnitude, event.summary.depth_km))
        if impact.distance_km > radius:
            return False, [f"OUTSIDE_RADIUS_{radius:.0f}_KM"]

        reasons.append(f"WITHIN_{radius:.0f}_KM")
        reasons.append(f"MAGNITUDE_{magnitude}")
        return True, reasons

    # Volcanic events and ash rely on geometry intersection rather than radius.
    if impact is not None and impact.ash_intersects:
        return True, ["ASH_GEOMETRY_INTERSECTS_WATCH_AREA"]

    if impact is not None and impact.distance_km <= area.radius_km:
        return True, [f"VOLCANO_WITHIN_{area.radius_km:.0f}_KM"]

    return False, ["NO_GEOMETRIC_RELATIONSHIP"]


def compose(
    event: HazardEvent,
    area: WatchArea,
    impact: ImpactResult | None,
    alert_type: AlertType,
    model: ModelSettings,
) -> tuple[str, str]:
    """Build deterministic notification title and body."""
    label = label_for(event.provenance_class, event.hazard_type)

    if alert_type == AlertType.CANCELLATION:
        title = "Event withdrawn"
        body = (
            f"The previously reported event near {event.summary.place or 'unknown location'} "
            f"has been retracted by the source. {FOLLOW_AUTHORITIES}"
        )
        return title, body

    if event.hazard_type == HazardType.EARTHQUAKE:
        magnitude = event.summary.magnitude
        place = event.summary.place or "unknown location"
        distance = f"{impact.distance_km:.0f} km away" if impact else "distance unknown"
        title = f"M{magnitude} earthquake {distance}"

        lines = [f"{label}. Source: {', '.join(event.providers)}."]

        if impact and impact.s_arrival and not impact.already_arrived:
            earliest = max(0, int(impact.s_arrival.seconds_from_now - _spread(impact)))
            latest = int(impact.s_arrival.seconds_from_now + _spread(impact))
            lines.append(f"Estimated shaking arrival: {earliest}\u2013{latest} seconds (modelled).")
        elif impact and impact.already_arrived:
            lines.append("Shaking may already have arrived.")

        if event.summary.tsunami:
            lines.append("Source reports a tsunami flag for this event.")

        lines.append(f"Near {place}.")
        lines.append(_ACTION_TEXT[HazardType.EARTHQUAKE])
        lines.append(FOLLOW_AUTHORITIES)
        return title, " ".join(lines)

    name = event.summary.volcano_name or event.summary.place or "Unknown volcano"
    if impact is not None and impact.ash_intersects:
        title = f"Volcanic ash forecast near {area.name}"
        when = to_iso(impact.ash_entry_time) or "an unspecified time"
        altitude = ""
        if impact.ash_altitude and impact.ash_altitude.top_meters:
            altitude = f" up to {int(impact.ash_altitude.top_meters)} m."
        body = (
            f"{label}. Forecast ash may affect the area around {when}.{altitude} "
            f"{_ACTION_TEXT[HazardType.ASH]} {FOLLOW_AUTHORITIES}"
        )
        return title, body

    title = f"Volcanic activity reported: {name}"
    level = f" Alert level {event.summary.alert_level}." if event.summary.alert_level else ""
    body = (
        f"{label}. Source: {', '.join(event.providers)}.{level} {FOLLOW_AUTHORITIES}"
    )
    return title, body


def _spread(impact: ImpactResult) -> float:
    if impact.s_arrival is None:
        return 0.0
    return (impact.s_arrival.latest - impact.s_arrival.estimate).total_seconds()


def within_cooldown(last_sent, alert_type: AlertType, config: AlertSettings) -> bool:
    """Escalations and retractions bypass cooldown. Spec section 16.2."""
    if alert_type in (AlertType.CANCELLATION, AlertType.ESCALATION):
        return False
    if last_sent is None:
        return False
    return utcnow() - last_sent < timedelta(seconds=config.cooldown_seconds)


def impact_for_area(
    event: HazardEvent,
    area: WatchArea,
    frames: list,
    model: ModelSettings,
) -> ImpactResult | None:
    from .impact import ash_impact

    if event.hazard_type == HazardType.EARTHQUAKE:
        centre = to_shape(area.geometry).centroid
        return earthquake_impact(event, centre.x, centre.y, model)

    if frames:
        return ash_impact(event, frames, area.geometry)

    if event.longitude is None or event.latitude is None:
        return None

    centre = to_shape(area.geometry).centroid
    return ImpactResult(
        event_id=event.id,
        distance_km=round(
            haversine_km(centre.x, centre.y, event.longitude, event.latitude), 1
        ),
        provenance_class=ProvenanceClass.MODEL_ESTIMATE,
    )
