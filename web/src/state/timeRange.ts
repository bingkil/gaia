import type { TimeZonePref } from "./timeZone";

export type TimeRange =
  | { kind: "rolling"; hours: number }
  | { kind: "day"; from: string; to: string };

export const ROLLING_PRESETS = [1, 6, 24, 48, 168] as const;

export function rollingLabel(hours: number): string {
  return hours < 24 ? `${hours}h` : `${hours / 24}d`;
}

export const DEFAULT_RANGE: TimeRange = { kind: "rolling", hours: 48 };

/** The calendar day the user is in, which is what a date picker shows them. */
export function todayIn(zone: TimeZonePref): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

/**
 * The zone's UTC offset in minutes at a given instant, computed by formatting
 * the instant in that zone and re-reading the result as if it were UTC. This
 * is what handles daylight saving correctly for an arbitrary IANA zone.
 */
function offsetMinutesAt(zone: string, at: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(at);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const asUtc = Date.UTC(
    get("year"),
    get("month") - 1,
    get("day"),
    get("hour"),
    get("minute"),
    get("second"),
  );
  return Math.round((asUtc - at.getTime()) / 60_000);
}

function offsetSuffix(zone: string, at: Date): string {
  if (zone === "UTC") return "Z";
  const minutes = offsetMinutesAt(zone, at);
  const sign = minutes >= 0 ? "+" : "-";
  const abs = Math.abs(minutes);
  const hh = String(Math.floor(abs / 60)).padStart(2, "0");
  const mm = String(abs % 60).padStart(2, "0");
  return `${sign}${hh}:${mm}`;
}

/**
 * A picked date means midnight to midnight where the user is, not in UTC, so
 * the bounds are built in the display zone and sent as instants.
 */
export function rangeParams(
  range: TimeRange,
  zone: TimeZonePref,
): { sinceHours?: number; since?: string; until?: string } {
  if (range.kind === "rolling") return { sinceHours: range.hours };

  const fromGuess = new Date(`${range.from}T00:00:00.000Z`);
  const toGuess = new Date(`${range.to}T23:59:59.999Z`);
  const since = new Date(`${range.from}T00:00:00.000${offsetSuffix(zone, fromGuess)}`);
  const until = new Date(`${range.to}T23:59:59.999${offsetSuffix(zone, toGuess)}`);
  return { since: since.toISOString(), until: until.toISOString() };
}

export function rangeSummary(range: TimeRange): string {
  if (range.kind === "rolling") return `last ${rollingLabel(range.hours)}`;
  return range.from === range.to ? range.from : `${range.from} to ${range.to}`;
}

/**
 * The data day to show imagery for. Satellite days are UTC, so a picked day
 * ahead of it would ask for imagery that has not been flown yet.
 */
export function imageryDate(range: TimeRange): string {
  const utcToday = new Date().toISOString().slice(0, 10);
  if (range.kind !== "day") return utcToday;
  return range.to < utcToday ? range.to : utcToday;
}
