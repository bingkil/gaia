import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ArrivalEstimate, EventDetail as EventDetailType, ImpactResult } from "../api/types";
import type { MapClock } from "../map/useMapClock";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { countdown, km, magnitudeText, utcStamp, utcTime } from "./format";

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
  if (!arrival) return null;

  const earliestMs = Date.parse(arrival.earliest);
  const latestMs = Date.parse(arrival.latest);
  const secondsAway = (earliestMs - nowMs) / 1000;
  const passed = latestMs < nowMs;

  return (
    <div className="arrival-row">
      <span className="arrival-phase">{phase}</span>
      <span className="arrival-window">
        {utcTime(arrival.earliest)} – {utcTime(arrival.latest)}
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
            {impact.ash_entry_time ? utcTime(impact.ash_entry_time) : "present"}
          </span>
          <span className="arrival-window">
            {impact.ash_exit_time ? `to ${utcTime(impact.ash_exit_time)}` : ""}
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
  const [detail, setDetail] = useState<EventDetailType | null>(null);
  const [impact, setImpact] = useState<{ result: ImpactResult; note: string } | null>(null);

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
      : (detail.summary.volcano_name ?? "Volcano");

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

        <dl className="kv">
          <dt>State</dt>
          <dd>{detail.state}</dd>
          <dt>Quality</dt>
          <dd>{detail.quality}</dd>
          <dt>Confidence</dt>
          <dd>{detail.confidence.toFixed(2)}</dd>
          <dt>Origin</dt>
          <dd>{utcStamp(detail.origin_time)}</dd>
          <dt>Updated</dt>
          <dd>{utcStamp(detail.last_updated_at)}</dd>
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
          </>
        ) : null}
      </div>
    </section>
  );
}
