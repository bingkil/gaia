import { useState } from "react";
import { api } from "../api/client";
import type { WatchArea } from "../api/types";

interface Props {
  watchAreas: WatchArea[];
  location: { longitude: number; latitude: number } | null;
  onChanged: () => void;
}

/** The circle ring is symmetric around its centre, so its bbox midpoint is the centre. */
function centerOf(geometry: GeoJSON.Geometry): { longitude: number; latitude: number } {
  const ring = geometry.type === "Polygon" ? (geometry.coordinates[0] ?? []) : [];
  const lons = ring.map((p) => p[0] ?? 0);
  const lats = ring.map((p) => p[1] ?? 0);
  return {
    longitude: (Math.min(...lons) + Math.max(...lons)) / 2,
    latitude: (Math.min(...lats) + Math.max(...lats)) / 2,
  };
}

export function WatchAreaPanel({ watchAreas, location, onChanged }: Props): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [radiusKm, setRadiusKm] = useState(300);
  const [minMagnitude, setMinMagnitude] = useState(4.5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = (area: WatchArea): void => {
    setEditingId(area.id);
    setName(area.name);
    setRadiusKm(area.radius_km);
    setMinMagnitude(area.min_magnitude);
    setError(null);
  };

  const cancelEdit = (): void => {
    setEditingId(null);
    setName("");
    setError(null);
  };

  const submit = (): void => {
    if (name.trim() === "") return;

    const editing = editingId ? watchAreas.find((a) => a.id === editingId) : undefined;
    const target = editing ? centerOf(editing.geometry) : location;
    if (!target) return;

    setBusy(true);
    setError(null);
    const body = {
      name: name.trim(),
      longitude: target.longitude,
      latitude: target.latitude,
      radiusKm,
      minMagnitude,
    };
    const request = editing ? api.updateWatchArea(editing.id, body) : api.createWatchArea(body);

    request
      .then(() => {
        setName("");
        setEditingId(null);
        onChanged();
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "could not save the watch area"),
      )
      .finally(() => setBusy(false));
  };

  const remove = (area: WatchArea): void => {
    setError(null);
    api
      .deleteWatchArea(area.id)
      .then(() => {
        if (editingId === area.id) cancelEdit();
        onChanged();
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "could not delete the watch area"),
      );
  };

  const showForm = editingId !== null || location !== null;

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
                onClick={() => startEdit(area)}
                type="button"
                aria-label={`Edit ${area.name}`}
              >
                ✎
              </button>
              <button
                className="btn ghost"
                onClick={() => remove(area)}
                type="button"
                aria-label={`Delete ${area.name}`}
              >
                ✕
              </button>
            </div>
          ))}

          <div style={{ borderTop: "1px solid var(--glass-border)", margin: "10px 0" }} />

          {error ? <p className="legend-note">{error}</p> : null}

          {showForm ? (
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
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  className="btn"
                  onClick={submit}
                  disabled={busy || name.trim() === ""}
                  type="button"
                >
                  {editingId ? "Save changes" : "Add at current location"}
                </button>
                {editingId ? (
                  <button className="btn ghost" onClick={cancelEdit} type="button">
                    Cancel
                  </button>
                ) : null}
              </div>
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
