"""Event correlation.

Decides whether a new observation describes an event already being tracked.
Conservative by design: a false merge corrupts magnitude, location, and impact
for every downstream consumer, which is worse than briefly carrying two
records that later merge.

Spec section 11.1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import CorrelationSettings
from ..domain.geo import haversine_km
from ..domain.models import HazardEvent, Observation


@dataclass
class MatchResult:
    event: HazardEvent | None
    score: float
    reasons: list[str] = field(default_factory=list)
    ambiguous: bool = False

    @property
    def matched(self) -> bool:
        return self.event is not None


def _similarity(delta: float, limit: float) -> float:
    if limit <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(delta) / limit)


def score_pair(
    observation: Observation,
    event: HazardEvent,
    config: CorrelationSettings,
) -> tuple[float, list[str]]:
    """Score one candidate. Returns (score, reasons); 0.0 means disqualified."""
    reasons: list[str] = []

    if observation.observed_at is None or event.origin_time is None:
        return 0.0, ["MISSING_ORIGIN_TIME"]

    # An identifier the provider itself already linked is decisive.
    for ref in event.source_refs:
        if ref.provider == observation.provider and ref.source_id == observation.source_id:
            return 1.0, ["PROVIDER_ID_MATCH"]

    # Two distinct identifiers from the same provider are strong evidence of two
    # separate events, which is what keeps close aftershocks apart.
    if any(
        ref.provider == observation.provider and ref.source_id != observation.source_id
        for ref in event.source_refs
    ):
        return 0.0, ["SAME_PROVIDER_DISTINCT_ID"]

    time_delta = abs((observation.observed_at - event.origin_time).total_seconds())
    if time_delta > config.max_time_delta_seconds:
        return 0.0, ["TIME_WINDOW_EXCEEDED"]

    if (
        observation.longitude is None
        or observation.latitude is None
        or event.longitude is None
        or event.latitude is None
    ):
        return 0.0, ["MISSING_COORDINATES"]

    distance = haversine_km(
        observation.longitude, observation.latitude, event.longitude, event.latitude
    )
    if distance > config.max_distance_km:
        return 0.0, ["DISTANCE_EXCEEDED"]

    obs_mag, event_mag = observation.magnitude, event.summary.magnitude
    if obs_mag is not None and event_mag is not None:
        magnitude_delta = abs(obs_mag - event_mag)
        if magnitude_delta > config.max_magnitude_delta:
            return 0.0, ["MAGNITUDE_DIVERGENCE"]
        magnitude_similarity = _similarity(magnitude_delta, config.max_magnitude_delta)
        reasons.append(f"MAGNITUDE_DELTA_{magnitude_delta:.1f}")
    else:
        # Absent magnitude is neutral evidence, not supporting evidence.
        magnitude_similarity = 0.5
        reasons.append("MAGNITUDE_UNAVAILABLE")

    time_similarity = _similarity(time_delta, config.max_time_delta_seconds)
    distance_similarity = _similarity(distance, config.max_distance_km)

    score = (
        config.weight_time * time_similarity
        + config.weight_distance * distance_similarity
        + config.weight_magnitude * magnitude_similarity
    )

    reasons.append(f"ORIGIN_TIME_MATCH_WITHIN_{time_delta:.0f}_SECONDS")
    reasons.append(f"SPATIAL_MATCH_WITHIN_{distance:.0f}_KM")
    return score, reasons


def best_match(
    observation: Observation,
    candidates: list[HazardEvent],
    config: CorrelationSettings,
) -> MatchResult:
    scored: list[tuple[float, HazardEvent, list[str]]] = []
    for candidate in candidates:
        score, reasons = score_pair(observation, candidate, config)
        if score > 0:
            scored.append((score, candidate, reasons))

    if not scored:
        return MatchResult(event=None, score=0.0, reasons=["NO_CANDIDATE"])

    scored.sort(key=lambda item: item[0], reverse=True)
    score, event, reasons = scored[0]

    # Two candidates of comparable quality mean the link is not yet decidable.
    if len(scored) > 1 and scored[1][0] >= score - 0.05 and score < 1.0:
        return MatchResult(
            event=None,
            score=score,
            reasons=[*reasons, "AMBIGUOUS_MULTIPLE_CANDIDATES"],
            ambiguous=True,
        )

    if score >= config.auto_link_score:
        return MatchResult(event=event, score=score, reasons=reasons)

    if score >= config.candidate_score:
        return MatchResult(
            event=None, score=score, reasons=[*reasons, "BELOW_AUTO_LINK"], ambiguous=True
        )

    return MatchResult(event=None, score=score, reasons=[*reasons, "SCORE_TOO_LOW"])
