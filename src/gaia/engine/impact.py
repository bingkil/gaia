"""Impact and arrival estimation.

Everything here is a model estimate and is labelled as such. The constant
velocity model is an MVP visual aid: it ignores crustal structure, rupture
propagation, basin amplification, and hypocentre uncertainty. Spec section 12.

Intensity is deliberately not derived from magnitude and distance. Spec section
12.3 forbids presenting such a figure in a safety-facing feature, so GAIA shows
distance and arrival only until a validated product is available.
"""

from __future__ import annotations

from datetime import timedelta

from shapely.geometry import shape

from ..config import ModelSettings
from ..db import utcnow
from ..domain.enums import FrameKind, ProvenanceClass, Quality
from ..domain.geo import haversine_km, hypocentral_distance_km
from ..domain.models import (
    ArrivalEstimate,
    AshAltitude,
    GeometryFrame,
    HazardEvent,
    ImpactResult,
)


def arrival_estimate(
    hypocentral_km: float,
    velocity_km_s: float,
    origin_time,
    config: ModelSettings,
) -> ArrivalEstimate:
    travel_seconds = hypocentral_km / velocity_km_s
    estimate = origin_time + timedelta(seconds=travel_seconds)

    # Report an interval rather than a single instant.
    spread = travel_seconds * config.uncertainty_fraction
    now = utcnow()

    return ArrivalEstimate(
        estimate=estimate,
        earliest=estimate - timedelta(seconds=spread),
        latest=estimate + timedelta(seconds=spread),
        seconds_from_now=(estimate - now).total_seconds(),
        model=config.version,
        quality=Quality.MODELLED,
    )


def earthquake_impact(
    event: HazardEvent,
    longitude: float,
    latitude: float,
    config: ModelSettings,
) -> ImpactResult | None:
    if event.longitude is None or event.latitude is None or event.origin_time is None:
        return None

    surface_km = haversine_km(longitude, latitude, event.longitude, event.latitude)
    depth = event.summary.depth_km or 0.0
    hypocentral = hypocentral_distance_km(surface_km, depth)

    p_arrival = arrival_estimate(hypocentral, config.p_velocity_km_s, event.origin_time, config)
    s_arrival = arrival_estimate(hypocentral, config.s_velocity_km_s, event.origin_time, config)

    # A countdown is only meaningful if the wave has not already passed, with a
    # margin for the time it takes to actually deliver the alert.
    remaining = s_arrival.seconds_from_now - config.delivery_margin_seconds

    return ImpactResult(
        event_id=event.id,
        distance_km=round(surface_km, 1),
        hypocentral_distance_km=round(hypocentral, 1),
        p_arrival=p_arrival,
        s_arrival=s_arrival,
        already_arrived=remaining <= 0,
        provenance_class=ProvenanceClass.MODEL_ESTIMATE,
    )


def ash_impact(
    event: HazardEvent,
    frames: list[GeometryFrame],
    geometry: dict,
) -> ImpactResult:
    """Intersect a location or area with observed and forecast ash frames.

    An aviation ash-cloud polygon describes airborne ash. It is not a
    surface-ashfall forecast, and the result must not be presented as one.
    """
    target = shape(geometry)
    entry_time = None
    exit_time = None
    intersects_now = False
    altitude: AshAltitude | None = None

    for frame in sorted(frames, key=lambda f: f.valid_time):
        if not shape(frame.geometry).intersects(target):
            continue

        if entry_time is None:
            entry_time = frame.valid_time
        exit_time = frame.valid_time

        if frame.frame_kind == FrameKind.OBSERVED:
            intersects_now = True

        if altitude is None:
            altitude = AshAltitude(
                bottom_meters=frame.lower_altitude_m,
                top_meters=frame.upper_altitude_m,
            )

    centre = target.centroid
    distance = 0.0
    if event.longitude is not None and event.latitude is not None:
        distance = haversine_km(centre.x, centre.y, event.longitude, event.latitude)

    return ImpactResult(
        event_id=event.id,
        distance_km=round(distance, 1),
        ash_intersects=entry_time is not None,
        ash_entry_time=entry_time,
        ash_exit_time=exit_time,
        ash_altitude=altitude,
        already_arrived=intersects_now,
        provenance_class=ProvenanceClass.MODEL_ESTIMATE,
    )


def alert_radius_km(magnitude: float | None, depth_km: float | None) -> float:
    """Screening radius for deciding who might care about an event.

    A coarse prioritisation heuristic, not a shaking-intensity estimate. Deeper
    events are felt over a wider area, so depth widens the radius.
    """
    if magnitude is None:
        return 100.0

    radius = 10.0 * (2.0 ** max(0.0, magnitude - 3.0))
    if depth_km and depth_km > 70.0:
        radius *= 1.5
    return min(radius, 2000.0)
