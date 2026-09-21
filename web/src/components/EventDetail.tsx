import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type {
  ArrivalEstimate,
  EventDetail as EventDetailType,
  HazardType,
  ImpactResult,
} from "../api/types";
import type { MapClock } from "../map/useMapClock";
import { useTimeZone } from "../state/timeZone";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { WebcamPlayer } from "./WebcamPlayer";
import { countdown, km, magnitudeText, stampIn, timeIn, utcStamp } from "./format";

/** Fallback headings. A title must never assert a hazard the event is not. */
const HAZARD_TITLES: Record<HazardType, string> = {
  EARTHQUAKE: "Earthquake",
  VOLCANO: "Volcano",
  ASH: "Volcanic ash",
  WILDFIRE: "Wildfire",
};

interface Props {
  eventId: string | null;
  location: { longitude: number; latitude: number } | null;
  clock: MapClock;
  onClose: () => void;
}

function ArrivalRow({
  phase,
  arrival,
  nowMs,
}: {
  phase: string;
  arrival: ArrivalEstimate | null;
  nowMs: number;
}): React.JSX.Element | null {
  const { zone } = useTimeZone();
  if (!arrival) return null;

  const earliestMs = Date.parse(arrival.earliest);
  const latestMs = Date.parse(arrival.latest);
  const secondsAway = (earliestMs - nowMs) / 1000;
  const passed = latestMs < nowMs;

  return (
    <div className="arrival-row">
      <span className="arrival-phase">{phase}</span>
      <span className="arrival-window">
        {timeIn(zone, arrival.earliest)} – {timeIn(zone, arrival.latest)}
      </span>
      <span className="arrival-window" style={{ color: passed ? "var(--fg-faint)" : undefined }}>
        {passed ? "passed" : secondsAway > 0 ? `in ${countdown(secondsAway)}` : "arriving"}
      </span>
    </div>
  );
}

/**
 * Arrival is always shown as an interval from a named model, on the opaque
 * tier, with the disclaimer attached. A single time would imply a precision
 * this model does not have.
 */
function ArrivalPanel({
  impact,
  note,
  nowMs,
}: {
  impact: ImpactResult;
  note: string;
  nowMs: number;
}): React.JSX.Element {
  const { zone } = useTimeZone();
  const model = impact.p_arrival?.model ?? impact.s_arrival?.model ?? "—";

  return (
    <div className="arrival solid" style={{ margin: "0 0 10px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
        <span>Your location</span>
        <span style={{ fontFamily: "var(--mono)" }}>{km(impact.distance_km)}</span>
      </div>

      {impact.p_arrival || impact.s_arrival ? (
        <>
          <ArrivalRow phase="P" arrival={impact.p_arrival} nowMs={nowMs} />
          <ArrivalRow phase="S" arrival={impact.s_arrival} nowMs={nowMs} />
        </>
      ) : null}

      {impact.ash_intersects ? (
        <div className="arrival-row">
          <span className="arrival-phase">ASH</span>
          <span className="arrival-window">
            {impact.ash_entry_time ? timeIn(zone, impact.ash_entry_time) : "present"}
          </span>
          <span className="arrival-window">
            {impact.ash_exit_time ? `to ${timeIn(zone, impact.ash_exit_time)}` : ""}
          </span>
        </div>
      ) : null}

      <p className="arrival-note">
        {note} Model {model}.
      </p>
    </div>
  );
}

export function EventDetail({ eventId, location, clock, onClose }: Props): React.JSX.Element | null {
  const { zone } = useTimeZone();
  const [detail, setDetail] = useState<EventDetailType | null>(null);
  const [impact, setImpact] = useState<{ result: ImpactResult; note: string } | null>(null);
  const [hazardMapOpen, setHazardMapOpen] = useState(false);
  const [mapZoom, setMapZoom] = useState(1);
  const [mapPan, setMapPan] = useState({ x: 0, y: 0 });
  const mapDrag = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  const clampZoom = (value: number): number => Math.min(4, Math.max(1, value));

  const zoomTo = (value: number): void => {
    const next = clampZoom(value);
    setMapZoom(next);
    if (next === 1) setMapPan({ x: 0, y: 0 });
  };

  const onMapWheel = (event: React.WheelEvent<HTMLDivElement>): void => {
    event.preventDefault();
    zoomTo(mapZoom - event.deltaY * 0.0015 * mapZoom);
  };

  const onMapPointerDown = (event: React.PointerEvent<HTMLImageElement>): void => {
    if (mapZoom <= 1) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    mapDrag.current = { x: event.clientX, y: event.clientY, panX: mapPan.x, panY: mapPan.y };
  };

  const onMapPointerMove = (event: React.PointerEvent<HTMLImageElement>): void => {
    if (!mapDrag.current) return;
    setMapPan({
      x: mapDrag.current.panX + (event.clientX - mapDrag.current.x),
      y: mapDrag.current.panY + (event.clientY - mapDrag.current.y),
    });
  };

  const onMapPointerUp = (): void => {
    mapDrag.current = null;
  };

  useEffect(() => {
    if (!hazardMapOpen) {
      setMapZoom(1);
      setMapPan({ x: 0, y: 0 });
    }
  }, [hazardMapOpen]);

  useEffect(() => {
    if (!hazardMapOpen) return;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setHazardMapOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hazardMapOpen]);

  useEffect(() => {
    if (!eventId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api
      .event(eventId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId]);

  useEffect(() => {
    if (!eventId || !location) {
      setImpact(null);
      return;
    }
    let cancelled = false;
    api
      .impact(location.longitude, location.latitude, eventId)
      .then((response) => {
        const first = response.results[0];
        if (!cancelled) setImpact(first ? { result: first, note: response.note } : null);
      })
      .catch(() => {
        if (!cancelled) setImpact(null);
      });
    return () => {
      cancelled = true;
    };
  }, [eventId, location]);

  if (!eventId) return null;

  if (!detail) {
    return (
      <section className="panel glass">
        <header className="panel-head">
          <span className="panel-title">Event</span>
          <button className="btn ghost" onClick={onClose} type="button">
            ✕
          </button>
        </header>
        <p className="empty">Loading…</p>
      </section>
    );
  }

  const title =
    detail.hazard_type === "EARTHQUAKE"
      ? `M ${magnitudeText(detail.summary.magnitude)}`
      : (detail.summary.volcano_name ?? HAZARD_TITLES[detail.hazard_type]);

  return (
    <section className="panel glass grow">
      <header className="panel-head">
        <span className="panel-title">Event detail</span>
        <button className="btn ghost" onClick={onClose} type="button" aria-label="Close">
          ✕
        </button>
      </header>

      <div className="panel-body pad">
        <h2 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 600 }}>{title}</h2>
        <p style={{ margin: "0 0 10px", fontSize: 12, color: "var(--fg-dim)" }}>
          {detail.summary.place ?? detail.summary.volcano_name ?? "Location unavailable"}
        </p>

        <div style={{ marginBottom: 12 }}>
          <ProvenanceBadge
            provenanceClass={detail.provenance_class}
            label={detail.label}
            dataAgeSeconds={detail.dataAgeSeconds}
          />
        </div>

        {detail.state === "RETRACTED" ? (
          <div className="alert solid CANCELLATION" style={{ marginBottom: 10 }}>
            <span className="alert-title">Retracted by source</span>
            <span className="alert-body">
              This event was withdrawn. Disregard earlier information about it.
            </span>
          </div>
        ) : null}

        {impact ? (
          <ArrivalPanel impact={impact.result} note={impact.note} nowMs={clock.displayMs} />
        ) : location ? null : (
          <p className="disclaimer solid" style={{ marginBottom: 10 }}>
            Set a location to see modelled arrival times.
          </p>
        )}

        {detail.webcams.length > 0 ? (
          <>
            <div className="panel-title" style={{ margin: "0 0 6px" }}>
              Nearby webcams
            </div>
            {detail.webcams.map((webcam) => (
              <WebcamPlayer key={webcam.id} webcam={webcam} />
            ))}
          </>
        ) : null}

        {detail.hazardMap ? (
          <>
            <div className="panel-title" style={{ margin: "0 0 6px" }}>
              Official hazard zone map
            </div>
            <button
              className="hazard-map"
              type="button"
              onClick={() => setHazardMapOpen(true)}
              aria-label={`View ${detail.hazardMap.volcanoName} hazard zone map`}
            >
              <img
                src={detail.hazardMap.imageUrl}
                alt={`${detail.hazardMap.volcanoName} hazard zone map (${detail.hazardMap.year})`}
              />
            </button>
            <div className="webcam-caption" style={{ marginBottom: 10 }}>
              <span>
                {detail.hazardMap.volcanoName} KRB map, {detail.hazardMap.year}
              </span>
              <span>{detail.hazardMap.attribution}</span>
              <a href={detail.hazardMap.sourceUrl} target="_blank" rel="noreferrer">
                View original on MAGMA Indonesia
              </a>
            </div>
          </>
        ) : null}

        {detail.hazardMap && hazardMapOpen
          ? createPortal(
              <div
                className="modal-scrim"
                onClick={() => setHazardMapOpen(false)}
                role="presentation"
              >
                <div
                  className="modal solid hazard-map-modal"
                  onClick={(event) => event.stopPropagation()}
                  role="dialog"
                  aria-modal="true"
                  aria-label={`${detail.hazardMap.volcanoName} hazard zone map`}
                >
                  <header className="panel-head">
                    <span className="panel-title">
                      {detail.hazardMap.volcanoName} KRB map, {detail.hazardMap.year}
                    </span>
                    <div className="hazard-map-zoom-controls">
                      <button
                        className="btn ghost"
                        onClick={() => zoomTo(mapZoom - 0.5)}
                        type="button"
                        disabled={mapZoom <= 1}
                        aria-label="Zoom out"
                      >
                        −
                      </button>
                      <button
                        className="btn ghost"
                        onClick={() => zoomTo(1)}
                        type="button"
                        disabled={mapZoom === 1}
                        aria-label="Reset zoom"
                      >
                        {Math.round(mapZoom * 100)}%
                      </button>
                      <button
                        className="btn ghost"
                        onClick={() => zoomTo(mapZoom + 0.5)}
                        type="button"
                        disabled={mapZoom >= 4}
                        aria-label="Zoom in"
                      >
                        +
                      </button>
                      <button
                        className="btn ghost"
                        onClick={() => setHazardMapOpen(false)}
                        type="button"
                        aria-label="Close"
                      >
                        ✕
                      </button>
                    </div>
                  </header>
                  <div className="modal-body hazard-map-modal-body" onWheel={onMapWheel}>
                    <img
                      src={detail.hazardMap.imageUrl}
                      alt={`${detail.hazardMap.volcanoName} hazard zone map (${detail.hazardMap.year})`}
                      style={{
                        transform: `translate(${mapPan.x}px, ${mapPan.y}px) scale(${mapZoom})`,
                        cursor: mapZoom > 1 ? "grab" : "default",
                      }}
                      onPointerDown={onMapPointerDown}
                      onPointerMove={onMapPointerMove}
                      onPointerUp={onMapPointerUp}
                      onPointerCancel={onMapPointerUp}
                      draggable={false}
                    />
                    <div className="webcam-caption">
                      <span>{detail.hazardMap.attribution}</span>
                      <a href={detail.hazardMap.sourceUrl} target="_blank" rel="noreferrer">
                        View on MAGMA Indonesia
                      </a>
                    </div>
                  </div>
                </div>
              </div>,
              document.body,
            )
          : null}

        <dl className="kv">
          <dt>State</dt>
          <dd>{detail.state}</dd>
          <dt>Quality</dt>
          <dd>{detail.quality}</dd>
          <dt>Confidence</dt>
          <dd>{detail.confidence.toFixed(2)}</dd>
          <dt>Origin</dt>
          <dd>
            {stampIn(zone, detail.origin_time)}
            {zone !== "UTC" ? (
              <span style={{ color: "var(--fg-faint)" }}> · {utcStamp(detail.origin_time)}</span>
            ) : null}
          </dd>
          <dt>Updated</dt>
          <dd>{stampIn(zone, detail.last_updated_at)}</dd>
          <dt>Depth</dt>
          <dd>{km(detail.summary.depth_km)}</dd>
          <dt>Position</dt>
          <dd>
            {detail.latitude?.toFixed(3) ?? "—"}, {detail.longitude?.toFixed(3) ?? "—"}
          </dd>
          <dt>Revision</dt>
          <dd>{detail.revision}</dd>
          <dt>Sources</dt>
          <dd>{detail.providers.join(", ") || "—"}</dd>
        </dl>

        {detail.confidence_reasons.length > 0 ? (
          <>
            <div className="panel-title" style={{ margin: "14px 0 6px" }}>
              Why this confidence
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "var(--fg-dim)" }}>
              {detail.confidence_reasons.map((reason) => (
                <li key={reason}>{reason.replaceAll("_", " ").toLowerCase()}</li>
              ))}
            </ul>
          </>
        ) : null}

        <div className="panel-title" style={{ margin: "14px 0 6px" }}>
          Source observations
        </div>
        <dl className="kv">
          {detail.source_refs.map((ref) => (
            <div key={`${ref.provider}:${ref.source_id}`} style={{ display: "contents" }}>
              <dt>{ref.provider}</dt>
              <dd>{ref.source_id}</dd>
            </div>
          ))}
        </dl>

        {detail.frames.length > 0 ? (
          <>
            <div className="panel-title" style={{ margin: "14px 0 6px" }}>
              Ash frames
            </div>
            <dl className="kv">
              {detail.frames.map((frame) => (
                <div key={frame.id} style={{ display: "contents" }}>
                  <dt>{frame.frame_kind === "OBSERVED" ? "Observed" : `+${frame.lead_hours}h`}</dt>
                  <dd>{utcStamp(frame.valid_time)}</dd>
                </div>
              ))}
            </dl>
            <p className="disclaimer">
              Advisory times stay in UTC. That is the zone the issuing VAAC and its aviation
              readers work in, and converting them here would invite a dispatch error.
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}
