import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type ClockMode = "live" | "scrub";

export interface MapClock {
  /**
   * The authoritative time, in epoch milliseconds. Every animated layer reads
   * this and nothing else, so the wavefronts, the ash frames and the countdown
   * can never disagree about what "now" means.
   *
   * Read it inside the animation frame; do not cache it.
   */
  read: () => number;
  /** Throttled copy for React rendering. Never drive animation from this. */
  displayMs: number;
  mode: ClockMode;
  windowStartMs: number;
  windowEndMs: number;
  setScrubMs: (ms: number) => void;
  resumeLive: () => void;
}

export function useMapClock(windowHours: number): MapClock {
  const [displayMs, setDisplayMs] = useState(() => Date.now());
  const [mode, setMode] = useState<ClockMode>("live");
  const scrubRef = useRef<number | null>(null);

  const read = useCallback(() => scrubRef.current ?? Date.now(), []);

  useEffect(() => {
    const id = window.setInterval(() => setDisplayMs(read()), 250);
    return () => window.clearInterval(id);
  }, [read]);

  const setScrubMs = useCallback((ms: number) => {
    scrubRef.current = ms;
    setMode("scrub");
    setDisplayMs(ms);
  }, []);

  const resumeLive = useCallback(() => {
    scrubRef.current = null;
    setMode("live");
    setDisplayMs(Date.now());
  }, []);

  // Anchored to wall time, not to the scrub position, so dragging the handle
  // does not drag the window along with it.
  const windowEndMs = mode === "live" ? displayMs : Math.max(displayMs, Date.now());
  const windowStartMs = Date.now() - windowHours * 3_600_000;

  return useMemo(
    () => ({
      read,
      displayMs,
      mode,
      windowStartMs,
      windowEndMs,
      setScrubMs,
      resumeLive,
    }),
    [read, displayMs, mode, windowStartMs, windowEndMs, setScrubMs, resumeLive],
  );
}
