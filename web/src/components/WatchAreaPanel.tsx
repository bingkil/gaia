import { useState } from "react";
import { api } from "../api/client";
import type { WatchArea } from "../api/types";

interface Props {
  watchAreas: WatchArea[];
  location: { longitude: number; latitude: number } | null;
  onChanged: () => void;
}

export function WatchAreaPanel({ watchAreas, location, onChanged }: Props): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [radiusKm, setRadiusKm] = useState(300);
  const [minMagnitude, setMinMagnitude] = useState(4.5);
  const [busy, setBusy] = useState(false);

  const submit = (): void => {
    if (!location || name.trim() === "") return;
    setBusy(true);
    api
      .createWatchArea({
        name: name.trim(),
        longitude: location.longitude,
        latitude: location.latitude,
        radiusKm,
        minMagnitude,
      })
      .then(() => {
        setName("");
        onChanged();
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="panel glass">
      <header className="panel-head">
        <span className="panel-title">Watch areas</span>
        <button className="btn ghost" onClick={() => setOpen(!open)} type="button">
          {open ? "−" : "+"}
        </button>
      </header>

      {open ? (
        <div className="panel-body pad">
          {watchAreas.map((area) => (
            <div
              key={area.id}
              style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 0" }}
            >
              <span style={{ flex: 1, fontSize: 11 }}>{area.name}</span>
              <span style={{ fontSize: 10, color: "var(--fg-faint)", fontFamily: "var(--mono)" }}>
                {Math.round(area.radius_km)} km · M{area.min_magnitude}
              </span>
              <button
                className="btn ghost"
                onClick={() => api.deleteWatchArea(area.id).then(onChanged)}
                type="button"
                aria-label={`Delete ${area.name}`}
              >
                ✕
              </button>
            </div>
          ))}

          <div style={{ borderTop: "1px solid var(--glass-border)", margin: "10px 0" }} />

          {location ? (
            <>
              <div className="field">
                <label htmlFor="watch-name">Name</label>
                <input
                  id="watch-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Home"
                />
              </div>
              <div className="field-row">
                <div className="field">
                  <label htmlFor="watch-radius">Radius km</label>
                  <input
                    id="watch-radius"
                    type="number"
                    min={1}
                    max={2000}
                    value={radiusKm}
                    onChange={(event) => setRadiusKm(Number(event.target.value))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="watch-mag">Min M</label>
                  <input
                    id="watch-mag"
                    type="number"
                    min={0}
                    max={10}
                    step={0.1}
                    value={minMagnitude}
                    onChange={(event) => setMinMagnitude(Number(event.target.value))}
                  />
                </div>
              </div>
              <button
                className="btn"
                onClick={submit}
                disabled={busy || name.trim() === ""}
                type="button"
              >
                Add at current location
              </button>
            </>
          ) : (
            <p className="empty" style={{ padding: "6px 0" }}>
              Set a location first.
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}
