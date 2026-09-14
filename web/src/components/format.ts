/**
 * Display helpers.
 *
 * Hazard data is issued in UTC and aviation products are read in UTC, so no
 * absolute time is ever rendered without saying which zone it is in.
 */

import type { TimeZonePref } from "../state/timeZone";

export function utcTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().slice(11, 19) + "Z";
}

export function utcStamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toISOString().slice(0, 19).replace("T", " ") + "Z";
}

export function msClock(ms: number): string {
  return new Date(ms).toISOString().slice(11, 19) + "Z";
}

// Formatters are keyed by zone and cached: a picker can select any of the
// ~400 IANA zones, and building a new one on every call would be wasteful.
const timeFormatCache = new Map<string, Intl.DateTimeFormat>();
function timeFormatFor(zone: string): Intl.DateTimeFormat {
  let format = timeFormatCache.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZoneName: "shortOffset",
      timeZone: zone,
    });
    timeFormatCache.set(zone, format);
  }
  return format;
}

const stampFormatCache = new Map<string, Intl.DateTimeFormat>();
function stampFormatFor(zone: string): Intl.DateTimeFormat {
  let format = stampFormatCache.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      timeZoneName: "shortOffset",
      timeZone: zone,
    });
    stampFormatCache.set(zone, format);
  }
  return format;
}

function localise(value: Date, format: Intl.DateTimeFormat): string {
  // Normalised because the locale separator varies and the offset must read
  // as part of the time rather than as a stray token.
  return format.format(value).replace(/,/g, "");
}

export function timeIn(zone: TimeZonePref, iso: string | null | undefined): string {
  if (zone === "UTC") return utcTime(iso);
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return localise(date, timeFormatFor(zone));
}

export function stampIn(zone: TimeZonePref, iso: string | null | undefined): string {
  if (zone === "UTC") return utcStamp(iso);
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return localise(date, stampFormatFor(zone));
}

export function clockIn(zone: TimeZonePref, ms: number): string {
  return zone === "UTC" ? msClock(ms) : localise(new Date(ms), timeFormatFor(zone));
}

const dayKeyUtc = new Intl.DateTimeFormat("en-CA", {
  timeZone: "UTC",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const dayKeyCache = new Map<string, Intl.DateTimeFormat>();
function dayKeyFor(zone: string): Intl.DateTimeFormat {
  let format = dayKeyCache.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone: zone,
    });
    dayKeyCache.set(zone, format);
  }
  return format;
}

const shortFormatCache = new Map<string, Intl.DateTimeFormat>();
function shortFormatFor(zone: string): Intl.DateTimeFormat {
  let format = shortFormatCache.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-CA", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZoneName: "shortOffset",
      timeZone: zone,
    });
    shortFormatCache.set(zone, format);
  }
  return format;
}

/**
 * List times carry their date unless they are from today, because the list
 * spans days and a bare time reads as now. Seconds are dropped once a date is
 * needed; the detail panel keeps full precision.
 */
export function eventTime(zone: TimeZonePref, iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";

  const dayKey = zone === "UTC" ? dayKeyUtc : dayKeyFor(zone);
  const day = dayKey.format(date);
  const today = dayKey.format(new Date());

  if (day === today) return timeIn(zone, iso);
  if (day.slice(0, 4) !== today.slice(0, 4)) return stampIn(zone, iso);

  if (zone === "UTC") {
    const stamp = date.toISOString();
    return `${stamp.slice(5, 10)} ${stamp.slice(11, 16)}Z`;
  }
  return localise(date, shortFormatFor(zone));
}

export function ago(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "age unknown";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

/**
 * Basemap imagery ages in days, months and years rather than the
 * minutes-to-days span `ago()` covers, so it gets its own coarser scale.
 */
export function longAgo(seconds: number): string {
  if (seconds < 0) return "today";
  const days = seconds / 86_400;
  if (days < 1) return "today";
  if (days < 30) return `${Math.round(days)}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return `${(days / 365).toFixed(1)}y ago`;
}

export function countdown(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return minutes > 0 ? `${minutes}m ${String(rest).padStart(2, "0")}s` : `${rest}s`;
}

export function km(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 100 ? `${Math.round(value)} km` : `${value.toFixed(1)} km`;
}

export function magnitudeText(magnitude: number | null | undefined): string {
  return magnitude === null || magnitude === undefined ? "—" : magnitude.toFixed(1);
}

/** Satellite detections carry no place name, so the position is the identity. */
export function coordText(
  longitude: number | null | undefined,
  latitude: number | null | undefined,
): string | null {
  if (longitude === null || longitude === undefined) return null;
  if (latitude === null || latitude === undefined) return null;
  const ns = latitude >= 0 ? "N" : "S";
  const ew = longitude >= 0 ? "E" : "W";
  return `${Math.abs(latitude).toFixed(2)}°${ns} ${Math.abs(longitude).toFixed(2)}°${ew}`;
}

/** Peak fire radiative power, the strongest single cue that heat is a fire. */
export function frpText(megawatts: number | null | undefined): string | null {
  if (megawatts === null || megawatts === undefined) return null;
  return megawatts >= 1000
    ? `${(megawatts / 1000).toFixed(1)} GW peak`
    : `${Math.round(megawatts)} MW peak`;
}
