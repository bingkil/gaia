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
  const now = new Date();
  if (zone === "UTC") return now.toISOString().slice(0, 10);
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
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

  const suffix = zone === "UTC" ? "Z" : "";
  const since = new Date(`${range.from}T00:00:00.000${suffix}`);
  const until = new Date(`${range.to}T23:59:59.999${suffix}`);
  return { since: since.toISOString(), until: until.toISOString() };
}

export function rangeSummary(range: TimeRange): string {
  if (range.kind === "rolling") return `last ${rollingLabel(range.hours)}`;
  return range.from === range.to ? range.from : `${range.from} to ${range.to}`;
}
