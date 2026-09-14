import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type TimeZonePref = "UTC" | "LOCAL";

const STORAGE_KEY = "gaia.timeZone";

/** The device zone, resolved once. Shown so the choice is never a guess. */
export const DEVICE_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

function load(): TimeZonePref {
  return localStorage.getItem(STORAGE_KEY) === "LOCAL" ? "LOCAL" : "UTC";
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
