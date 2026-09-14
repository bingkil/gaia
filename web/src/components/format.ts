/** Display helpers. Times are shown in UTC because hazard data is issued in UTC. */

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

export function ago(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "age unknown";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
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
