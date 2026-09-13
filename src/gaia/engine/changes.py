"""Semantic change detection.

A provider revision is not a reason to notify. This module reduces a raw diff
to the changes that actually alter what a person would do. Spec section 11.5.
"""

from __future__ import annotations

from typing import Any

from ..config import AlertSettings
from ..domain.enums import AlertType, EventState, HazardType, ProvenanceClass
from ..domain.geo import haversine_km
from ..domain.models import HazardEvent

# Provenance strength ordering; a move up this list is an escalation.
_PROVENANCE_RANK = {
    ProvenanceClass.MODEL_ESTIMATE: 0,
    ProvenanceClass.AUTOMATED_SIGNAL: 1,
    ProvenanceClass.SINGLE_SOURCE_RAPID: 2,
    ProvenanceClass.MULTISOURCE_RAPID: 3,
    ProvenanceClass.AUTHORITATIVE_NOTICE: 4,
    ProvenanceClass.AUTHORITATIVE_EEW: 5,
}

_ALERT_LEVEL_RANK = {"GREEN": 0, "ORANGE": 1, "RED": 2}

EPICENTRE_MOVE_KM = 25.0
DEPTH_CHANGE_KM = 30.0


def material_changes(
    previous: HazardEvent | None,
    current: HazardEvent,
    config: AlertSettings,
) -> tuple[AlertType | None, list[str]]:
    """Return the alert type warranted by this revision, or None."""
    if current.state == EventState.RETRACTED:
        return AlertType.CANCELLATION, ["EVENT_RETRACTED"]

    if previous is None:
        return AlertType.INITIAL, ["FIRST_OBSERVATION"]

    reasons: list[str] = []
    escalated = False

    before_rank = _PROVENANCE_RANK[previous.provenance_class]
    after_rank = _PROVENANCE_RANK[current.provenance_class]
    if after_rank > before_rank:
        reasons.append("PROVENANCE_UPGRADED")
        escalated = True

    if current.hazard_type == HazardType.EARTHQUAKE:
        escalated |= _earthquake_changes(previous, current, config, reasons)
    else:
        escalated |= _volcano_changes(previous, current, reasons)

    if previous.state != EventState.CONFIRMED and current.state == EventState.CONFIRMED:
        reasons.append("EVENT_CONFIRMED")

    if current.state == EventState.ENDED and previous.state != EventState.ENDED:
        return AlertType.EVENT_ENDED, [*reasons, "EVENT_ENDED"]

    if not reasons:
        return None, []

    if escalated:
        return AlertType.ESCALATION, reasons
    if "EVENT_CONFIRMED" in reasons and len(reasons) == 1:
        return AlertType.CONFIRMATION, reasons
    return AlertType.MATERIAL_UPDATE, reasons


def _earthquake_changes(
    previous: HazardEvent,
    current: HazardEvent,
    config: AlertSettings,
    reasons: list[str],
) -> bool:
    escalated = False
    before_mag = previous.summary.magnitude
    after_mag = current.summary.magnitude

    if before_mag is not None and after_mag is not None:
        delta = after_mag - before_mag
        if abs(delta) >= config.magnitude_change_threshold:
            reasons.append(f"MAGNITUDE_CHANGED_{delta:+.1f}")
            escalated = escalated or delta > 0

        # Crossing the notification threshold matters even for a small change.
        if (before_mag < config.min_magnitude) != (after_mag < config.min_magnitude):
            reasons.append("MAGNITUDE_CROSSED_THRESHOLD")
            escalated = escalated or after_mag >= config.min_magnitude
    elif after_mag is not None and before_mag is None:
        reasons.append("MAGNITUDE_AVAILABLE")

    if None not in (previous.longitude, previous.latitude, current.longitude, current.latitude):
        moved = haversine_km(
            previous.longitude, previous.latitude, current.longitude, current.latitude
        )
        if moved >= EPICENTRE_MOVE_KM:
            reasons.append(f"EPICENTRE_MOVED_{moved:.0f}_KM")

    before_depth, after_depth = previous.summary.depth_km, current.summary.depth_km
    if before_depth is not None and after_depth is not None:
        if abs(after_depth - before_depth) >= DEPTH_CHANGE_KM:
            reasons.append("DEPTH_CHANGED_MATERIALLY")

    if previous.summary.tsunami != current.summary.tsunami:
        reasons.append("TSUNAMI_FLAG_CHANGED")
        escalated = escalated or bool(current.summary.tsunami)

    return escalated


def _volcano_changes(
    previous: HazardEvent, current: HazardEvent, reasons: list[str]
) -> bool:
    escalated = False
    before = _ALERT_LEVEL_RANK.get(previous.summary.alert_level or "", -1)
    after = _ALERT_LEVEL_RANK.get(current.summary.alert_level or "", -1)

    if after > before >= 0:
        reasons.append("ALERT_LEVEL_ESCALATED")
        escalated = True
    elif before > after >= 0:
        reasons.append("ALERT_LEVEL_LOWERED")

    return escalated


def ash_frame_changes(
    previous_frames: list[dict[str, Any]], current_frames: list[dict[str, Any]]
) -> list[str]:
    """Compare advisory frame sets. Spec section 11.5 volcano triggers."""
    reasons: list[str] = []

    had_observed = any(f.get("kind") == "OBSERVED" for f in previous_frames)
    has_observed = any(f.get("kind") == "OBSERVED" for f in current_frames)
    if has_observed and not had_observed:
        reasons.append("OBSERVED_ASH_APPEARED")
    elif had_observed and not has_observed:
        reasons.append("OBSERVED_ASH_CLEARED")

    before_top = max((f.get("top_flight_level") or 0 for f in previous_frames), default=0)
    after_top = max((f.get("top_flight_level") or 0 for f in current_frames), default=0)
    # One flight-level band is 100; require a full band to avoid churn.
    if abs(after_top - before_top) >= 100:
        reasons.append(f"ASH_TOP_CHANGED_FL{before_top}_TO_FL{after_top}")

    return reasons
