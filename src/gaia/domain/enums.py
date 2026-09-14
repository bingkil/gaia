"""Safety-critical vocabulary.

Spec section 3 requires that provenance and quality be enforced in code rather
than left to copywriting. Every user-facing label is derived from these enums;
no call site is permitted to invent its own wording.
"""

from __future__ import annotations

from enum import StrEnum


class HazardType(StrEnum):
    EARTHQUAKE = "EARTHQUAKE"
    VOLCANO = "VOLCANO"
    ASH = "ASH"
    WILDFIRE = "WILDFIRE"


class EventState(StrEnum):
    DETECTED = "DETECTED"
    PRELIMINARY = "PRELIMINARY"
    CONFIRMED = "CONFIRMED"
    UPDATED = "UPDATED"
    ENDED = "ENDED"
    RETRACTED = "RETRACTED"


# Transitions permitted by the state machine in spec section 11.4.
ALLOWED_TRANSITIONS: dict[EventState, frozenset[EventState]] = {
    EventState.DETECTED: frozenset({EventState.PRELIMINARY, EventState.RETRACTED}),
    EventState.PRELIMINARY: frozenset(
        {EventState.CONFIRMED, EventState.RETRACTED, EventState.UPDATED, EventState.ENDED}
    ),
    EventState.CONFIRMED: frozenset({EventState.UPDATED, EventState.ENDED, EventState.RETRACTED}),
    EventState.UPDATED: frozenset({EventState.UPDATED, EventState.ENDED, EventState.RETRACTED}),
    EventState.ENDED: frozenset({EventState.UPDATED}),
    EventState.RETRACTED: frozenset(),
}


def can_transition(current: EventState, target: EventState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


class ProvenanceClass(StrEnum):
    AUTHORITATIVE_EEW = "AUTHORITATIVE_EEW"
    AUTHORITATIVE_NOTICE = "AUTHORITATIVE_NOTICE"
    MULTISOURCE_RAPID = "MULTISOURCE_RAPID"
    SINGLE_SOURCE_RAPID = "SINGLE_SOURCE_RAPID"
    AUTOMATED_SIGNAL = "AUTOMATED_SIGNAL"
    MODEL_ESTIMATE = "MODEL_ESTIMATE"


# The only labels permitted for each provenance class. Spec section 3.1.
PROVENANCE_LABELS: dict[ProvenanceClass, str] = {
    ProvenanceClass.AUTHORITATIVE_EEW: "Earthquake Early Warning",
    ProvenanceClass.AUTHORITATIVE_NOTICE: "Official notice",
    ProvenanceClass.MULTISOURCE_RAPID: "Rapid earthquake alert",
    ProvenanceClass.SINGLE_SOURCE_RAPID: "Preliminary earthquake report",
    ProvenanceClass.AUTOMATED_SIGNAL: "Possible event — automated detection",
    ProvenanceClass.MODEL_ESTIMATE: "Estimate",
}

# The default labels name the earthquake case. A label must never assert a
# hazard the event is not, so non-seismic hazards override them here.
HAZARD_PROVENANCE_LABELS: dict[tuple[HazardType, ProvenanceClass], str] = {
    (HazardType.VOLCANO, ProvenanceClass.MULTISOURCE_RAPID): "Volcanic activity report",
    (
        HazardType.VOLCANO,
        ProvenanceClass.SINGLE_SOURCE_RAPID,
    ): "Preliminary volcanic activity report",
    (HazardType.ASH, ProvenanceClass.MULTISOURCE_RAPID): "Volcanic ash report",
    (HazardType.ASH, ProvenanceClass.SINGLE_SOURCE_RAPID): "Preliminary volcanic ash report",
    (HazardType.ASH, ProvenanceClass.AUTHORITATIVE_NOTICE): "Official volcanic ash advisory",
    # A thermal cluster with no official counterpart keeps the generic
    # automated-detection wording, which already says "possible" and names no
    # cause. Satellite heat alone cannot tell a fire from a flare.
    (HazardType.WILDFIRE, ProvenanceClass.MULTISOURCE_RAPID): "Wildfire report",
    (HazardType.WILDFIRE, ProvenanceClass.SINGLE_SOURCE_RAPID): "Preliminary wildfire report",
    (HazardType.WILDFIRE, ProvenanceClass.AUTHORITATIVE_NOTICE): "Official wildfire notice",
}

# Only an approved authority feed may ever carry an early-warning label. No
# catalogue-derived event may be promoted into this set at runtime.
AUTHORITATIVE_CLASSES = frozenset(
    {ProvenanceClass.AUTHORITATIVE_EEW, ProvenanceClass.AUTHORITATIVE_NOTICE}
)


def label_for(provenance: ProvenanceClass, hazard_type: HazardType | None = None) -> str:
    if hazard_type is not None:
        override = HAZARD_PROVENANCE_LABELS.get((hazard_type, provenance))
        if override is not None:
            return override
    return PROVENANCE_LABELS[provenance]


class Quality(StrEnum):
    PRELIMINARY = "PRELIMINARY"
    REVIEWED = "REVIEWED"
    OFFICIAL_ADVISORY = "OFFICIAL_ADVISORY"
    MODELLED = "MODELLED"
    UNAVAILABLE = "UNAVAILABLE"


class FrameKind(StrEnum):
    """Distinguishes what a geometry actually represents. Spec section 14.3
    requires observed, forecast, and platform-interpolated geometry to be
    visually and semantically distinct."""

    OBSERVED = "OBSERVED"
    FORECAST = "FORECAST"
    INTERPOLATED = "INTERPOLATED"


class GeometryType(StrEnum):
    ASH_CLOUD = "ASH_CLOUD"
    IMPACT_ZONE = "IMPACT_ZONE"
    THERMAL_ANOMALY = "THERMAL_ANOMALY"


class Action(StrEnum):
    UPSERT = "UPSERT"
    CANCEL = "CANCEL"
    DELETE = "DELETE"


class EruptionClassification(StrEnum):
    """Deterministic thermal-anomaly classification, spec section 13.1."""

    AUTOMATED_SIGNAL = "AUTOMATED_SIGNAL"
    POSSIBLE_ERUPTION = "POSSIBLE_ERUPTION"
    LIKELY_ERUPTION = "LIKELY_ERUPTION"
    CONFIRMED_ERUPTION = "CONFIRMED_ERUPTION"


class ProviderHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    DISABLED = "DISABLED"


class AlertType(StrEnum):
    """Notification lifecycle, spec section 16.2."""

    INITIAL = "INITIAL"
    MATERIAL_UPDATE = "MATERIAL_UPDATE"
    ESCALATION = "ESCALATION"
    CONFIRMATION = "CONFIRMATION"
    CANCELLATION = "CANCELLATION"
    EVENT_ENDED = "EVENT_ENDED"


# Retractions and authoritative escalations must bypass ordinary cooldown.
COOLDOWN_EXEMPT = frozenset({AlertType.CANCELLATION, AlertType.ESCALATION})
