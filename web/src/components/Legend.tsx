import { Fragment, useState } from "react";
import type { Meta } from "../api/types";
import { FLAME_PATH, SEVERITY_COLOURS, VOLCANO_PATH } from "../map/severity";
import { PROVENANCE_MARKS, PROVENANCE_ORDER, ProvenanceTag } from "./ProvenanceBadge";

/** One row per ramp step, read against whichever hazard's column applies. */
const SEVERITY_SCALE = [
  { quake: "M <3", volcano: "—", ash: "—", fire: "—" },
  { quake: "M 3–4.5", volcano: "GREEN or none", ash: "—", fire: "satellite only" },
  { quake: "M 4.5–6", volcano: "YELLOW", ash: "—", fire: "YELLOW" },
  { quake: "M 6–7", volcano: "ORANGE", ash: "always", fire: "ORANGE" },
  { quake: "M 7+", volcano: "RED", ash: "—", fire: "RED" },
];

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
          <div className="legend-scale">
            <span />
            <span className="legend-scale-head">● quake</span>
            <span className="legend-scale-head">
              <svg className="legend-glyph" viewBox="0 0 12 12" aria-hidden="true">
                <path d={VOLCANO_PATH} fill="currentColor" />
              </svg>
              volcano
            </span>
            <span className="legend-scale-head">◆ ash</span>
            <span className="legend-scale-head">
              <svg className="legend-glyph" viewBox="0 0 12 12" aria-hidden="true">
                <path d={FLAME_PATH} fill="currentColor" />
              </svg>
              fire
            </span>
            {SEVERITY_COLOURS.map((colour, index) => (
              <Fragment key={colour}>
                <i className="legend-swatch" style={{ background: colour, borderRadius: "50%" }} />
                <span>{SEVERITY_SCALE[index]?.quake}</span>
                <span>{SEVERITY_SCALE[index]?.volcano}</span>
                <span>{SEVERITY_SCALE[index]?.ash}</span>
                <span>{SEVERITY_SCALE[index]?.fire}</span>
              </Fragment>
            ))}
          </div>
          <p className="legend-note">
            A step is a rank on that hazard&rsquo;s own scale, so the same colour across two
            shapes is not the same danger. A volcano&rsquo;s swatch is this ranking, not the
            agency&rsquo;s own colour code — an agency RED is drawn magenta here. Ash is always
            drawn at step 4; that is a placeholder, not a measurement. A fire at step 2 carries no
            agency grading at all: it is a cluster of satellite heat, not a declared emergency.
          </p>

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

          <div className="panel-title" style={{ margin: "12px 0 6px" }}>
            How well backed
          </div>
          {PROVENANCE_ORDER.map((provenanceClass) => (
            <div className="legend-row" key={provenanceClass}>
              <ProvenanceTag
                provenanceClass={provenanceClass}
                label={PROVENANCE_MARKS[provenanceClass].meaning}
              />
              <span>{PROVENANCE_MARKS[provenanceClass].meaning}</span>
            </div>
          ))}

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
