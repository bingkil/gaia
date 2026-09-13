"""Ingestion pipeline.

Turns observations into canonical events and decides what is worth notifying.
Runs in a single process; database work is offloaded to threads so the event
loop stays responsive to the EMSC stream.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from ..config import Settings
from ..db import Database, dumps, loads, to_iso, utcnow
from ..domain.enums import (
    AlertType,
    EruptionClassification,
    EventState,
    FrameKind,
    GeometryType,
    HazardType,
    ProvenanceClass,
    Quality,
)
from ..domain.models import (
    AshAdvisory,
    AshAltitude,
    AshMovement,
    GeometryFrame,
    HazardEvent,
    Observation,
)
from ..providers.vaac import parse_vaa
from ..store import (
    AdvisoryRepo,
    EventRepo,
    FrameRepo,
    ObservationRepo,
    VolcanoRepo,
    WatchAreaRepo,
    new_id,
)
from .bus import (
    EVENT_CANCELLED,
    EVENT_CREATED,
    EVENT_UPDATED,
    NOTIFICATION_CREATED,
    EventBus,
)
from .changes import material_changes
from .correlate import best_match
from .fusion import DECISION_VERSION, build_event, diff_events
from .policy import (
    POLICY_VERSION,
    TEMPLATE_VERSION,
    change_bucket,
    compose,
    idempotency_key,
    impact_for_area,
    should_alert,
)
from .volcano import ThermalCluster, classify_thermal, resolve_volcano

log = logging.getLogger(__name__)

# A volcanic event stays open for this long before new activity starts a new one.
VOLCANO_EVENT_WINDOW = timedelta(hours=72)


class Pipeline:
    def __init__(self, db: Database, settings: Settings, bus: EventBus) -> None:
        self.db = db
        self.settings = settings
        self.bus = bus
        self.observations = ObservationRepo(db)
        self.events = EventRepo(db)
        self.frames = FrameRepo(db)
        self.advisories = AdvisoryRepo(db)
        self.volcanoes = VolcanoRepo(db)
        self.watch_areas = WatchAreaRepo(db)
        self._volcano_cache: list | None = None

    def volcano_catalogue(self) -> list:
        if self._volcano_cache is None:
            self._volcano_cache = self.volcanoes.all()
        return self._volcano_cache

    async def handle_observation(self, observation: Observation) -> HazardEvent | None:
        try:
            result = await self._process(observation)
        except Exception:
            log.exception("pipeline failed for observation %s", observation.message_id)
            return None

        if result is None:
            return None

        event, previous, changes = result
        await self._publish(event, previous, changes)

        # Replay rebuilds history; it must not re-send notifications.
        if not self.bus.replay_mode:
            await self._evaluate_notifications(event, previous, changes)
        return event

    async def _process(
        self, observation: Observation
    ) -> tuple[HazardEvent, HazardEvent | None, dict[str, Any]] | None:
        return await asyncio.to_thread(self._process_sync, observation)

    def _process_sync(
        self, observation: Observation
    ) -> tuple[HazardEvent, HazardEvent | None, dict[str, Any]] | None:
        if observation.normalized.get("kind") == "THERMAL_ANOMALY":
            return self._process_thermal(observation)

        if observation.hazard_type == HazardType.EARTHQUAKE:
            return self._process_earthquake(observation)
        return self._process_volcano(observation)

    def _process_earthquake(
        self, observation: Observation
    ) -> tuple[HazardEvent, HazardEvent | None, dict[str, Any]] | None:
        if observation.observed_at is None:
            return None

        existing = self.events.find_by_source(observation.provider, observation.source_id)
        score, reasons = 1.0, ["PROVIDER_ID_MATCH"]

        if existing is None:
            candidates = self.events.candidates(
                HazardType.EARTHQUAKE,
                observation.observed_at,
                self.settings.correlation.max_time_delta_seconds,
            )
            match = best_match(observation, candidates, self.settings.correlation)
            existing, score, reasons = match.event, match.score, match.reasons

        previous = existing
        event_id = existing.id if existing else new_id("evt")

        linked = self.observations.for_event(event_id) if existing else []
        if observation.message_id not in {o.message_id for o in linked}:
            linked.append(observation)

        event, changes = build_event(
            event_id, HazardType.EARTHQUAKE, linked, previous
        )
        # The event row must exist before the link row references it.
        self.events.save(event, changes, DECISION_VERSION)
        self.events.link(event_id, observation.message_id, score, reasons)
        return event, previous, changes

    def _process_volcano(
        self, observation: Observation
    ) -> tuple[HazardEvent, HazardEvent | None, dict[str, Any]] | None:
        existing = self.events.find_by_source(observation.provider, observation.source_id)

        if existing is None and observation.longitude is not None:
            match = resolve_volcano(
                self.volcano_catalogue(),
                name=observation.normalized.get("volcano_name"),
                longitude=observation.longitude,
                latitude=observation.latitude,
            )
            if match:
                existing = self._open_volcano_event(match.volcano.id)

        previous = existing
        event_id = existing.id if existing else new_id("evt")

        linked = self.observations.for_event(event_id) if existing else []
        if observation.message_id not in {o.message_id for o in linked}:
            linked.append(observation)

        event, changes = build_event(event_id, HazardType.VOLCANO, linked, previous)
        self.events.save(event, changes, DECISION_VERSION)
        self.events.link(event_id, observation.message_id, 1.0, ["VOLCANO_IDENTITY"])
        return event, previous, changes

    def _process_thermal(
        self, observation: Observation
    ) -> tuple[HazardEvent, HazardEvent | None, dict[str, Any]] | None:
        """A thermal detection only matters once tied to a catalogued volcano."""
        match = resolve_volcano(
            self.volcano_catalogue(),
            longitude=observation.longitude,
            latitude=observation.latitude,
            radius_km=self.settings.providers.firms.volcano_radius_km,
        )
        if match is None:
            return None

        volcano = match.volcano
        self.db.execute(
            """INSERT OR REPLACE INTO thermal_anomaly
               (id, observation_id, volcano_id, acquired_at, latitude, longitude,
                instrument, satellite, confidence_category, frp, daynight,
                distance_km, classification)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                new_id("thermal"),
                observation.message_id,
                volcano.id,
                to_iso(observation.observed_at),
                observation.latitude,
                observation.longitude,
                observation.normalized.get("instrument"),
                observation.normalized.get("satellite"),
                observation.normalized.get("confidence_category"),
                observation.normalized.get("frp"),
                observation.normalized.get("daynight"),
                match.distance_km,
                EruptionClassification.AUTOMATED_SIGNAL.value,
            ),
        )

        cluster = self._thermal_cluster(volcano.id, match.distance_km)
        existing = self._open_volcano_event(volcano.id)
        classification, reasons = classify_thermal(
            cluster,
            has_official_event=existing is not None
            and "GDACS" in existing.providers,
            has_ash_advisory=existing is not None and existing.hazard_type == HazardType.ASH,
        )

        # A lone pixel is recorded but never creates a public event.
        if classification == EruptionClassification.AUTOMATED_SIGNAL and existing is None:
            return None

        previous = existing
        event_id = existing.id if existing else new_id("evt")

        linked = self.observations.for_event(event_id) if existing else []
        if observation.message_id not in {o.message_id for o in linked}:
            linked.append(observation)

        event, changes = build_event(event_id, HazardType.VOLCANO, linked, previous)
        if event.summary.volcano_name is None:
            event.summary.volcano_name = volcano.name
            event.summary.place = event.summary.place or volcano.country
        self.events.save(event, changes, DECISION_VERSION)
        self.events.link(event_id, observation.message_id, 0.6, reasons)
        return event, previous, changes

    def _thermal_cluster(self, volcano_id: str, nearest_km: float) -> ThermalCluster:
        since = to_iso(utcnow() - timedelta(hours=24))
        rows = self.db.query(
            """SELECT satellite, frp, distance_km FROM thermal_anomaly
               WHERE volcano_id=? AND acquired_at >= ?""",
            (volcano_id, since),
        )
        return ThermalCluster(
            volcano_id=volcano_id,
            detection_count=len(rows),
            distinct_satellites=len({r["satellite"] for r in rows if r["satellite"]}),
            max_frp=max((r["frp"] or 0.0 for r in rows), default=0.0),
            nearest_km=min((r["distance_km"] or nearest_km for r in rows), default=nearest_km),
        )

    def _open_volcano_event(self, volcano_id: str) -> HazardEvent | None:
        """Find an event already tracking this volcano within the open window."""
        since = to_iso(utcnow() - VOLCANO_EVENT_WINDOW)
        rows = self.db.query(
            """SELECT current_payload FROM hazard_event
               WHERE hazard_type IN ('VOLCANO','ASH')
                 AND state != 'RETRACTED'
                 AND last_updated_at >= ?
               ORDER BY last_updated_at DESC""",
            (since,),
        )

        for row in rows:
            event = HazardEvent.model_validate(loads(row["current_payload"], {}))
            if event.summary.volcano_id == volcano_id:
                return event

            match = resolve_volcano(
                self.volcano_catalogue(),
                name=event.summary.volcano_name,
                longitude=event.longitude,
                latitude=event.latitude,
            )
            if match and match.volcano.id == volcano_id:
                return event
        return None

    async def ingest_vaa_bulletin(self, text: str, source: str = "MANUAL") -> HazardEvent | None:
        """Parse a VAA bulletin into an ash event with time-valid frames."""
        return await asyncio.to_thread(self._ingest_vaa_sync, text, source)

    def _ingest_vaa_sync(self, text: str, source: str) -> HazardEvent | None:
        parsed = parse_vaa(text)
        if parsed["issue_time"] is None and not parsed["frames"]:
            log.warning("VAA bulletin unusable: %s", parsed["warnings"])
            return None

        match = resolve_volcano(
            self.volcano_catalogue(),
            name=parsed.get("volcano_name"),
            longitude=parsed.get("longitude"),
            latitude=parsed.get("latitude"),
        )
        volcano_id = match.volcano.id if match else None

        existing = self._open_volcano_event(volcano_id) if volcano_id else None
        previous = existing
        event_id = existing.id if existing else new_id("evt")

        issue_time = parsed["issue_time"] or utcnow()
        advisory_number = parsed.get("advisory_number") or issue_time.strftime("%Y%m%d%H%M")
        vaac = parsed.get("vaac") or source

        # Frames carry no geometry when the bulletin could not be read; the
        # advisory is still recorded with its raw text.
        frames: list[GeometryFrame] = []
        for item in parsed["frames"]:
            valid_time = item["valid_time"] or issue_time + timedelta(
                hours=item["lead_hours"] or 0
            )
            frames.append(
                GeometryFrame(
                    id=new_id("frame"),
                    event_id=event_id,
                    geometry_type=GeometryType.ASH_CLOUD,
                    frame_kind=FrameKind(item["kind"]),
                    valid_time=valid_time,
                    lead_hours=item["lead_hours"],
                    lower_altitude_m=_fl_to_m(item["bottom_flight_level"]),
                    upper_altitude_m=_fl_to_m(item["top_flight_level"]),
                    geometry=item["geometry"],
                    source_provider=vaac,
                    source_ref=advisory_number,
                    properties={
                        "bottomFlightLevel": item["bottom_flight_level"],
                        "topFlightLevel": item["top_flight_level"],
                    },
                )
            )

        longitude = parsed.get("longitude")
        latitude = parsed.get("latitude")
        if longitude is None and match:
            longitude, latitude = match.volcano.longitude, match.volcano.latitude

        event = HazardEvent(
            id=event_id,
            hazard_type=HazardType.ASH,
            state=previous.state if previous else "PRELIMINARY",
            provenance_class=ProvenanceClass.AUTHORITATIVE_NOTICE,
            quality=Quality.OFFICIAL_ADVISORY if frames else Quality.UNAVAILABLE,
            origin_time=parsed.get("observation_time") or issue_time,
            first_observed_at=parsed.get("observation_time") or issue_time,
            first_ingested_at=previous.first_ingested_at if previous else utcnow(),
            last_updated_at=utcnow(),
            revision=(previous.revision + 1) if previous else 1,
            longitude=longitude,
            latitude=latitude,
            confidence=0.95 if frames else 0.6,
            confidence_reasons=["OFFICIAL_VAA_BULLETIN"],
            source_refs=previous.source_refs if previous else [],
        )
        event.summary.volcano_id = volcano_id
        event.summary.volcano_name = parsed.get("volcano_name")
        event.summary.place = parsed.get("area")
        event.summary.alert_level = parsed.get("colour_code")

        changes = diff_events(previous, event)
        self.events.save(event, changes, DECISION_VERSION)

        if frames:
            self.frames.replace_for_event(event_id, frames)

        self.advisories.save(
            AshAdvisory(
                advisory_id=f"{vaac}_{advisory_number}".replace("/", "_"),
                event_id=event_id,
                volcano_id=volcano_id,
                volcano_name=parsed.get("volcano_name"),
                issue_time=issue_time,
                observation_time=parsed.get("observation_time"),
                status=parsed["status"],
                source=vaac,
                altitude=AshAltitude(
                    bottom_flight_level=parsed.get("bottom_flight_level"),
                    top_flight_level=parsed.get("top_flight_level"),
                    bottom_meters=parsed.get("bottom_metres"),
                    top_meters=parsed.get("top_metres"),
                ),
                movement=AshMovement(**parsed.get("movement", {})),
                geometry_quality=Quality.OFFICIAL_ADVISORY if frames else Quality.UNAVAILABLE,
                raw_bulletin=parsed["raw_text"],
                parser_version=parsed["parser_version"],
                parser_warnings=parsed["warnings"],
            )
        )
        return event

    async def _publish(
        self, event: HazardEvent, previous: HazardEvent | None, changes: dict[str, Any]
    ) -> None:
        subject = EVENT_CREATED if previous is None else EVENT_UPDATED
        if event.state == EventState.RETRACTED:
            subject = EVENT_CANCELLED

        await self.bus.publish(
            subject,
            {
                "eventId": event.id,
                "revision": event.revision,
                "changedFields": sorted(changes.keys()),
                "event": event.model_dump(mode="json"),
            },
        )

    async def _evaluate_notifications(
        self, event: HazardEvent, previous: HazardEvent | None, changes: dict[str, Any]
    ) -> None:
        alert_type, reasons = material_changes(previous, event, self.settings.alerts)
        if alert_type is None:
            return

        notifications = await asyncio.to_thread(
            self._decide_notifications, event, alert_type, reasons
        )
        for notification in notifications:
            await self.bus.publish(NOTIFICATION_CREATED, notification)

    def _decide_notifications(
        self, event: HazardEvent, alert_type: AlertType, reasons: list[str]
    ) -> list[dict[str, Any]]:
        created: list[dict[str, Any]] = []
        frames = (
            self.frames.for_event(event.id)
            if event.hazard_type != HazardType.EARTHQUAKE
            else []
        )

        for area in self.watch_areas.all(enabled_only=True):
            impact = impact_for_area(event, area, frames, self.settings.seismic_model)
            allowed, decision_reasons = should_alert(
                event, area, impact, alert_type, self.settings.alerts
            )
            all_reasons = reasons + decision_reasons
            decision_id = new_id("decision")

            try:
                self.db.execute(
                    """INSERT INTO alert_decision
                       (id, event_id, event_revision, watch_area_id, policy_version,
                        alert_type, decision, reason_codes, computed_impact, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        decision_id,
                        event.id,
                        event.revision,
                        area.id,
                        POLICY_VERSION,
                        alert_type.value,
                        "SEND" if allowed else "SUPPRESS",
                        dumps(all_reasons),
                        dumps(impact.model_dump(mode="json") if impact else {}),
                        to_iso(utcnow()),
                    ),
                )
            except Exception:
                # The unique constraint means this revision was already decided.
                continue

            if not allowed:
                continue

            key = idempotency_key(event.id, alert_type, area.id, change_bucket(all_reasons))
            title, body = compose(
                event, area, impact, alert_type, self.settings.seismic_model
            )
            notification_id = new_id("notif")

            try:
                self.db.execute(
                    """INSERT INTO notification
                       (id, alert_decision_id, event_id, alert_type, title, body,
                        template_version, idempotency_key, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        notification_id,
                        decision_id,
                        event.id,
                        alert_type.value,
                        title,
                        body,
                        TEMPLATE_VERSION,
                        key,
                        to_iso(utcnow()),
                    ),
                )
            except Exception:
                # Duplicate idempotency key: this alert was already delivered.
                continue

            created.append(
                {
                    "id": notification_id,
                    "eventId": event.id,
                    "alertType": alert_type.value,
                    "title": title,
                    "body": body,
                    "watchAreaId": area.id,
                    "watchAreaName": area.name,
                    "hazardType": event.hazard_type.value,
                    "provenanceClass": event.provenance_class.value,
                    "createdAt": to_iso(utcnow()),
                    "impact": impact.model_dump(mode="json") if impact else None,
                }
            )
        return created


def _fl_to_m(flight_level: int | None) -> float | None:
    return None if flight_level is None else flight_level * 100 * 0.3048
