import type { ProvenanceClass } from "../api/types";
import { ago } from "./format";

interface Props {
  provenanceClass: ProvenanceClass;
  label: string;
  dataAgeSeconds: number | null;
}

/**
 * Provenance and freshness always travel together, on the opaque tier. A
 * reader must never have to guess how good a claim is or how old it is.
 */
export function ProvenanceBadge({ provenanceClass, label, dataAgeSeconds }: Props): React.JSX.Element {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span className={`provenance ${provenanceClass}`}>{label}</span>
      <span style={{ fontSize: 10, color: "var(--fg-faint)" }}>{ago(dataAgeSeconds)}</span>
    </div>
  );
}
