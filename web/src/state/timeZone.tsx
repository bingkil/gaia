import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/** "UTC" or any IANA zone name, e.g. "Asia/Jakarta". */
export type TimeZonePref = string;

const STORAGE_KEY = "gaia.timeZone";

/** The device zone, resolved once. Shown so the choice is never a guess. */
export const DEVICE_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** Every zone the runtime knows, for a proper picker instead of just UTC vs. the device zone. */
export const TIME_ZONES: string[] =
  typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : [DEVICE_ZONE];

const KNOWN_ZONES = new Set(["UTC", ...TIME_ZONES]);

function load(): TimeZonePref {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "LOCAL") return DEVICE_ZONE; // migrate the old sentinel value
  return stored && KNOWN_ZONES.has(stored) ? stored : "UTC";
}

interface Value {
  zone: TimeZonePref;
  setZone: (zone: TimeZonePref) => void;
}

const TimeZoneContext = createContext<Value>({ zone: "UTC", setZone: () => {} });

export function TimeZoneProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [zone, setZoneState] = useState<TimeZonePref>(load);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, zone);
  }, [zone]);

  const setZone = useCallback((next: TimeZonePref) => setZoneState(next), []);
  const value = useMemo(() => ({ zone, setZone }), [zone, setZone]);

  return <TimeZoneContext.Provider value={value}>{children}</TimeZoneContext.Provider>;
}

export function useTimeZone(): Value {
  return useContext(TimeZoneContext);
}
