import type { HazardEvent } from "../api/types";
import { severityColour, severityOfEvent } from "../map/severity";
import { ago, magnitudeText, utcTime } from "./format";

interface Props {
  events: HazardEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function primaryText(event: HazardEvent): string {
  if (event.hazard_type === "EARTHQUAKE") return event.summary.place ?? "Unknown region";
  return event.summary.volcano_name ?? event.summary.place ?? "Unnamed volcano";
}

function secondaryText(event: HazardEvent): string {
  if (event.hazard_type === "VOLCANO" && event.summary.alert_level) {
    return event.summary.alert_level;
  }
  if (event.hazard_type === "EARTHQUAKE" && event.summary.depth_km !== null) {
    return `${Math.round(event.summary.depth_km)} km deep`;
  }
  return event.hazard_type.toLowerCase();
}

export function EventList({ events, selectedId, onSelect }: Props): React.JSX.Element {
  return (
    <section className="panel glass grow">
      <header className="panel-head">
        <span className="panel-title">Active events</span>
        <span className="tag">{events.length}</span>
      </header>

      <div className="panel-body">
        {events.length === 0 ? (
          <p className="empty">
            No events in the active window.
            <br />
            Feeds may still be warming up.
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
                onClick={() => onSelect(event.id)}
                onKeyDown={(keyEvent) => {
                  if (keyEvent.key === "Enter" || keyEvent.key === " ") onSelect(event.id);
                }}
                role="button"
                tabIndex={0}
              >
                <div className="event-mag" style={{ color: severityColour(severity) }}>
                  {event.hazard_type === "EARTHQUAKE"
                    ? magnitudeText(event.summary.magnitude)
                    : event.hazard_type === "VOLCANO"
                      ? "▲"
                      : "◆"}
                </div>

                <div style={{ minWidth: 0 }}>
                  <div className="event-place">{primaryText(event)}</div>
                  <div className="event-meta">
                    <span>{secondaryText(event)}</span>
                    <span>·</span>
                    <span>{event.label}</span>
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div className="event-time">{utcTime(event.origin_time)}</div>
                  <div className="event-time">{ago(event.dataAgeSeconds)}</div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
