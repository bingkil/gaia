import { useState } from "react";
import type { ProviderRecord } from "../api/types";
import { ago } from "./format";

/**
 * A silent feed is indistinguishable from a quiet planet, so staleness is
 * shown explicitly rather than inferred from an empty map.
 */
export function ProviderHealthPanel({
  providers,
}: {
  providers: ProviderRecord[];
}): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const degraded = providers.filter(
    (provider) => provider.state !== "HEALTHY" && provider.state !== "DISABLED",
  );

  return (
    <section className="panel glass">
      <header className="panel-head">
        <span className="panel-title">Feeds</span>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {degraded.length > 0 ? (
            <span className="tag" style={{ color: "var(--warn)" }}>
              {degraded.length} degraded
            </span>
          ) : null}
          <button className="btn ghost" onClick={() => setOpen(!open)} type="button">
            {open ? "−" : "+"}
          </button>
        </span>
      </header>

      {open ? (
        <div className="panel-body pad">
          {providers.map((provider) => (
            <div key={provider.provider} style={{ padding: "3px 0" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11 }}>
                <i className={`dot ${provider.state}`} />
                <span style={{ flex: 1 }}>{provider.provider}</span>
                <span
                  style={{ color: "var(--fg-faint)", fontFamily: "var(--mono)", fontSize: 10 }}
                >
                  {provider.state === "DISABLED"
                    ? "off"
                    : ago(provider.lastMessageAgeSeconds)}
                </span>
              </div>
              {provider.lastError ? (
                <div
                  style={{ color: "var(--warn)", fontSize: 10, paddingLeft: 16, marginTop: 1 }}
                >
                  {provider.lastError}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}
