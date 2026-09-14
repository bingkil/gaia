-- Local-first translation of spec section 9.
-- Geometry is stored as GeoJSON text with explicit bbox columns; the bbox acts
-- as the coarse filter that a PostGIS GiST index would provide, and Shapely
-- performs the exact predicate afterwards.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_observation (
    id                  TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    source_revision     TEXT NOT NULL,
    hazard_type         TEXT NOT NULL,
    action              TEXT NOT NULL,
    source_issued_at    TEXT,
    observed_at         TEXT,
    ingested_at         TEXT NOT NULL,
    parser_version      TEXT NOT NULL,
    raw_object_key      TEXT NOT NULL,
    raw_sha256          TEXT NOT NULL,
    normalized_payload  TEXT NOT NULL,
    validation_warnings TEXT NOT NULL DEFAULT '[]',
    UNIQUE (provider, source_id, source_revision)
);

CREATE INDEX IF NOT EXISTS observation_lookup_idx
    ON source_observation (hazard_type, observed_at DESC);
CREATE INDEX IF NOT EXISTS observation_provider_idx
    ON source_observation (provider, ingested_at DESC);

CREATE TABLE IF NOT EXISTS hazard_event (
    id                  TEXT PRIMARY KEY,
    hazard_type         TEXT NOT NULL,
    state               TEXT NOT NULL,
    provenance_class    TEXT NOT NULL,
    quality             TEXT NOT NULL,
    origin_time         TEXT,
    first_observed_at   TEXT,
    first_ingested_at   TEXT NOT NULL,
    last_updated_at     TEXT NOT NULL,
    revision            INTEGER NOT NULL,
    longitude           REAL,
    latitude            REAL,
    magnitude           REAL,
    magnitude_type      TEXT,
    depth_km            REAL,
    confidence          REAL NOT NULL,
    current_payload     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS hazard_event_time_idx ON hazard_event (origin_time DESC);
CREATE INDEX IF NOT EXISTS hazard_event_type_idx ON hazard_event (hazard_type, state);
CREATE INDEX IF NOT EXISTS hazard_event_bbox_idx ON hazard_event (longitude, latitude);

-- Append-only history. Never updated in place.
CREATE TABLE IF NOT EXISTS hazard_event_revision (
    event_id            TEXT NOT NULL REFERENCES hazard_event(id),
    revision            INTEGER NOT NULL,
    changed_at          TEXT NOT NULL,
    decision_version    TEXT NOT NULL,
    snapshot            TEXT NOT NULL,
    change_set          TEXT NOT NULL,
    PRIMARY KEY (event_id, revision)
);

CREATE TABLE IF NOT EXISTS event_source_link (
    event_id            TEXT NOT NULL REFERENCES hazard_event(id),
    observation_id      TEXT NOT NULL REFERENCES source_observation(id),
    match_score         REAL NOT NULL,
    match_reasons       TEXT NOT NULL,
    PRIMARY KEY (event_id, observation_id)
);

CREATE INDEX IF NOT EXISTS event_source_link_obs_idx ON event_source_link (observation_id);

CREATE TABLE IF NOT EXISTS hazard_geometry_frame (
    id                  TEXT PRIMARY KEY,
    event_id            TEXT NOT NULL REFERENCES hazard_event(id),
    geometry_type       TEXT NOT NULL,
    frame_kind          TEXT NOT NULL,
    valid_time          TEXT NOT NULL,
    lead_hours          REAL,
    lower_altitude_m    REAL,
    upper_altitude_m    REAL,
    geometry            TEXT NOT NULL,
    min_lon             REAL NOT NULL,
    min_lat             REAL NOT NULL,
    max_lon             REAL NOT NULL,
    max_lat             REAL NOT NULL,
    source_provider     TEXT NOT NULL,
    source_ref          TEXT NOT NULL DEFAULT '',
    properties          TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS frame_event_idx ON hazard_geometry_frame (event_id, valid_time);
CREATE INDEX IF NOT EXISTS frame_bbox_idx ON hazard_geometry_frame (min_lon, min_lat, max_lon, max_lat);

CREATE TABLE IF NOT EXISTS ash_advisory (
    advisory_id         TEXT PRIMARY KEY,
    event_id            TEXT NOT NULL REFERENCES hazard_event(id),
    volcano_id          TEXT,
    volcano_name        TEXT,
    issue_time          TEXT,
    observation_time    TEXT,
    status              TEXT NOT NULL,
    source              TEXT NOT NULL,
    altitude            TEXT NOT NULL DEFAULT '{}',
    movement            TEXT NOT NULL DEFAULT '{}',
    geometry_quality    TEXT NOT NULL,
    raw_bulletin        TEXT NOT NULL DEFAULT '',
    parser_version      TEXT NOT NULL DEFAULT '',
    parser_warnings     TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS ash_advisory_event_idx ON ash_advisory (event_id);

CREATE TABLE IF NOT EXISTS volcano (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    latitude            REAL NOT NULL,
    longitude           REAL NOT NULL,
    country             TEXT,
    elevation_m         REAL,
    aliases             TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS volcano_pos_idx ON volcano (longitude, latitude);

CREATE TABLE IF NOT EXISTS thermal_anomaly (
    id                  TEXT PRIMARY KEY,
    observation_id      TEXT NOT NULL REFERENCES source_observation(id),
    volcano_id          TEXT REFERENCES volcano(id),
    acquired_at         TEXT NOT NULL,
    latitude            REAL NOT NULL,
    longitude           REAL NOT NULL,
    instrument          TEXT,
    satellite           TEXT,
    confidence_category TEXT,
    frp                 REAL,
    daynight            TEXT,
    distance_km         REAL,
    classification      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS thermal_volcano_idx ON thermal_anomaly (volcano_id, acquired_at DESC);

-- Non-volcanic detections are clustered by position instead of by volcano.
CREATE INDEX IF NOT EXISTS thermal_position_idx
    ON thermal_anomaly (acquired_at DESC, longitude, latitude);

-- Single local user: no user_id column. Spec section 17 privacy concerns are
-- largely satisfied by the data never leaving this machine.
CREATE TABLE IF NOT EXISTS watch_area (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    geometry            TEXT NOT NULL,
    min_lon             REAL NOT NULL,
    min_lat             REAL NOT NULL,
    max_lon             REAL NOT NULL,
    max_lat             REAL NOT NULL,
    hazard_types        TEXT NOT NULL,
    min_magnitude       REAL NOT NULL DEFAULT 4.5,
    radius_km           REAL NOT NULL DEFAULT 300,
    enabled             INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_decision (
    id                  TEXT PRIMARY KEY,
    event_id            TEXT NOT NULL,
    event_revision      INTEGER NOT NULL,
    watch_area_id       TEXT NOT NULL,
    policy_version      TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    decision            TEXT NOT NULL,
    reason_codes        TEXT NOT NULL,
    computed_impact     TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    UNIQUE (event_id, event_revision, watch_area_id, policy_version)
);

CREATE INDEX IF NOT EXISTS alert_decision_event_idx ON alert_decision (event_id);

CREATE TABLE IF NOT EXISTS notification (
    id                  TEXT PRIMARY KEY,
    alert_decision_id   TEXT NOT NULL REFERENCES alert_decision(id),
    event_id            TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    template_version    TEXT NOT NULL,
    idempotency_key     TEXT NOT NULL UNIQUE,
    created_at          TEXT NOT NULL,
    read_at             TEXT
);

CREATE INDEX IF NOT EXISTS notification_created_idx ON notification (created_at DESC);

CREATE TABLE IF NOT EXISTS provider_health (
    provider            TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    last_success_at     TEXT,
    last_message_at     TEXT,
    last_error          TEXT,
    consecutive_errors  INTEGER NOT NULL DEFAULT 0,
    messages_total      INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL
);

-- Conditional-request bookkeeping so polling adapters stay well behaved.
CREATE TABLE IF NOT EXISTS poll_state (
    provider            TEXT PRIMARY KEY,
    etag                TEXT,
    last_modified       TEXT,
    last_polled_at      TEXT
);
