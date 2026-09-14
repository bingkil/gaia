import type { AerialCapture } from "../map/imagery";
import type { Basemap } from "../map/MapView";
import { longAgo } from "./format";

interface Props {
  basemap: Basemap;
  /** GIBS is daily, so this is the UTC day whose imagery is on screen. */
  imageryDate: string;
  /** undefined while a lookup for the current view is in flight. */
  aerialCapture: AerialCapture | null | undefined;
}

function daySeconds(dateIso: string): number {
  return (Date.now() - new Date(`${dateIso}T00:00:00Z`).getTime()) / 1000;
}

export function ImageryAgeBadge({
  basemap,
  imageryDate,
  aerialCapture,
}: Props): React.JSX.Element | null {
  if (basemap === "dark") return null;

  if (basemap === "live") {
    return (
      <div
        className="imagery-age"
        title="Daily VIIRS NOAA-21 true-colour pass used for this basemap"
      >
        Satellite: {imageryDate} UTC · {longAgo(daySeconds(imageryDate))}
      </div>
    );
  }

  if (aerialCapture === undefined) {
    return <div className="imagery-age">Aerial: checking capture date…</div>;
  }
  if (aerialCapture === null) {
    return <div className="imagery-age">Aerial: capture date unavailable here</div>;
  }
  return (
    <div
      className="imagery-age"
      title={aerialCapture.source ? `Source: ${aerialCapture.source}` : undefined}
    >
      Aerial: {aerialCapture.iso} · {longAgo(daySeconds(aerialCapture.iso))}
    </div>
  );
}
