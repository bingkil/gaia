import { useState } from "react";
import type { HazardEvent, HazardType } from "../api/types";
import { FLAME_PATH, SHAPE_BY_HAZARD, VOLCANO_PATH, severityColour, severityOfEvent } from "../map/severity";
import {
  ROLLING_PRESETS,
  type TimeRange,
  rangeSummary,
  rollingLabel,
  todayIn,
} from "../state/timeRange";
import { useTimeZone } from "../state/timeZone";
import { ago, coordText, eventTime, frpText, magnitudeText } from "./format";
import { ProvenanceTag } from "./ProvenanceBadge";

interface Props {
  events: HazardEvent[];
  selectedId: string | null;
  onSelect: (event: HazardEvent) => void;
  inView: boolean;
  range: TimeRange;
  onRange: (range: TimeRange) => void;
}

/** Reuses the map's shape cue so a row and its marker read as the same thing. */
const DIAMOND_POINTS = "6,0.4 11.6,6 6,11.6 0.4,6";

export function HazardIcon({ hazardType }: { hazardType: HazardType }): React.JSX.Element {
  const shape = SHAPE_BY_HAZARD[hazardType];
  return (
    <svg
      className="hazard-icon"
      viewBox="0 0 12 12"
      role="img"
      aria-label={hazardType.toLowerCase()}
    >
      {shape === "circle" ? (
        <circle cx="6" cy="6" r="4.8" fill="currentColor" />
      ) : shape === "flame" ? (
        <path d={FLAME_PATH} fill="currentColor" />
      ) : shape === "volcano" ? (
        <path d={VOLCANO_PATH} fill="currentColor" />
      ) : (
        <polygon points={DIAMOND_POINTS} fill="currentColor" />
      )}
    </svg>
  );
}

function primaryText(event: HazardEvent): string {
  if (event.hazard_type === "EARTHQUAKE") return event.summary.place ?? "Unknown region";
  if (event.hazard_type === "WILDFIRE") {
    return event.summary.place ?? coordText(event.longitude, event.latitude) ?? "Unnamed fire";
  }
  return event.summary.volcano_name ?? event.summary.place ?? "Unnamed volcano";
}

function secondaryText(event: HazardEvent): string {
  if (event.hazard_type === "VOLCANO" && event.summary.alert_level) {
    return event.summary.alert_level;
  }
  if (event.hazard_type === "EARTHQUAKE" && event.summary.depth_km !== null) {
    return `${Math.round(event.summary.depth_km)} km deep`;
  }
  if (event.hazard_type === "WILDFIRE") {
    const { detection_count, max_frp_mw, alert_level } = event.summary;
    const parts = [
      alert_level,
      detection_count === null ? null : `${detection_count} detections`,
      frpText(max_frp_mw),
    ].filter(Boolean);
    if (parts.length > 0) return parts.join(" · ");
  }
  return event.hazard_type.toLowerCase();
}

export function EventList({
  events,
  selectedId,
  onSelect,
  inView,
  range,
  onRange,
}: Props): React.JSX.Element {
  const { zone } = useTimeZone();
  const [dates, setDates] = useState(range.kind === "day");
  const today = todayIn(zone);
  const from = range.kind === "day" ? range.from : today;
  const to = range.kind === "day" ? range.to : today;

  return (
    <>
      <div className="range-bar">
        {ROLLING_PRESETS.map((hours) => (
          <button
            key={hours}
            className={`btn${range.kind === "rolling" && range.hours === hours ? " on" : ""}`}
            onClick={() => {
              setDates(false);
              onRange({ kind: "rolling", hours });
            }}
            type="button"
            aria-pressed={range.kind === "rolling" && range.hours === hours}
          >
            {rollingLabel(hours)}
          </button>
        ))}
        <button
          className={`btn${range.kind === "day" ? " on" : ""}`}
          onClick={() => {
            const next = !dates;
            setDates(next);
            if (next) onRange({ kind: "day", from: today, to: today });
            else onRange({ kind: "rolling", hours: 48 });
          }}
          type="button"
          aria-pressed={dates}
          title="Pick calendar dates instead of a rolling window"
        >
          Dates
        </button>
      </div>

      {dates ? (
        <div className="range-bar">
          <input
            type="date"
            className="date-input"
            value={from}
            max={to}
            onChange={(event) => onRange({ kind: "day", from: event.target.value, to })}
            aria-label="From date"
          />
          <span className="clock-label">to</span>
          <input
            type="date"
            className="date-input"
            value={to}
            min={from}
            max={today}
            onChange={(event) => onRange({ kind: "day", from, to: event.target.value })}
            aria-label="To date"
          />
        </div>
      ) : null}

      <div className="panel-body">
        {events.length === 0 ? (
          <p className="empty">
            {inView ? (
              <>
                No events in the current map view.
                <br />
                Zoom out or switch back to the full list.
              </>
            ) : (
              <>
                No events in {rangeSummary(range)}.
                <br />
                Only what this machine has collected is stored, so older ranges may be thin.
              </>
            )}
          </p>
        ) : (
          events.map((event) => {
            const severity = severityOfEvent(event);
            return (
              <div
                key={event.id}
                className={[
                  "event-row",
                  event.id === selectedId ? "selected" : "",
                  event.state === "RETRACTED" ? "retracted" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() => onSelect(event)}
                onKeyDown={(keyEvent) => {
                  if (keyEvent.key === "Enter" || keyEvent.key === " ") onSelect(event);
                }}
                role="button"
                tabIndex={0}
              >
                <div className="event-mag" style={{ color: severityColour(severity) }}>
                  <HazardIcon hazardType={event.hazard_type} />
                  {event.hazard_type === "EARTHQUAKE" ? (
                    <span>{magnitudeText(event.summary.magnitude)}</span>
                  ) : null}
                </div>

                <div style={{ minWidth: 0 }}>
                  <div className="event-place">{primaryText(event)}</div>
                  <div className="event-meta">
                    <ProvenanceTag
                      provenanceClass={event.provenance_class}
                      label={event.label}
                      compact
                    />
                    <span>{secondaryText(event)}</span>
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div className="event-time">{eventTime(zone, event.origin_time)}</div>
                  <div className="event-time">{ago(event.dataAgeSeconds)}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
}
