"""Canonical domain model, spec section 8.

Provider field names must never reach these structures; adapters translate into
the observation envelope and nothing else.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .enums import (
    Action,
    EventState,
    FrameKind,
    GeometryType,
    HazardType,
    ProvenanceClass,
    Quality,
)


class Observation(BaseModel):
    """The single envelope every adapter emits. Spec section 8.3."""

    message_id: str
    provider: str
    source_id: str
    source_revision: str
    hazard_type: HazardType
    action: Action = Action.UPSERT
    source_issued_at: datetime | None = None
    observed_at: datetime | None = None
    ingested_at: datetime
    schema_version: str = "observation/1.0"
    parser_version: str
    raw_object_key: str = ""
    raw_sha256: str = ""
    normalized: dict[str, Any] = Field(default_factory=dict)
    validation_warnings: list[str] = Field(default_factory=list)

    @property
    def longitude(self) -> float | None:
        return self.normalized.get("longitude")

    @property
    def latitude(self) -> float | None:
        return self.normalized.get("latitude")

    @property
    def depth_km(self) -> float | None:
        return self.normalized.get("depth_km")

    @property
    def magnitude(self) -> float | None:
        return self.normalized.get("magnitude")


class SourceRef(BaseModel):
    provider: str
    source_id: str
    revision: str
    observation_id: str


class EventSummary(BaseModel):
    magnitude: float | None = None
    magnitude_type: str | None = None
    depth_km: float | None = None
    place: str | None = None
    volcano_id: str | None = None
    volcano_name: str | None = None
    alert_level: str | None = None
    tsunami: bool | None = None


class HazardEvent(BaseModel):
    """Canonical fused event. Spec section 8.1."""

    id: str
    hazard_type: HazardType
    state: EventState
    provenance_class: ProvenanceClass
    quality: Quality
    origin_time: datetime | None = None
    first_observed_at: datetime | None = None
    first_ingested_at: datetime
    last_updated_at: datetime
    revision: int = 1
    longitude: float | None = None
    latitude: float | None = None
    summary: EventSummary = Field(default_factory=EventSummary)
    confidence: float = 0.0
    confidence_reasons: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    # Which observation won each canonical field, so the API can explain values.
    field_provenance: dict[str, str] = Field(default_factory=dict)

    @property
    def providers(self) -> list[str]:
        seen: dict[str, None] = {}
        for ref in self.source_refs:
            seen.setdefault(ref.provider, None)
        return list(seen)


class GeometryFrame(BaseModel):
    """A time-valid geometry belonging to an event, such as one VAA polygon."""

    id: str
    event_id: str
    geometry_type: GeometryType
    frame_kind: FrameKind
    valid_time: datetime
    lead_hours: float | None = None
    lower_altitude_m: float | None = None
    upper_altitude_m: float | None = None
    geometry: dict[str, Any]
    source_provider: str
    source_ref: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class AshMovement(BaseModel):
    direction_degrees: float | None = None
    direction_text: str | None = None
    speed_knots: float | None = None


class AshAltitude(BaseModel):
    bottom_flight_level: int | None = None
    top_flight_level: int | None = None
    bottom_meters: float | None = None
    top_meters: float | None = None


class AshAdvisory(BaseModel):
    """Volcanic ash advisory. Spec section 8.2."""

    advisory_id: str
    event_id: str
    volcano_id: str | None = None
    volcano_name: str | None = None
    issue_time: datetime | None = None
    observation_time: datetime | None = None
    status: str = "ACTIVE"
    source: str = ""
    altitude: AshAltitude = Field(default_factory=AshAltitude)
    movement: AshMovement = Field(default_factory=AshMovement)
    geometry_quality: Quality = Quality.UNAVAILABLE
    raw_bulletin: str = ""
    parser_version: str = ""
    parser_warnings: list[str] = Field(default_factory=list)


class Volcano(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    elevation_m: float | None = None
    aliases: list[str] = Field(default_factory=list)


class WatchArea(BaseModel):
    id: str
    name: str
    geometry: dict[str, Any]
    hazard_types: list[HazardType]
    min_magnitude: float = 4.5
    radius_km: float = 300.0
    enabled: bool = True


class ArrivalEstimate(BaseModel):
    """Always an interval. Spec section 12.2 forbids false precision."""

    estimate: datetime
    earliest: datetime
    latest: datetime
    seconds_from_now: float
    model: str
    quality: Quality = Quality.MODELLED


class ImpactResult(BaseModel):
    event_id: str
    distance_km: float
    hypocentral_distance_km: float | None = None
    p_arrival: ArrivalEstimate | None = None
    s_arrival: ArrivalEstimate | None = None
    already_arrived: bool = False
    ash_intersects: bool = False
    ash_entry_time: datetime | None = None
    ash_exit_time: datetime | None = None
    ash_altitude: AshAltitude | None = None
    # Never presented as an official warning; always labelled as modelled.
    provenance_class: ProvenanceClass = ProvenanceClass.MODEL_ESTIMATE
