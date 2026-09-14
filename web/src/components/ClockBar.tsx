import type { MapClock } from "../map/useMapClock";
import { msClock } from "./format";

interface Props {
  clock: MapClock;
}

/**
 * The one place the map time can be changed. Scrubbing is clearly marked so a
 * replayed position is never mistaken for the present.
 */
export function ClockBar({ clock }: Props): React.JSX.Element {
  const span = clock.windowEndMs - clock.windowStartMs;
  const position = span > 0 ? (clock.displayMs - clock.windowStartMs) / span : 1;

  return (
    <footer className={`clockbar ${clock.mode === "scrub" ? "solid" : "glass"}`}>
      <div>
        <div className="clock-label">{clock.mode === "live" ? "Live" : "Replay"}</div>
        <div className="clock-time" style={{ color: clock.mode === "scrub" ? "var(--warn)" : undefined }}>
          {msClock(clock.displayMs)}
        </div>
      </div>

      <div className="scrub">
        <span className="clock-label">{msClock(clock.windowStartMs)}</span>
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
