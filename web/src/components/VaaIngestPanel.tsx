import { useState } from "react";
import { ApiError, api } from "../api/client";
import type { HazardEvent } from "../api/types";

interface Props {
  onIngested: (event: HazardEvent) => void;
}

interface Result {
  frameCount: number;
  warnings: string[];
}

export function VaaIngestPanel({ onIngested }: Props): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [bulletin, setBulletin] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = (): void => {
    setBusy(true);
    setError(null);
    setResult(null);
    api
      .ingestVaa(bulletin)
      .then((response) => {
        setResult({ frameCount: response.frameCount, warnings: response.parserWarnings });
        setBulletin("");
        onIngested(response.event);
      })
      .catch((cause: unknown) => {
        setError(
          cause instanceof ApiError ? cause.message : "Could not reach the local service.",
        );
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="panel glass">
      <header className="panel-head">
        <span className="panel-title">Paste ash advisory</span>
        <button className="btn ghost" onClick={() => setOpen(!open)} type="button">
          {open ? "−" : "+"}
        </button>
      </header>

      {open ? (
        <div className="panel-body pad">
          <div className="field">
            <label htmlFor="vaa-bulletin">VAA bulletin text</label>
            <textarea
              id="vaa-bulletin"
              rows={7}
              value={bulletin}
              spellCheck={false}
              style={{ fontFamily: "var(--mono)", fontSize: 10, resize: "vertical" }}
              onChange={(event) => setBulletin(event.target.value)}
              placeholder={"VA ADVISORY\nDTG: …\nVAAC: …\nVOLCANO: …\nOBS VA CLD: …"}
            />
          </div>

          <button
            className="btn"
            onClick={submit}
            disabled={busy || bulletin.trim() === ""}
            type="button"
          >
            {busy ? "Reading…" : "Ingest advisory"}
          </button>

          {error ? (
            <p className="disclaimer solid" style={{ marginTop: 10 }}>
              {error}
            </p>
          ) : null}

          {result ? (
            <div style={{ marginTop: 10 }}>
              <p className="disclaimer solid">
                {result.frameCount} ash {result.frameCount === 1 ? "frame" : "frames"} stored.
                Each frame is drawn only at its own valid time — scrub the clock to reach a
                forecast frame.
              </p>
              {result.warnings.length > 0 ? (
                <>
                  <div className="panel-title" style={{ margin: "10px 0 4px" }}>
                    Parser warnings
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "var(--warn)" }}>
                    {result.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
