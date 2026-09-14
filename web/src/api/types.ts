export type HazardType = "EARTHQUAKE" | "VOLCANO" | "ASH" | "WILDFIRE";

export type EventState =
  | "DETECTED"
  | "PRELIMINARY"
  | "CONFIRMED"
  | "UPDATED"
  | "ENDED"
  | "RETRACTED";

export type ProvenanceClass =
  | "AUTHORITATIVE_EEW"
  | "AUTHORITATIVE_NOTICE"
  | "MULTISOURCE_RAPID"
  | "SINGLE_SOURCE_RAPID"
  | "AUTOMATED_SIGNAL"
  | "MODEL_ESTIMATE";

export type Quality =
  | "PRELIMINARY"
  | "REVIEWED"
  | "OFFICIAL_ADVISORY"
  | "MODELLED"
  | "UNAVAILABLE";

export type FrameKind = "OBSERVED" | "FORECAST";

export interface SeismicModel {
  p_velocity_km_s: number;
  s_velocity_km_s: number;
  delivery_margin_seconds: number;
  version: string;
  uncertainty_fraction: number;
}

export interface Meta {
  app: string;
  subtitle: string;
  seismicModel: SeismicModel;
  provenanceLabels: Record<ProvenanceClass, string>;
  hazardProvenanceLabels: Record<string, string>;
  activeWindowHours: number;
  attribution: string[];
  disclaimer: string;
}

export interface EventSummary {
  magnitude: number | null;
  magnitude_type: string | null;
  depth_km: number | null;
  place: string | null;
  volcano_id: string | null;
  volcano_name: string | null;
  alert_level: string | null;
  tsunami: boolean | null;
  detection_count: number | null;
  max_frp_mw: number | null;
}

export interface SourceRef {
  provider: string;
  source_id: string;
  revision: string;
  observation_id: string;
}

export interface HazardEvent {
  id: string;
  hazard_type: HazardType;
  state: EventState;
  provenance_class: ProvenanceClass;
  quality: Quality;
  origin_time: string | null;
  first_observed_at: string | null;
  first_ingested_at: string;
  last_updated_at: string;
  revision: number;
  longitude: number | null;
  latitude: number | null;
  summary: EventSummary;
  confidence: number;
  confidence_reasons: string[];
  source_refs: SourceRef[];
  field_provenance: Record<string, string>;
  label: string;
  dataAgeSeconds: number | null;
  providers: string[];
}

export interface EventDetail extends HazardEvent {
  frames: GeometryFrame[];
  advisories: Record<string, unknown>[];
}

export interface GeometryFrame {
  id: string;
  event_id: string;
  geometry_type: string;
  frame_kind: FrameKind;
  valid_time: string;
  lead_hours: number | null;
  lower_altitude_m: number | null;
  upper_altitude_m: number | null;
  geometry: GeoJSON.Geometry;
  source_provider: string;
  source_ref: string;
  properties: Record<string, unknown>;
}

export interface EventFeatureProperties {
  eventId: string;
  hazardType: HazardType;
  state: EventState;
  provenanceClass: ProvenanceClass;
  label: string;
  quality: Quality;
  magnitude: number | null;
  depthKm: number | null;
  place: string | null;
  volcanoName: string | null;
  alertLevel: string | null;
  tsunami: boolean | null;
  detectionCount: number | null;
  maxFrpMw: number | null;
  originTime: string | null;
  originTimeMs: number | null;
  lastUpdatedAt: string | null;
  dataAgeSeconds: number | null;
  confidence: number;
  providers: string[];
  revision: number;
}

export interface FrameFeatureProperties {
  frameId: string;
  eventId: string;
  frameKind: FrameKind;
  validTime: string;
  validTimeMs: number;
  leadHours: number | null;
  lowerAltitudeM: number | null;
  upperAltitudeM: number | null;
  source: string;
  styleClass: string;
}

export interface ArrivalEstimate {
  estimate: string;
  earliest: string;
  latest: string;
  seconds_from_now: number;
  model: string;
  quality: Quality;
}

export interface ImpactResult {
  event_id: string;
  distance_km: number;
  hypocentral_distance_km: number | null;
  p_arrival: ArrivalEstimate | null;
  s_arrival: ArrivalEstimate | null;
  already_arrived: boolean;
  ash_intersects: boolean;
  ash_entry_time: string | null;
  ash_exit_time: string | null;
  ash_altitude: Record<string, number | null> | null;
  provenance_class: ProvenanceClass;
  hazardType: HazardType;
  label: string;
  magnitude: number | null;
  place: string | null;
}

export interface ImpactResponse {
  location: { longitude: number; latitude: number };
  results: ImpactResult[];
  model: SeismicModel;
  note: string;
}

export interface WatchArea {
  id: string;
  name: string;
  geometry: GeoJSON.Geometry;
  hazard_types: HazardType[];
  min_magnitude: number;
  radius_km: number;
  enabled: boolean;
}

export interface ProviderRecord {
  provider: string;
  state: "HEALTHY" | "DEGRADED" | "STALE" | "DISABLED" | string;
  lastMessageAgeSeconds: number | null;
  staleAfterSeconds: number;
  consecutiveErrors: number;
  messagesTotal: number;
  lastError: string | null;
  attribution: string | null;
}

export interface RefreshResult {
  provider: string;
  status: "REQUESTED" | "COOLING_DOWN" | "NOT_APPLICABLE" | string;
  retryAfterSeconds?: number;
}

export interface ProviderSetting {
  provider: string;
  key: string;
  enabled: boolean;
  mode: "POLL" | "STREAM";
  pollSeconds: number | null;
  staleAfterSeconds: number;
  envPrefix: string;
  attribution: string | null;
}

export interface FirmsKeyStatus {
  configured: boolean;
  /** Masked tail only. The key itself never leaves the server. */
  hint: string | null;
  fromEnvironment: boolean;
  enabled: boolean;
}

export interface SettingsResponse {
  providers: ProviderSetting[];
  ingestEnabled: boolean;
  manualPollMinSeconds: number;
  dataDir: string;
  firmsKey: FirmsKeyStatus;
}

export interface NotificationRecord {
  id: string;
  eventId: string;
  alertType: string;
  title: string;
  body: string;
  createdAt: string;
  readAt: string | null;
  watchAreaId: string | null;
  reasonCodes: string[];
  impact: Partial<ImpactResult>;
}

export interface AlertDecision {
  revision: number;
  watchAreaId: string | null;
  alertType: string;
  decision: "SEND" | "SUPPRESS" | string;
  reasonCodes: string[];
  impact: Partial<ImpactResult>;
  policyVersion: string;
  createdAt: string;
}

export interface Observation {
  message_id: string;
  provider: string;
  source_id: string;
  source_revision: string;
  observed_at: string | null;
  source_issued_at: string | null;
  ingested_at: string;
  parser_version: string;
  raw_object_key: string;
  raw_sha256: string;
  normalized: Record<string, unknown>;
  validation_warnings: string[];
  rawAvailable: boolean;
}

/** Bus subjects published by gaia.engine.bus. */
export type BusSubject =
  | "raw"
  | "normalized"
  | "canonical.event.created"
  | "canonical.event.updated"
  | "canonical.event.cancelled"
  | "impact.updated"
  | "notification.created"
  | "provider.health";

export type RealtimeMessage =
  | { type: "hello"; sequence: number; resyncRequired: boolean; serverTime: string }
  | { type: "heartbeat"; sequence: number; serverTime: string }
  | { type: BusSubject; sequence: number; payload: Record<string, unknown> };
