import type { MapClock } from "../map/useMapClock";
import { useTimeZone } from "../state/timeZone";
import { clockIn, stampIn } from "./format";

interface Props {
  clock: MapClock;
  /** Set when the event filter no longer matches the window this clock spans. */
  note?: string | null;
}

/**
 * The one place the map time can be changed. Scrubbing is clearly marked so a
 * replayed position is never mistaken for the present.
 */
export function ClockBar({ clock, note }: Props): React.JSX.Element {
  const { zone } = useTimeZone();
  const span = clock.windowEndMs - clock.windowStartMs;
  const position = span > 0 ? (clock.displayMs - clock.windowStartMs) / span : 1;
  // A time-only label a whole number of days in the past is indistinguishable
  // from now, so a replayed position carries its date.
  const sameDay = Math.abs(Date.now() - clock.displayMs) < 12 * 3_600_000;

  return (
    <footer className={`clockbar ${clock.mode === "scrub" ? "solid" : "glass"}`}>
      <div>
        <div className="clock-label">{clock.mode === "live" ? "Live" : "Replay"}</div>
        <div className="clock-time" style={{ color: clock.mode === "scrub" ? "var(--warn)" : undefined }}>
          {sameDay
            ? clockIn(zone, clock.displayMs)
            : stampIn(zone, new Date(clock.displayMs).toISOString())}
        </div>
      </div>

      <div className="scrub">
        <span className="clock-label" title={stampIn(zone, new Date(clock.windowStartMs).toISOString())}>
          {`−${Math.round((Date.now() - clock.windowStartMs) / 3_600_000)}h`}
        </span>
        <input
          type="range"
          min={0}
          max={1000}
          value={Math.round(Math.min(1, Math.max(0, position)) * 1000)}
          onChange={(event) => {
            const fraction = Number(event.target.value) / 1000;
            clock.setScrubMs(clock.windowStartMs + fraction * span);
          }}
          aria-label="Map time"
        />
        <span className="clock-label">now</span>
      </div>

      {note ? <span className="tag">{note}</span> : null}

      <button
        className={`btn ${clock.mode === "live" ? "on" : ""}`}
        onClick={clock.resumeLive}
        disabled={clock.mode === "live"}
        type="button"
      >
        Return to live
      </button>
    </footer>
  );
}
