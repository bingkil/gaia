"""Repositories.

Observations and revisions are append-only; ``hazard_event`` is the
materialised current state that can always be rebuilt from them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from ..db import Database, dumps, from_iso, loads, to_iso, utcnow
from ..domain.enums import (
    EventState,
    FrameKind,
    GeometryType,
    HazardType,
    ProvenanceClass,
    Quality,
)
from ..domain.geo import bbox_of
from ..domain.models import (
    AshAdvisory,
    EventSummary,
    GeometryFrame,
    HazardEvent,
    Observation,
    SourceRef,
    Volcano,
    WatchArea,
)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class ObservationRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, obs: Observation) -> bool:
        """Returns False when this exact provider revision was already stored."""
        existing = self.db.query_one(
            "SELECT id FROM source_observation WHERE provider=? AND source_id=? "
            "AND source_revision=?",
            (obs.provider, obs.source_id, obs.source_revision),
        )
        if existing:
            return False
        self.db.execute(
            """INSERT INTO source_observation
               (id, provider, source_id, source_revision, hazard_type, action,
                source_issued_at, observed_at, ingested_at, parser_version,
                raw_object_key, raw_sha256, normalized_payload, validation_warnings)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                obs.message_id,
                obs.provider,
                obs.source_id,
                obs.source_revision,
                obs.hazard_type.value,
                obs.action.value,
                to_iso(obs.source_issued_at),
                to_iso(obs.observed_at),
                to_iso(obs.ingested_at),
                obs.parser_version,
                obs.raw_object_key,
                obs.raw_sha256,
                dumps(obs.normalized),
                dumps(obs.validation_warnings),
            ),
        )
        return True

    def get(self, observation_id: str) -> Observation | None:
        row = self.db.query_one("SELECT * FROM source_observation WHERE id=?", (observation_id,))
        return _row_to_observation(row) if row else None

    def for_event(self, event_id: str) -> list[Observation]:
        rows = self.db.query(
            """SELECT o.* FROM source_observation o
               JOIN event_source_link l ON l.observation_id = o.id
               WHERE l.event_id = ?
               ORDER BY o.ingested_at ASC""",
            (event_id,),
        )
        return [_row_to_observation(r) for r in rows]

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM source_observation")
        return int(row["n"]) if row else 0


class EventRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, event: HazardEvent, change_set: dict[str, Any], decision_version: str) -> None:
        payload = event.model_dump(mode="json")
        self.db.execute(
            """INSERT INTO hazard_event
               (id, hazard_type, state, provenance_class, quality, origin_time,
                first_observed_at, first_ingested_at, last_updated_at, revision,
                longitude, latitude, magnitude, magnitude_type, depth_km,
                confidence, current_payload)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                 state=excluded.state,
                 provenance_class=excluded.provenance_class,
                 quality=excluded.quality,
                 origin_time=excluded.origin_time,
                 last_updated_at=excluded.last_updated_at,
                 revision=excluded.revision,
                 longitude=excluded.longitude,
                 latitude=excluded.latitude,
                 magnitude=excluded.magnitude,
                 magnitude_type=excluded.magnitude_type,
                 depth_km=excluded.depth_km,
                 confidence=excluded.confidence,
                 current_payload=excluded.current_payload""",
            (
                event.id,
                event.hazard_type.value,
                event.state.value,
                event.provenance_class.value,
                event.quality.value,
                to_iso(event.origin_time),
                to_iso(event.first_observed_at),
                to_iso(event.first_ingested_at),
                to_iso(event.last_updated_at),
                event.revision,
                event.longitude,
                event.latitude,
                event.summary.magnitude,
                event.summary.magnitude_type,
                event.summary.depth_km,
                event.confidence,
                dumps(payload),
            ),
        )
        self.db.execute(
            """INSERT OR IGNORE INTO hazard_event_revision
               (event_id, revision, changed_at, decision_version, snapshot, change_set)
               VALUES (?,?,?,?,?,?)""",
            (
                event.id,
                event.revision,
                to_iso(event.last_updated_at),
                decision_version,
                dumps(payload),
                dumps(change_set),
            ),
        )

    def link(self, event_id: str, observation_id: str, score: float, reasons: list[str]) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO event_source_link
               (event_id, observation_id, match_score, match_reasons)
               VALUES (?,?,?,?)""",
            (event_id, observation_id, score, dumps(reasons)),
        )

    def get(self, event_id: str) -> HazardEvent | None:
        row = self.db.query_one("SELECT current_payload FROM hazard_event WHERE id=?", (event_id,))
        return HazardEvent.model_validate(loads(row["current_payload"], {})) if row else None

    def find_by_source(self, provider: str, source_id: str) -> HazardEvent | None:
        """Locate the canonical event a provider's own identifier already maps to."""
        row = self.db.query_one(
            """SELECT e.current_payload FROM hazard_event e
               JOIN event_source_link l ON l.event_id = e.id
               JOIN source_observation o ON o.id = l.observation_id
               WHERE o.provider=? AND o.source_id=?
               ORDER BY e.last_updated_at DESC LIMIT 1""",
            (provider, source_id),
        )
        return HazardEvent.model_validate(loads(row["current_payload"], {})) if row else None

    def candidates(
        self,
        hazard_type: HazardType,
        origin_time: datetime,
        window_seconds: float,
    ) -> list[HazardEvent]:
        window = timedelta(seconds=window_seconds)
        lo = to_iso(origin_time - window)
        hi = to_iso(origin_time + window)
        rows = self.db.query(
            """SELECT current_payload FROM hazard_event
               WHERE hazard_type=? AND origin_time BETWEEN ? AND ?
                 AND state != 'RETRACTED'""",
            (hazard_type.value, lo, hi),
        )
        return [HazardEvent.model_validate(loads(r["current_payload"], {})) for r in rows]

    def list_events(
        self,
        hazard_types: list[HazardType] | None = None,
        states: list[EventState] | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        min_magnitude: float | None = None,
        limit: int = 500,
    ) -> list[HazardEvent]:
        sql = ["SELECT current_payload FROM hazard_event WHERE 1=1"]
        params: list[Any] = []
        if hazard_types:
            sql.append(f"AND hazard_type IN ({','.join('?' * len(hazard_types))})")
            params += [h.value for h in hazard_types]
        if states:
            sql.append(f"AND state IN ({','.join('?' * len(states))})")
            params += [s.value for s in states]
        # An earthquake happened at a moment, so a window means its origin time.
        # A volcano alert stands until it is withdrawn and its origin can be
        # months old, so for those recency comes from the last update instead.
        recency = "COALESCE(origin_time, last_updated_at)"
        standing = "hazard_type <> 'EARTHQUAKE' AND state <> 'ENDED' AND last_updated_at"
        if since and until:
            sql.append(f"AND (({recency} BETWEEN ? AND ?) OR ({standing} BETWEEN ? AND ?))")
            bounds = [to_iso(since), to_iso(until)]
            params += bounds + bounds
        elif since:
            sql.append(f"AND ({recency} >= ? OR ({standing} >= ?))")
            params += [to_iso(since), to_iso(since)]
        elif until:
            sql.append(f"AND {recency} <= ?")
            params.append(to_iso(until))
        if bbox:
            sql.append("AND longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?")
            params += [bbox[0], bbox[2], bbox[1], bbox[3]]
        if min_magnitude is not None:
            sql.append("AND (magnitude IS NULL OR magnitude >= ?)")
            params.append(min_magnitude)
        sql.append("ORDER BY COALESCE(origin_time, last_updated_at) DESC LIMIT ?")
        params.append(limit)
        rows = self.db.query(" ".join(sql), params)
        return [HazardEvent.model_validate(loads(r["current_payload"], {})) for r in rows]

    def revisions(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            """SELECT revision, changed_at, decision_version, change_set, snapshot
               FROM hazard_event_revision WHERE event_id=? ORDER BY revision ASC""",
            (event_id,),
        )
        return [
            {
                "revision": r["revision"],
                "changedAt": r["changed_at"],
                "decisionVersion": r["decision_version"],
                "changeSet": loads(r["change_set"], {}),
                "snapshot": loads(r["snapshot"], {}),
            }
            for r in rows
        ]

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM hazard_event")
        return int(row["n"]) if row else 0


class FrameRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, frame: GeometryFrame) -> None:
        min_lon, min_lat, max_lon, max_lat = bbox_of(frame.geometry)
        self.db.execute(
            """INSERT OR REPLACE INTO hazard_geometry_frame
               (id, event_id, geometry_type, frame_kind, valid_time, lead_hours,
                lower_altitude_m, upper_altitude_m, geometry,
                min_lon, min_lat, max_lon, max_lat,
                source_provider, source_ref, properties)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                frame.id,
                frame.event_id,
                frame.geometry_type.value,
                frame.frame_kind.value,
                to_iso(frame.valid_time),
                frame.lead_hours,
                frame.lower_altitude_m,
                frame.upper_altitude_m,
                dumps(frame.geometry),
                min_lon,
                min_lat,
                max_lon,
                max_lat,
                frame.source_provider,
                frame.source_ref,
                dumps(frame.properties),
            ),
        )

    def replace_for_event(self, event_id: str, frames: list[GeometryFrame]) -> None:
        """A new advisory supersedes the previous frame set for that event."""
        with self.db.tx() as conn:
            conn.execute("DELETE FROM hazard_geometry_frame WHERE event_id=?", (event_id,))
        for frame in frames:
            self.save(frame)

    def for_event(self, event_id: str) -> list[GeometryFrame]:
        rows = self.db.query(
            "SELECT * FROM hazard_geometry_frame WHERE event_id=? ORDER BY valid_time ASC",
            (event_id,),
        )
        return [_row_to_frame(r) for r in rows]

    def in_bbox(
        self, bbox: tuple[float, float, float, float], event_ids: list[str] | None = None
    ) -> list[GeometryFrame]:
        sql = [
            "SELECT * FROM hazard_geometry_frame",
            "WHERE NOT (max_lon < ? OR min_lon > ? OR max_lat < ? OR min_lat > ?)",
        ]
        params: list[Any] = [bbox[0], bbox[2], bbox[1], bbox[3]]
        if event_ids:
            sql.append(f"AND event_id IN ({','.join('?' * len(event_ids))})")
            params += event_ids
        sql.append("ORDER BY valid_time ASC")
        return [_row_to_frame(r) for r in self.db.query(" ".join(sql), params)]

    def all_frames(self) -> list[GeometryFrame]:
        return [_row_to_frame(r) for r in self.db.query("SELECT * FROM hazard_geometry_frame")]


class AdvisoryRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, advisory: AshAdvisory) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO ash_advisory
               (advisory_id, event_id, volcano_id, volcano_name, issue_time,
                observation_time, status, source, altitude, movement,
                geometry_quality, raw_bulletin, parser_version, parser_warnings)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                advisory.advisory_id,
                advisory.event_id,
                advisory.volcano_id,
                advisory.volcano_name,
                to_iso(advisory.issue_time),
                to_iso(advisory.observation_time),
                advisory.status,
                advisory.source,
                dumps(advisory.altitude.model_dump()),
                dumps(advisory.movement.model_dump()),
                advisory.geometry_quality.value,
                advisory.raw_bulletin,
                advisory.parser_version,
                dumps(advisory.parser_warnings),
            ),
        )

    def for_event(self, event_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM ash_advisory WHERE event_id=? ORDER BY issue_time DESC", (event_id,)
        )
        return [
            {
                "advisoryId": r["advisory_id"],
                "volcanoName": r["volcano_name"],
                "issueTime": r["issue_time"],
                "observationTime": r["observation_time"],
                "status": r["status"],
                "source": r["source"],
                "altitude": loads(r["altitude"], {}),
                "movement": loads(r["movement"], {}),
                "geometryQuality": r["geometry_quality"],
                "rawBulletin": r["raw_bulletin"],
                "parserWarnings": loads(r["parser_warnings"], []),
            }
            for r in rows
        ]


class VolcanoRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_many(self, volcanoes: list[Volcano]) -> None:
        with self.db.tx() as conn:
            for v in volcanoes:
                conn.execute(
                    """INSERT OR REPLACE INTO volcano
                       (id, name, latitude, longitude, country, elevation_m, aliases)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        v.id,
                        v.name,
                        v.latitude,
                        v.longitude,
                        v.country,
                        v.elevation_m,
                        dumps(v.aliases),
                    ),
                )

    def all(self) -> list[Volcano]:
        rows = self.db.query("SELECT * FROM volcano")
        return [
            Volcano(
                id=r["id"],
                name=r["name"],
                latitude=r["latitude"],
                longitude=r["longitude"],
                country=r["country"],
                elevation_m=r["elevation_m"],
                aliases=loads(r["aliases"], []),
            )
            for r in rows
        ]

    def count(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM volcano")
        return int(row["n"]) if row else 0


class WatchAreaRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def save(self, area: WatchArea) -> None:
        min_lon, min_lat, max_lon, max_lat = bbox_of(area.geometry)
        self.db.execute(
            """INSERT OR REPLACE INTO watch_area
               (id, name, geometry, min_lon, min_lat, max_lon, max_lat,
                hazard_types, min_magnitude, radius_km, enabled, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                area.id,
                area.name,
                dumps(area.geometry),
                min_lon,
                min_lat,
                max_lon,
                max_lat,
                dumps([h.value for h in area.hazard_types]),
                area.min_magnitude,
                area.radius_km,
                1 if area.enabled else 0,
                to_iso(utcnow()),
            ),
        )

    def all(self, enabled_only: bool = False) -> list[WatchArea]:
        sql = "SELECT * FROM watch_area"
        if enabled_only:
            sql += " WHERE enabled = 1"
        return [_row_to_watch_area(r) for r in self.db.query(sql)]

    def get(self, area_id: str) -> WatchArea | None:
        row = self.db.query_one("SELECT * FROM watch_area WHERE id=?", (area_id,))
        return _row_to_watch_area(row) if row else None

    def delete(self, area_id: str) -> None:
        self.db.execute("DELETE FROM watch_area WHERE id=?", (area_id,))


class ProviderHealthRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def record_success(self, provider: str, message_count: int = 0) -> None:
        now = to_iso(utcnow())
        self.db.execute(
            """INSERT INTO provider_health
               (provider, state, last_success_at, last_message_at, last_error,
                consecutive_errors, messages_total, updated_at)
               VALUES (?, 'HEALTHY', ?, ?, NULL, 0, ?, ?)
               ON CONFLICT(provider) DO UPDATE SET
                 state='HEALTHY',
                 last_success_at=excluded.last_success_at,
                 last_message_at=CASE WHEN ? > 0 THEN excluded.last_message_at
                                      ELSE provider_health.last_message_at END,
                 last_error=NULL,
                 consecutive_errors=0,
                 messages_total=provider_health.messages_total + ?,
                 updated_at=excluded.updated_at""",
            (provider, now, now, message_count, now, message_count, message_count),
        )

    def record_error(self, provider: str, error: str) -> None:
        now = to_iso(utcnow())
        self.db.execute(
            """INSERT INTO provider_health
               (provider, state, last_error, consecutive_errors, updated_at)
               VALUES (?, 'DEGRADED', ?, 1, ?)
               ON CONFLICT(provider) DO UPDATE SET
                 state='DEGRADED',
                 last_error=excluded.last_error,
                 consecutive_errors=provider_health.consecutive_errors + 1,
                 updated_at=excluded.updated_at""",
            (provider, error[:500], now),
        )

    def set_state(self, provider: str, state: str) -> None:
        now = to_iso(utcnow())
        self.db.execute(
            """INSERT INTO provider_health (provider, state, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(provider) DO UPDATE SET
                 state=excluded.state, updated_at=excluded.updated_at""",
            (provider, state, now),
        )

    def all(self) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM provider_health ORDER BY provider")
        return [dict(r) for r in rows]


class PollStateRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, provider: str) -> tuple[str | None, str | None]:
        row = self.db.query_one(
            "SELECT etag, last_modified FROM poll_state WHERE provider=?", (provider,)
        )
        return (row["etag"], row["last_modified"]) if row else (None, None)

    def set(self, provider: str, etag: str | None, last_modified: str | None) -> None:
        self.db.execute(
            """INSERT INTO poll_state (provider, etag, last_modified, last_polled_at)
               VALUES (?,?,?,?)
               ON CONFLICT(provider) DO UPDATE SET
                 etag=excluded.etag,
                 last_modified=excluded.last_modified,
                 last_polled_at=excluded.last_polled_at""",
            (provider, etag, last_modified, to_iso(utcnow())),
        )


def _row_to_observation(row: Any) -> Observation:
    return Observation(
        message_id=row["id"],
        provider=row["provider"],
        source_id=row["source_id"],
        source_revision=row["source_revision"],
        hazard_type=HazardType(row["hazard_type"]),
        action=row["action"],
        source_issued_at=from_iso(row["source_issued_at"]),
        observed_at=from_iso(row["observed_at"]),
        ingested_at=from_iso(row["ingested_at"]) or utcnow(),
        parser_version=row["parser_version"],
        raw_object_key=row["raw_object_key"],
        raw_sha256=row["raw_sha256"],
        normalized=loads(row["normalized_payload"], {}),
        validation_warnings=loads(row["validation_warnings"], []),
    )


def _row_to_frame(row: Any) -> GeometryFrame:
    return GeometryFrame(
        id=row["id"],
        event_id=row["event_id"],
        geometry_type=GeometryType(row["geometry_type"]),
        frame_kind=FrameKind(row["frame_kind"]),
        valid_time=from_iso(row["valid_time"]) or utcnow(),
        lead_hours=row["lead_hours"],
        lower_altitude_m=row["lower_altitude_m"],
        upper_altitude_m=row["upper_altitude_m"],
        geometry=loads(row["geometry"], {}),
        source_provider=row["source_provider"],
        source_ref=row["source_ref"],
        properties=loads(row["properties"], {}),
    )


def _row_to_watch_area(row: Any) -> WatchArea:
    return WatchArea(
        id=row["id"],
        name=row["name"],
        geometry=loads(row["geometry"], {}),
        hazard_types=[HazardType(h) for h in loads(row["hazard_types"], [])],
        min_magnitude=row["min_magnitude"],
        radius_km=row["radius_km"],
        enabled=bool(row["enabled"]),
    )


__all__ = [
    "AdvisoryRepo",
    "EventRepo",
    "EventState",
    "EventSummary",
    "FrameRepo",
    "ObservationRepo",
    "PollStateRepo",
    "ProvenanceClass",
    "ProviderHealthRepo",
    "Quality",
    "SourceRef",
    "VolcanoRepo",
    "WatchAreaRepo",
    "new_id",
]
