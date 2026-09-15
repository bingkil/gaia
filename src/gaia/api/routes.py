"""HTTP API.

Every safety-relevant response carries provenance and data freshness so the
client never has to infer them. Spec section 15.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..db import from_iso, to_iso, utcnow
from ..domain.enums import (
    HAZARD_PROVENANCE_LABELS,
    PROVENANCE_LABELS,
    EventState,
    HazardType,
    ProviderHealth,
    label_for,
)
from ..domain.geo import circle_geojson, point_geojson
from ..domain.models import HazardEvent, WatchArea
from ..engine.impact import ash_impact, earthquake_impact
from ..logbuffer import BUFFER
from ..providers import ADAPTERS, StreamingAdapter
from ..runtime import MANUAL_POLL_MIN_SECONDS, Runtime
from ..store import (
    AdvisoryRepo,
    EventRepo,
    FrameRepo,
    ObservationRepo,
    WatchAreaRepo,
    new_id,
)

router = APIRouter(prefix="/v1")


def runtime_of(request: Request) -> Runtime:
    return request.app.state.runtime


def _data_age(event: HazardEvent) -> float | None:
    if event.last_updated_at is None:
        return None
    return round((utcnow() - event.last_updated_at).total_seconds(), 1)


def time_range(
    runtime: Runtime,
    since_hours: float | None,
    since: str | None,
    until: str | None,
) -> tuple[datetime, datetime | None]:
    """Resolve the window shared by the list and the map, so they cannot drift."""
    if since is not None:
        parsed = from_iso(since)
        if parsed is None:
            raise HTTPException(400, "since must be an ISO timestamp")
        start = parsed
    else:
        hours = since_hours if since_hours is not None else runtime.settings.active_window_hours
        start = utcnow() - timedelta(hours=hours)

    end = None
    if until is not None:
        end = from_iso(until)
        if end is None:
            raise HTTPException(400, "until must be an ISO timestamp")
        if end < start:
            raise HTTPException(400, "until must not precede since")

    return start, end


def event_payload(event: HazardEvent) -> dict[str, Any]:
    data = event.model_dump(mode="json")
    data["label"] = label_for(event.provenance_class, event.hazard_type)
    data["dataAgeSeconds"] = _data_age(event)
    data["providers"] = event.providers
    return data


@router.get("/meta")
async def meta(request: Request) -> dict[str, Any]:
    """Model versions, labels, and attribution the client must display."""
    runtime = runtime_of(request)
    providers = runtime.settings.providers
    return {
        "app": "GAIA",
        "subtitle": "Geohazard Awareness, Impact & Alerting",
        "seismicModel": runtime.settings.seismic_model.model_dump(),
        "provenanceLabels": {k.value: v for k, v in PROVENANCE_LABELS.items()},
        "hazardProvenanceLabels": {
            f"{hazard.value}:{provenance.value}": text
            for (hazard, provenance), text in HAZARD_PROVENANCE_LABELS.items()
        },
        "activeWindowHours": runtime.settings.active_window_hours,
        "attribution": [
            providers.emsc.attribution,
            providers.usgs.attribution,
            providers.geofon.attribution,
            providers.gdacs.attribution,
            providers.firms.attribution,
        ],
        "disclaimer": (
            "GAIA is not an earthquake early warning system. Arrival times are "
            "modelled estimates. Follow local authority instructions."
        ),
    }


@router.get("/events")
async def list_events(
    request: Request,
    hazardType: str | None = None,
    state: str | None = None,
    bbox: str | None = None,
    minMagnitude: float | None = None,
    sinceHours: float | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = Query(500, le=2000),
) -> dict[str, Any]:
    runtime = runtime_of(request)
    repo = EventRepo(runtime.db)

    hazards = [HazardType(h) for h in hazardType.split(",")] if hazardType else None
    states = [EventState(s) for s in state.split(",")] if state else None
    since_at, until_at = time_range(runtime, sinceHours, since, until)

    box = None
    if bbox:
        parts = [float(p) for p in bbox.split(",")]
        if len(parts) != 4:
            raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat")
        box = (parts[0], parts[1], parts[2], parts[3])

    events = repo.list_events(
        hazard_types=hazards,
        states=states,
        since=since_at,
        until=until_at,
        bbox=box,
        min_magnitude=minMagnitude,
        limit=limit,
    )
    return {
        "events": [event_payload(e) for e in events],
        "generatedAt": to_iso(utcnow()),
        "count": len(events),
    }


@router.get("/events/{event_id}")
async def get_event(request: Request, event_id: str) -> dict[str, Any]:
    runtime = runtime_of(request)
    event = EventRepo(runtime.db).get(event_id)
    if event is None:
        raise HTTPException(404, "event not found")

    payload = event_payload(event)
    payload["frames"] = [
        f.model_dump(mode="json") for f in FrameRepo(runtime.db).for_event(event_id)
    ]
    payload["advisories"] = AdvisoryRepo(runtime.db).for_event(event_id)
    return payload


@router.get("/events/{event_id}/revisions")
async def event_revisions(request: Request, event_id: str) -> dict[str, Any]:
    runtime = runtime_of(request)
    return {"eventId": event_id, "revisions": EventRepo(runtime.db).revisions(event_id)}


@router.get("/events/{event_id}/observations")
async def event_observations(request: Request, event_id: str) -> dict[str, Any]:
    """Raw source observations behind the canonical event."""
    runtime = runtime_of(request)
    observations = ObservationRepo(runtime.db).for_event(event_id)
    return {
        "eventId": event_id,
        "observations": [
            {
                **o.model_dump(mode="json"),
                "rawAvailable": runtime.raw.get(o.raw_object_key) is not None,
            }
            for o in observations
        ],
    }


@router.get("/events/{event_id}/raw/{observation_id}")
async def raw_payload(request: Request, event_id: str, observation_id: str) -> dict[str, Any]:
    runtime = runtime_of(request)
    observation = ObservationRepo(runtime.db).get(observation_id)
    if observation is None:
        raise HTTPException(404, "observation not found")

    payload = runtime.raw.get(observation.raw_object_key)
    if payload is None:
        raise HTTPException(404, "raw payload not retained")

    return {
        "observationId": observation_id,
        "provider": observation.provider,
        "objectKey": observation.raw_object_key,
        "sha256": observation.raw_sha256,
        "payload": payload.decode("utf-8", errors="replace")[:200_000],
    }


@router.get("/map/events.geojson")
async def map_events(
    request: Request,
    hazardType: str | None = None,
    minMagnitude: float | None = None,
    sinceHours: float | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    runtime = runtime_of(request)
    hazards = [HazardType(h) for h in hazardType.split(",")] if hazardType else None
    since_at, until_at = time_range(runtime, sinceHours, since, until)

    events = EventRepo(runtime.db).list_events(
        hazard_types=hazards,
        since=since_at,
        until=until_at,
        min_magnitude=minMagnitude,
        limit=2000,
    )

    features = []
    for event in events:
        if event.longitude is None or event.latitude is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": point_geojson(event.longitude, event.latitude),
                "properties": {
                    "eventId": event.id,
                    "hazardType": event.hazard_type.value,
                    "state": event.state.value,
                    "provenanceClass": event.provenance_class.value,
                    "label": label_for(event.provenance_class, event.hazard_type),
                    "quality": event.quality.value,
                    "magnitude": event.summary.magnitude,
                    "depthKm": event.summary.depth_km,
                    "place": event.summary.place,
                    "volcanoName": event.summary.volcano_name,
                    "alertLevel": event.summary.alert_level,
                    "tsunami": event.summary.tsunami,
                    "detectionCount": event.summary.detection_count,
                    "maxFrpMw": event.summary.max_frp_mw,
                    "originTime": to_iso(event.origin_time),
                    "originTimeMs": (
                        event.origin_time.timestamp() * 1000 if event.origin_time else None
                    ),
                    "lastUpdatedAt": to_iso(event.last_updated_at),
                    "dataAgeSeconds": _data_age(event),
                    "confidence": event.confidence,
                    "providers": event.providers,
                    "revision": event.revision,
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "generatedAt": to_iso(utcnow()),
    }


@router.get("/map/frames.geojson")
async def map_frames(request: Request, eventId: str | None = None) -> dict[str, Any]:
    """Time-valid ash geometry. The client selects frames using the map clock."""
    runtime = runtime_of(request)
    repo = FrameRepo(runtime.db)
    frames = repo.for_event(eventId) if eventId else repo.all_frames()

    features = []
    for frame in frames:
        features.append(
            {
                "type": "Feature",
                "geometry": frame.geometry,
                "properties": {
                    "frameId": frame.id,
                    "eventId": frame.event_id,
                    "geometryType": frame.geometry_type.value,
                    "frameKind": frame.frame_kind.value,
                    "validTime": to_iso(frame.valid_time),
                    "validTimeMs": frame.valid_time.timestamp() * 1000,
                    "leadHours": frame.lead_hours,
                    "lowerAltitudeM": frame.lower_altitude_m,
                    "upperAltitudeM": frame.upper_altitude_m,
                    "source": frame.source_provider,
                    "sourceRef": frame.source_ref,
                    "styleClass": (
                        "ash-observed" if frame.frame_kind.value == "OBSERVED" else "ash-forecast"
                    ),
                    **frame.properties,
                },
            }
        )

    return {"type": "FeatureCollection", "features": features}


class ImpactRequest(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    eventId: str | None = None
    radiusKm: float = Field(default=0.0, ge=0, le=1000)


@router.post("/impact/point")
async def impact_point(request: Request, body: ImpactRequest) -> dict[str, Any]:
    """Distance and modelled arrival for a location. Never an official warning."""
    runtime = runtime_of(request)
    repo = EventRepo(runtime.db)
    frames_repo = FrameRepo(runtime.db)

    if body.eventId:
        event = repo.get(body.eventId)
        if event is None:
            raise HTTPException(404, "event not found")
        events = [event]
    else:
        since = utcnow() - timedelta(hours=runtime.settings.active_window_hours)
        events = repo.list_events(since=since, limit=200)

    geometry = (
        circle_geojson(body.longitude, body.latitude, body.radiusKm)
        if body.radiusKm > 0
        else point_geojson(body.longitude, body.latitude)
    )

    results = []
    for event in events:
        if event.hazard_type == HazardType.EARTHQUAKE:
            impact = earthquake_impact(
                event, body.longitude, body.latitude, runtime.settings.seismic_model
            )
        else:
            impact = ash_impact(event, frames_repo.for_event(event.id), geometry)

        if impact is None:
            continue
        results.append(
            {
                **impact.model_dump(mode="json"),
                "hazardType": event.hazard_type.value,
                "label": label_for(event.provenance_class, event.hazard_type),
                "magnitude": event.summary.magnitude,
                "place": event.summary.place,
            }
        )

    results.sort(key=lambda r: r["distance_km"])
    return {
        "location": {"longitude": body.longitude, "latitude": body.latitude},
        "results": results[:50],
        "model": runtime.settings.seismic_model.model_dump(),
        "note": "Modelled estimate. Not an official warning.",
    }


@router.get("/volcanoes")
async def volcanoes(request: Request) -> dict[str, Any]:
    runtime = runtime_of(request)
    return {"volcanoes": [v.model_dump() for v in runtime.volcanoes.all()]}


class WatchAreaRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    radiusKm: float = Field(default=300.0, gt=0, le=2000)
    hazardTypes: list[HazardType] = Field(
        default_factory=lambda: [HazardType.EARTHQUAKE, HazardType.VOLCANO, HazardType.ASH]
    )
    minMagnitude: float = Field(default=4.5, ge=0, le=10)


@router.get("/watch-areas")
async def list_watch_areas(request: Request) -> dict[str, Any]:
    runtime = runtime_of(request)
    areas = WatchAreaRepo(runtime.db).all()
    return {"watchAreas": [a.model_dump(mode="json") for a in areas]}


@router.post("/watch-areas", status_code=201)
async def create_watch_area(request: Request, body: WatchAreaRequest) -> dict[str, Any]:
    runtime = runtime_of(request)
    area = WatchArea(
        id=new_id("watch"),
        name=body.name,
        geometry=circle_geojson(body.longitude, body.latitude, body.radiusKm),
        hazard_types=body.hazardTypes,
        min_magnitude=body.minMagnitude,
        radius_km=body.radiusKm,
    )
    WatchAreaRepo(runtime.db).save(area)
    return area.model_dump(mode="json")


@router.put("/watch-areas/{area_id}")
async def update_watch_area(
    request: Request, area_id: str, body: WatchAreaRequest
) -> dict[str, Any]:
    runtime = runtime_of(request)
    repo = WatchAreaRepo(runtime.db)
    if repo.get(area_id) is None:
        raise HTTPException(404, "watch area not found")

    area = WatchArea(
        id=area_id,
        name=body.name,
        geometry=circle_geojson(body.longitude, body.latitude, body.radiusKm),
        hazard_types=body.hazardTypes,
        min_magnitude=body.minMagnitude,
        radius_km=body.radiusKm,
    )
    repo.save(area)
    return area.model_dump(mode="json")


@router.delete("/watch-areas/{area_id}", status_code=204)
async def delete_watch_area(request: Request, area_id: str) -> None:
    WatchAreaRepo(runtime_of(request).db).delete(area_id)


@router.get("/notifications")
async def notifications(request: Request, limit: int = Query(50, le=200)) -> dict[str, Any]:
    runtime = runtime_of(request)
    rows = runtime.db.query(
        """SELECT n.*, d.reason_codes, d.computed_impact, d.watch_area_id
           FROM notification n
           JOIN alert_decision d ON d.id = n.alert_decision_id
           ORDER BY n.created_at DESC LIMIT ?""",
        (limit,),
    )
    from ..db import loads

    return {
        "notifications": [
            {
                "id": r["id"],
                "eventId": r["event_id"],
                "alertType": r["alert_type"],
                "title": r["title"],
                "body": r["body"],
                "createdAt": r["created_at"],
                "readAt": r["read_at"],
                "watchAreaId": r["watch_area_id"],
                "reasonCodes": loads(r["reason_codes"], []),
                "impact": loads(r["computed_impact"], {}),
            }
            for r in rows
        ]
    }


@router.post("/notifications/{notification_id}/read", status_code=204)
async def mark_read(request: Request, notification_id: str) -> None:
    runtime = runtime_of(request)
    runtime.db.execute(
        "UPDATE notification SET read_at=? WHERE id=?", (to_iso(utcnow()), notification_id)
    )


@router.get("/alert-decisions/{event_id}")
async def alert_decisions(request: Request, event_id: str) -> dict[str, Any]:
    """Explains why an event did or did not notify. Spec section 14.8."""
    runtime = runtime_of(request)
    rows = runtime.db.query(
        """SELECT * FROM alert_decision WHERE event_id=?
           ORDER BY event_revision DESC""",
        (event_id,),
    )
    from ..db import loads

    return {
        "eventId": event_id,
        "decisions": [
            {
                "revision": r["event_revision"],
                "watchAreaId": r["watch_area_id"],
                "alertType": r["alert_type"],
                "decision": r["decision"],
                "reasonCodes": loads(r["reason_codes"], []),
                "impact": loads(r["computed_impact"], {}),
                "policyVersion": r["policy_version"],
                "createdAt": r["created_at"],
            }
            for r in rows
        ],
    }


@router.get("/provider-health")
async def provider_health(request: Request) -> dict[str, Any]:
    """A healthy process does not imply healthy data. Spec section 19.4."""
    runtime = runtime_of(request)
    now = utcnow()
    records = []

    for row in runtime.health.all():
        key = row["provider"].lower()
        provider_settings = getattr(runtime.settings.providers, key, None)
        stale_after = getattr(provider_settings, "stale_after_seconds", 900.0)

        last_message = from_iso(row["last_message_at"]) or from_iso(row["last_success_at"])
        age = (now - last_message).total_seconds() if last_message else None

        state = row["state"]
        if state != ProviderHealth.DISABLED.value and age is not None and age > stale_after:
            state = ProviderHealth.STALE.value

        records.append(
            {
                "provider": row["provider"],
                "state": state,
                "lastMessageAgeSeconds": round(age, 1) if age is not None else None,
                "staleAfterSeconds": stale_after,
                "consecutiveErrors": row["consecutive_errors"],
                "messagesTotal": row["messages_total"],
                "lastError": row["last_error"],
                "attribution": getattr(provider_settings, "attribution", None),
            }
        )

    return {"providers": records, "generatedAt": to_iso(now)}


@router.post("/ingest/vaa")
async def ingest_vaa(
    request: Request, bulletin: str = Body(..., embed=True, max_length=50_000)
) -> dict[str, Any]:
    """Ingest a VAA bulletin pasted from a VAAC.

    No free VAAC endpoint contract is assumed here; the bulletin text is the
    stable interface. Parse warnings are returned rather than hidden.
    """
    runtime = runtime_of(request)
    event = await runtime.pipeline.ingest_vaa_bulletin(bulletin)
    if event is None:
        raise HTTPException(422, "bulletin could not be interpreted as an advisory")

    frames = FrameRepo(runtime.db).for_event(event.id)
    advisories = AdvisoryRepo(runtime.db).for_event(event.id)
    return {
        "event": event_payload(event),
        "frameCount": len(frames),
        "parserWarnings": advisories[0]["parserWarnings"] if advisories else [],
    }


@router.post("/providers/refresh")
async def refresh_providers(
    request: Request, provider: str | None = Body(None, embed=True)
) -> dict[str, Any]:
    """Ask the pollers to fetch now instead of waiting for their next tick."""
    results = runtime_of(request).refresh(provider)
    return {"results": results, "requestedAt": to_iso(utcnow())}


@router.get("/settings")
async def read_settings(request: Request) -> dict[str, Any]:
    """Expose the effective ingestion configuration and how to change it.

    Read-only on purpose: cadence belongs to the process that owns the
    connections, and a value edited here would not survive a restart.
    """
    runtime = runtime_of(request)
    providers = []

    for key, adapter_class in ADAPTERS.items():
        provider_settings = getattr(runtime.settings.providers, key)
        streaming = issubclass(adapter_class, StreamingAdapter)
        providers.append(
            {
                "provider": adapter_class.name,
                "key": key,
                "enabled": provider_settings.enabled,
                "mode": "STREAM" if streaming else "POLL",
                # A stream has no cadence, and reporting the inherited default
                # would read as one.
                "pollSeconds": None
                if streaming
                else getattr(provider_settings, "poll_seconds", None),
                "staleAfterSeconds": provider_settings.stale_after_seconds,
                "envPrefix": f"GAIA_PROVIDERS__{key.upper()}__",
                "attribution": getattr(provider_settings, "attribution", None),
            }
        )

    return {
        "providers": providers,
        "ingestEnabled": runtime.settings.ingest_enabled,
        "manualPollMinSeconds": MANUAL_POLL_MIN_SECONDS,
        "dataDir": str(runtime.settings.data_dir),
        "firmsKey": runtime.firms_key_status(),
    }


@router.put("/settings/firms-key")
async def set_firms_key(request: Request, mapKey: str = Body(..., embed=True)) -> dict[str, Any]:
    """Store the NASA FIRMS key. The value is never read back out."""
    key = mapKey.strip()
    if not key:
        raise HTTPException(422, "map key is empty")
    if len(key) > 128 or not key.isalnum():
        raise HTTPException(422, "map key should be alphanumeric")

    runtime = runtime_of(request)
    status = await runtime.set_firms_key(key)
    runtime.refresh("FIRMS")
    return status


@router.delete("/settings/firms-key")
async def clear_firms_key(request: Request) -> dict[str, Any]:
    return await runtime_of(request).clear_firms_key()


@router.get("/status")
async def status(request: Request) -> dict[str, Any]:
    return runtime_of(request).status()


@router.get("/logs")
async def logs(
    limit: int = Query(200, le=500),
    level: str = Query("INFO"),
) -> dict[str, Any]:
    """Recent log lines from this process, however it was launched.

    Backed by an in-memory ring buffer rather than a file, so it works the
    same whether GAIA is running under `uv run`, as a packaged executable, or
    anywhere else that gives no guaranteed place to tail a log file.
    """
    min_level = logging.getLevelName(level.upper())
    if not isinstance(min_level, int):
        raise HTTPException(422, f"unknown log level: {level}")

    records = BUFFER.tail(limit=limit, min_level=min_level)
    return {"logs": records, "generatedAt": to_iso(utcnow())}
