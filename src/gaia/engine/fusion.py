"""Canonical field selection and event assembly.

Every canonical field records which observation won it, so the API can explain
where each displayed value came from. Spec sections 11.3 and 11.4.
"""

from __future__ import annotations

from typing import Any

from ..db import utcnow
from ..domain.enums import (
    Action,
    EventState,
    HazardType,
    ProvenanceClass,
    Quality,
    can_transition,
)
from ..domain.models import EventSummary, HazardEvent, Observation, SourceRef

DECISION_VERSION = "fusion/1.0.0"

# Per-field source authority. Higher wins. Spec section 11.3 ranks by authority
# first, then quality, then freshness.
FIELD_AUTHORITY: dict[str, dict[str, int]] = {
    "location": {"USGS": 3, "EMSC": 3, "GEOFON": 2, "GDACS": 1, "FIRMS": 0},
    "magnitude": {"USGS": 3, "GEOFON": 3, "EMSC": 2, "GDACS": 0, "FIRMS": 0},
    "depth": {"USGS": 3, "GEOFON": 3, "EMSC": 2, "GDACS": 0, "FIRMS": 0},
    "place": {"EMSC": 3, "USGS": 3, "GEOFON": 1, "GDACS": 2, "FIRMS": 0},
    "volcano": {"GDACS": 3, "FIRMS": 1},
}

_EARTHQUAKE_PROVIDERS = {"EMSC", "USGS", "GEOFON"}


def _field_score(observation: Observation, field: str) -> tuple[float, float]:
    """Rank key for one observation on one field: (authority, recency)."""
    authority = float(FIELD_AUTHORITY.get(field, {}).get(observation.provider, 0))

    # An analyst-reviewed solution outranks a newer automatic one.
    if observation.normalized.get("reviewed"):
        authority += 2.0

    issued = observation.source_issued_at or observation.observed_at or observation.ingested_at
    return authority, issued.timestamp()


def _select(
    observations: list[Observation], field: str, key: str
) -> tuple[Any, Observation | None]:
    """Pick the winning value for a field, ignoring observations that lack it."""
    candidates = [o for o in observations if o.normalized.get(key) is not None]
    if not candidates:
        return None, None
    winner = max(candidates, key=lambda o: _field_score(o, field))
    return winner.normalized.get(key), winner


def classify_provenance(
    hazard_type: HazardType, observations: list[Observation]
) -> tuple[ProvenanceClass, list[str]]:
    """Catalogue feeds can never yield an authoritative early-warning class."""
    providers = {o.provider for o in observations}
    reasons: list[str] = []

    if hazard_type == HazardType.EARTHQUAKE:
        seismic = providers & _EARTHQUAKE_PROVIDERS
        if len(seismic) >= 2:
            reasons.append(
                "THREE_INDEPENDENT_SOURCES" if len(seismic) >= 3 else "TWO_INDEPENDENT_SOURCES"
            )
            return ProvenanceClass.MULTISOURCE_RAPID, reasons
        reasons.append("SINGLE_SOURCE")
        return ProvenanceClass.SINGLE_SOURCE_RAPID, reasons

    # Volcanic: a satellite heat signal alone is only an automated signal.
    if providers == {"FIRMS"}:
        reasons.append("THERMAL_SIGNAL_ONLY")
        return ProvenanceClass.AUTOMATED_SIGNAL, reasons

    if "GDACS" in providers and len(providers) > 1:
        reasons.append("EVENT_FEED_PLUS_INDEPENDENT_SIGNAL")
        return ProvenanceClass.MULTISOURCE_RAPID, reasons

    reasons.append("SINGLE_SOURCE")
    return ProvenanceClass.SINGLE_SOURCE_RAPID, reasons


def compute_confidence(
    hazard_type: HazardType, observations: list[Observation]
) -> tuple[float, list[str]]:
    provenance, reasons = classify_provenance(hazard_type, observations)
    providers = {o.provider for o in observations}

    if hazard_type == HazardType.EARTHQUAKE:
        independent = len(providers & _EARTHQUAKE_PROVIDERS)
        confidence = {0: 0.30, 1: 0.55, 2: 0.85}.get(independent, 0.97)
    else:
        confidence = 0.40 if provenance == ProvenanceClass.AUTOMATED_SIGNAL else 0.70
        if len(providers) > 1:
            confidence = 0.88

    if any(o.normalized.get("reviewed") for o in observations):
        confidence = min(0.99, confidence + 0.02)
        reasons.append("ANALYST_REVIEWED")

    if any(o.validation_warnings for o in observations):
        confidence = max(0.05, confidence - 0.05)
        reasons.append("VALIDATION_WARNINGS_PRESENT")

    return round(confidence, 3), reasons


def derive_state(
    observations: list[Observation],
    previous: EventState | None,
    provenance: ProvenanceClass,
) -> EventState:
    if any(o.action in (Action.DELETE, Action.CANCEL) for o in observations):
        return EventState.RETRACTED

    reviewed = any(o.normalized.get("reviewed") for o in observations)
    multisource = provenance == ProvenanceClass.MULTISOURCE_RAPID

    if previous is None:
        if multisource or reviewed:
            return EventState.CONFIRMED
        return EventState.PRELIMINARY

    if previous == EventState.RETRACTED:
        return EventState.RETRACTED

    target = EventState.CONFIRMED if (multisource or reviewed) else EventState.UPDATED
    if previous == EventState.PRELIMINARY and target == EventState.CONFIRMED:
        return EventState.CONFIRMED
    if previous in (EventState.CONFIRMED, EventState.UPDATED):
        return EventState.UPDATED
    return target if can_transition(previous, target) else previous


def derive_quality(observations: list[Observation]) -> Quality:
    if any(o.normalized.get("reviewed") for o in observations):
        return Quality.REVIEWED
    return Quality.PRELIMINARY


def build_event(
    event_id: str,
    hazard_type: HazardType,
    observations: list[Observation],
    previous: HazardEvent | None,
) -> tuple[HazardEvent, dict[str, Any]]:
    """Fuse all linked observations into the canonical event."""
    if not observations:
        raise ValueError("cannot build an event with no observations")

    ordered = sorted(observations, key=lambda o: o.ingested_at)

    longitude, lon_src = _select(ordered, "location", "longitude")
    latitude, lat_src = _select(ordered, "location", "latitude")
    magnitude, mag_src = _select(ordered, "magnitude", "magnitude")
    magnitude_type, _ = _select(ordered, "magnitude", "magnitude_type")
    depth, depth_src = _select(ordered, "depth", "depth_km")
    place, place_src = _select(ordered, "place", "place")
    volcano_name, volcano_src = _select(ordered, "volcano", "volcano_name")
    alert_level, _ = _select(ordered, "volcano", "alert_level")
    tsunami, _ = _select(ordered, "magnitude", "tsunami")

    provenance, provenance_reasons = classify_provenance(hazard_type, ordered)
    confidence, confidence_reasons = compute_confidence(hazard_type, ordered)
    state = derive_state(ordered, previous.state if previous else None, provenance)

    origin_times = [o.observed_at for o in ordered if o.observed_at]
    origin_time = min(origin_times) if origin_times else None

    field_provenance = {
        name: source.message_id
        for name, source in (
            ("longitude", lon_src),
            ("latitude", lat_src),
            ("magnitude", mag_src),
            ("depth_km", depth_src),
            ("place", place_src),
            ("volcano_name", volcano_src),
        )
        if source is not None
    }

    event = HazardEvent(
        id=event_id,
        hazard_type=hazard_type,
        state=state,
        provenance_class=provenance,
        quality=derive_quality(ordered),
        origin_time=origin_time,
        first_observed_at=origin_time,
        first_ingested_at=previous.first_ingested_at if previous else ordered[0].ingested_at,
        last_updated_at=utcnow(),
        revision=(previous.revision + 1) if previous else 1,
        longitude=longitude,
        latitude=latitude,
        summary=EventSummary(
            magnitude=magnitude,
            magnitude_type=magnitude_type,
            depth_km=depth,
            place=place or volcano_name,
            volcano_name=volcano_name,
            alert_level=alert_level,
            tsunami=bool(tsunami) if tsunami is not None else None,
        ),
        confidence=confidence,
        confidence_reasons=sorted(set(provenance_reasons + confidence_reasons)),
        source_refs=[
            SourceRef(
                provider=o.provider,
                source_id=o.source_id,
                revision=o.source_revision,
                observation_id=o.message_id,
            )
            for o in ordered
        ],
        field_provenance=field_provenance,
    )

    return event, diff_events(previous, event)


def diff_events(previous: HazardEvent | None, current: HazardEvent) -> dict[str, Any]:
    if previous is None:
        return {"created": True}

    changes: dict[str, Any] = {}

    def compare(name: str, before: Any, after: Any) -> None:
        if before != after:
            changes[name] = {"from": before, "to": after}

    compare("state", previous.state.value, current.state.value)
    compare("provenanceClass", previous.provenance_class.value, current.provenance_class.value)
    compare("quality", previous.quality.value, current.quality.value)
    compare("magnitude", previous.summary.magnitude, current.summary.magnitude)
    compare("depthKm", previous.summary.depth_km, current.summary.depth_km)
    compare("longitude", previous.longitude, current.longitude)
    compare("latitude", previous.latitude, current.latitude)
    compare("place", previous.summary.place, current.summary.place)
    compare("alertLevel", previous.summary.alert_level, current.summary.alert_level)
    compare("tsunami", previous.summary.tsunami, current.summary.tsunami)
    compare("confidence", previous.confidence, current.confidence)

    before_providers = set(previous.providers)
    after_providers = set(current.providers)
    if before_providers != after_providers:
        changes["providers"] = {
            "from": sorted(before_providers),
            "to": sorted(after_providers),
            "added": sorted(after_providers - before_providers),
        }

    return changes
