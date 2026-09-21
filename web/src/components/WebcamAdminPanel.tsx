import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import type { HazardType, Webcam } from "../api/types";
import { WebcamPlayer } from "./WebcamPlayer";

interface Props {
  location: { longitude: number; latitude: number } | null;
  onFocus: (webcam: Webcam) => void;
  onClose: () => void;
}

const HAZARDS: { value: HazardType; label: string }[] = [
  { value: "EARTHQUAKE", label: "Quake" },
  { value: "VOLCANO", label: "Volcano" },
  { value: "ASH", label: "Ash" },
  { value: "WILDFIRE", label: "Fire" },
];

interface FormState {
  name: string;
  latitude: string;
  longitude: string;
  hazardTypes: Set<HazardType>;
  streamUrl: string;
  imageUrl: string;
  thumbnailUrl: string;
  sourceUrl: string;
  attribution: string;
  enabled: boolean;
}

function emptyForm(location: { longitude: number; latitude: number } | null): FormState {
  return {
    name: "",
    latitude: location ? String(location.latitude) : "",
    longitude: location ? String(location.longitude) : "",
    hazardTypes: new Set(),
    streamUrl: "",
    imageUrl: "",
    thumbnailUrl: "",
    sourceUrl: "",
    attribution: "",
    enabled: true,
  };
}

function formFromWebcam(webcam: Webcam): FormState {
  return {
    name: webcam.name,
    latitude: String(webcam.latitude),
    longitude: String(webcam.longitude),
    hazardTypes: new Set(webcam.hazard_types),
    streamUrl: webcam.stream_url ?? "",
    imageUrl: webcam.image_url ?? "",
    thumbnailUrl: webcam.thumbnail_url ?? "",
    sourceUrl: webcam.source_url ?? "",
    attribution: webcam.attribution ?? "",
    enabled: webcam.enabled,
  };
}

function StatusDot({ status }: { status: string }): React.JSX.Element {
  return <span className={`dot ${status}`} title={status.toLowerCase()} />;
}

export function WebcamAdminPanel({ location, onFocus, onClose }: Props): React.JSX.Element {
  const [webcams, setWebcams] = useState<Webcam[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<FormState>(() => emptyForm(location));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewWebcam, setPreviewWebcam] = useState<Webcam | null>(null);

  useEffect(() => {
    if (!previewWebcam) return;
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setPreviewWebcam(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [previewWebcam]);

  const load = (): void => {
    api
      .webcams()
      .then((r) => setWebcams(r.webcams))
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "could not load webcams"),
      );
  };

  useEffect(load, []);

  const startCreate = (): void => {
    setEditingId(null);
    setForm(emptyForm(location));
    setShowForm(true);
    setError(null);
  };

  const startEdit = (webcam: Webcam): void => {
    setEditingId(webcam.id);
    setForm(formFromWebcam(webcam));
    setShowForm(true);
    setError(null);
  };

  const cancelForm = (): void => {
    setShowForm(false);
    setEditingId(null);
    setError(null);
  };

  const toggleHazard = (hazard: HazardType): void => {
    setForm((prev) => {
      const next = new Set(prev.hazardTypes);
      if (next.has(hazard)) next.delete(hazard);
      else next.add(hazard);
      return { ...prev, hazardTypes: next };
    });
  };

  const submit = (): void => {
    const latitude = Number(form.latitude);
    const longitude = Number(form.longitude);
    if (form.name.trim() === "" || form.hazardTypes.size === 0) return;
    if (Number.isNaN(latitude) || Number.isNaN(longitude)) return;

    setBusy(true);
    setError(null);
    const body = {
      name: form.name.trim(),
      latitude,
      longitude,
      hazardTypes: [...form.hazardTypes],
      streamUrl: form.streamUrl.trim() || null,
      imageUrl: form.imageUrl.trim() || null,
      thumbnailUrl: form.thumbnailUrl.trim() || null,
      sourceUrl: form.sourceUrl.trim() || null,
      attribution: form.attribution.trim() || null,
      enabled: form.enabled,
    };
    const request = editingId ? api.updateWebcam(editingId, body) : api.createWebcam(body);

    request
      .then(() => {
        setShowForm(false);
        setEditingId(null);
        load();
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "could not save the webcam"),
      )
      .finally(() => setBusy(false));
  };

  const remove = (webcam: Webcam): void => {
    setError(null);
    api
      .deleteWebcam(webcam.id)
      .then(() => {
        if (editingId === webcam.id) cancelForm();
        load();
      })
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "could not delete the webcam"),
      );
  };

  const recheck = (webcam: Webcam): void => {
    api
      .recheckWebcam(webcam.id)
      .then((updated) => setWebcams((prev) => prev.map((w) => (w.id === updated.id ? updated : w))))
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : "could not recheck the webcam"),
      );
  };

  return (
    <section className="panel glass">
      <header className="panel-head">
        <span className="panel-title">Webcams</span>
        <button className="btn ghost" onClick={onClose} type="button" aria-label="Close">
          ✕
        </button>
      </header>

      <div className="panel-body pad">
        {webcams.length === 0 && !showForm ? (
          <p className="empty">
            No webcams yet. Public hazard cameras rarely expose a stable direct link, so add ones
            you have verified yourself.
          </p>
        ) : (
          webcams.map((webcam) => (
            <div key={webcam.id}>
              <div
                className="webcam-row clickable"
                onClick={() => onFocus(webcam)}
                title="Show this place on the map"
              >
                <div className="webcam-row-main">
                  <span className="webcam-row-name">{webcam.name}</span>
                  <span className="webcam-row-tags">
                    {webcam.hazard_types.map((h) => (
                      <span key={h} className="tag">
                        {h}
                      </span>
                    ))}
                  </span>
                </div>
                <div className="webcam-row-status">
                  {webcam.stream_url ? (
                    <span title="Live stream">
                      <StatusDot status={webcam.stream_status} /> stream
                    </span>
                  ) : null}
                  {webcam.image_url ? (
                    <span title="Snapshot image">
                      <StatusDot status={webcam.image_status} /> image
                    </span>
                  ) : null}
                  {webcam.source_url ? (
                    <a
                      href={webcam.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(event) => event.stopPropagation()}
                    >
                      Source ↗
                    </a>
                  ) : null}
                </div>
                <div className="webcam-row-actions">
                  <button
                    className="btn ghost"
                    onClick={(event) => {
                      event.stopPropagation();
                      setPreviewWebcam(webcam);
                    }}
                    type="button"
                    aria-label={`Preview ${webcam.name}`}
                    title="Preview"
                  >
                    👁
                  </button>
                  <button
                    className="btn ghost"
                    onClick={(event) => {
                      event.stopPropagation();
                      recheck(webcam);
                    }}
                    type="button"
                    aria-label={`Recheck ${webcam.name}`}
                    title="Recheck now"
                  >
                    ↻
                  </button>
                  <button
                    className="btn ghost"
                    onClick={(event) => {
                      event.stopPropagation();
                      startEdit(webcam);
                    }}
                    type="button"
                    aria-label={`Edit ${webcam.name}`}
                  >
                    ✎
                  </button>
                  <button
                    className="btn ghost"
                    onClick={(event) => {
                      event.stopPropagation();
                      remove(webcam);
                    }}
                    type="button"
                    aria-label={`Delete ${webcam.name}`}
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          ))
        )}

        <div style={{ borderTop: "1px solid var(--glass-border)", margin: "10px 0" }} />

        {error ? <p className="legend-note">{error}</p> : null}

        {showForm ? (
          <>
            <div className="field">
              <label htmlFor="webcam-name">Name</label>
              <input
                id="webcam-name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Overlook camera"
              />
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="webcam-lat">Latitude</label>
                <input
                  id="webcam-lat"
                  type="number"
                  value={form.latitude}
                  onChange={(event) => setForm({ ...form, latitude: event.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="webcam-lon">Longitude</label>
                <input
                  id="webcam-lon"
                  type="number"
                  value={form.longitude}
                  onChange={(event) => setForm({ ...form, longitude: event.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>Hazard types</label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                {HAZARDS.map((hazard) => (
                  <label
                    key={hazard.value}
                    style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11 }}
                  >
                    <input
                      type="checkbox"
                      checked={form.hazardTypes.has(hazard.value)}
                      onChange={() => toggleHazard(hazard.value)}
                    />
                    {hazard.label}
                  </label>
                ))}
              </div>
            </div>
            <div className="field">
              <label htmlFor="webcam-stream">Stream URL (live video, e.g. .m3u8)</label>
              <input
                id="webcam-stream"
                value={form.streamUrl}
                onChange={(event) => setForm({ ...form, streamUrl: event.target.value })}
                placeholder="https://…/stream.m3u8"
              />
            </div>
            <div className="field">
              <label htmlFor="webcam-image">Image URL (refreshing snapshot)</label>
              <input
                id="webcam-image"
                value={form.imageUrl}
                onChange={(event) => setForm({ ...form, imageUrl: event.target.value })}
                placeholder="https://…/latest.jpg"
              />
            </div>
            <div className="field">
              <label htmlFor="webcam-thumbnail">Thumbnail URL (static fallback)</label>
              <input
                id="webcam-thumbnail"
                value={form.thumbnailUrl}
                onChange={(event) => setForm({ ...form, thumbnailUrl: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="webcam-source">Source page URL</label>
              <input
                id="webcam-source"
                value={form.sourceUrl}
                onChange={(event) => setForm({ ...form, sourceUrl: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="webcam-attribution">Attribution</label>
              <input
                id="webcam-attribution"
                value={form.attribution}
                onChange={(event) => setForm({ ...form, attribution: event.target.value })}
              />
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, marginBottom: 9 }}>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
              />
              Enabled
            </label>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                className="btn"
                onClick={submit}
                disabled={busy || form.name.trim() === "" || form.hazardTypes.size === 0}
                type="button"
              >
                {editingId ? "Save changes" : "Add webcam"}
              </button>
              <button className="btn ghost" onClick={cancelForm} type="button">
                Cancel
              </button>
            </div>
          </>
        ) : (
          <button className="btn" onClick={startCreate} type="button">
            Add webcam
          </button>
        )}
      </div>

      {previewWebcam
        ? createPortal(
            <div className="modal-scrim" onClick={() => setPreviewWebcam(null)} role="presentation">
              <div
                className="modal solid webcam-modal"
                onClick={(event) => event.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-label={previewWebcam.name}
              >
                <header className="panel-head">
                  <span className="panel-title">{previewWebcam.name}</span>
                  <button
                    className="btn ghost"
                    onClick={() => setPreviewWebcam(null)}
                    type="button"
                    aria-label="Close"
                  >
                    ✕
                  </button>
                </header>
                <div className="modal-body webcam-modal-body">
                  <WebcamPlayer webcam={previewWebcam} />
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </section>
  );
}
