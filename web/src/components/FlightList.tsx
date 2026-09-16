import { airlineFromCallsign } from "../map/flights";
import type { FlightFeatureProperties } from "../map/flights";

interface Props {
  flights: GeoJSON.FeatureCollection;
  enabled: boolean;
  status: { loading: boolean; error: string | null };
}

function speedText(velocityMs: number | null): string {
  return typeof velocityMs === "number" ? `${Math.round(velocityMs * 3.6)} km/h` : "—";
}

function altitudeText(altitudeM: number | null): string {
  return typeof altitudeM === "number" ? `${Math.round(altitudeM)} m` : "—";
}

/**
 * The map already scopes `flights` to the current viewport bbox each poll, so
 * this list is "in view" by construction — no separate toggle needed.
 * Sorted alphabetically by callsign (falling back to the ICAO24 hex code for
 * aircraft not broadcasting one) since that is stable and easy to scan; swap
 * the comparator below if a different order turns out to be more useful.
 */
export function FlightList({ flights, enabled, status }: Props): React.JSX.Element {
  const rows = flights.features
    .map((feature) => feature.properties as unknown as FlightFeatureProperties)
    .sort((a, b) => (a.callsign ?? a.icao24).localeCompare(b.callsign ?? b.icao24));

  return (
    <div className="panel-body">
      {status.error ? <p className="list-error">{status.error}</p> : null}
      {!enabled ? (
        <p className="empty">Turn on the Flights layer to see aircraft in the current view.</p>
      ) : rows.length === 0 ? (
        <p className="empty">
          {status.loading ? "Loading flights…" : "No aircraft in the current map view."}
        </p>
      ) : (
        rows.map((row) => (
          <div key={row.icao24} className="flight-row">
            <div className="flight-id">
              <div className="flight-callsign">{row.callsign ?? row.icao24}</div>
              {airlineFromCallsign(row.callsign) ? (
                <div className="flight-airline">{airlineFromCallsign(row.callsign)}</div>
              ) : null}
            </div>
            <div className="flight-meta">
              {altitudeText(row.altitudeM)} · {speedText(row.velocityMs)}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
