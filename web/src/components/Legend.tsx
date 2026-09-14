import { useState } from "react";
import type { Meta } from "../api/types";
import { SEVERITY_COLOURS } from "../map/severity";

const SEVERITY_LABELS = ["M <3", "M 3–4.5", "M 4.5–6", "M 6–7", "M 7+"];

export function Legend({ meta }: { meta: Meta | null }): React.JSX.Element {
  const [open, setOpen] = useState(true);

  return (
    <section className="panel glass">
      <header className="panel-head">
        <span className="panel-title">Legend &amp; sources</span>
        <button className="btn ghost" onClick={() => setOpen(!open)} type="button">
          {open ? "−" : "+"}
        </button>
      </header>

      {open ? (
        <div className="panel-body pad">
          {SEVERITY_COLOURS.map((colour, index) => (
            <div className="legend-row" key={colour}>
              <i
                className="legend-swatch"
                style={{ background: colour, borderRadius: "50%" }}
              />
              {SEVERITY_LABELS[index]}
            </div>
          ))}

          <div className="legend-row" style={{ marginTop: 6 }}>
            <span className="legend-swatch" style={{ textAlign: "center" }}>
              ▲
            </span>
            Volcano
          </div>
          <div className="legend-row">
            <span className="legend-swatch" style={{ textAlign: "center" }}>
              ◆
            </span>
            Ash
          </div>
          <div className="legend-row">
            <i className="legend-swatch" style={{ background: "#b388ff", opacity: 0.6 }} />
            Ash observed
          </div>
          <div className="legend-row">
            <i
              className="legend-swatch"
              style={{ border: "1px dashed #6c5ce7", background: "rgba(108,92,231,.15)" }}
            />
            Ash forecast
          </div>
          <div className="legend-row">
            <i className="legend-swatch" style={{ border: "1px solid #00a5d4" }} />
            P wavefront (modelled)
          </div>
          <div className="legend-row">
            <i className="legend-swatch" style={{ border: "2px solid #f2681c" }} />
            S wavefront (modelled)
          </div>

          {meta ? (
            <p className="disclaimer" style={{ padding: "10px 0 0" }}>
              {meta.disclaimer}
              <br />
              <br />
              {meta.attribution.filter(Boolean).join(" · ")}
              <br />
              Basemap © CARTO, © OpenStreetMap contributors.
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
