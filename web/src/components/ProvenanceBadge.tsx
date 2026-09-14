import type { ProvenanceClass } from "../api/types";
import { ago } from "./format";

interface Mark {
  glyph: string;
  code: string;
  meaning: string;
}

/** Strongest to weakest. The glyph fills in as corroboration increases. */
export const PROVENANCE_ORDER: ProvenanceClass[] = [
  "AUTHORITATIVE_EEW",
  "AUTHORITATIVE_NOTICE",
  "MULTISOURCE_RAPID",
  "SINGLE_SOURCE_RAPID",
  "AUTOMATED_SIGNAL",
  "MODEL_ESTIMATE",
];

export const PROVENANCE_MARKS: Record<ProvenanceClass, Mark> = {
  AUTHORITATIVE_EEW: {
    glyph: "★",
    code: "EEW",
    meaning: "Official early warning",
  },
  AUTHORITATIVE_NOTICE: {
    glyph: "✓",
    code: "OFFICIAL",
    meaning: "Official bulletin from the responsible agency",
  },
  MULTISOURCE_RAPID: {
    glyph: "◉",
    code: "2+ SRC",
    meaning: "Two or more independent networks agree",
  },
  SINGLE_SOURCE_RAPID: {
    glyph: "◎",
    code: "1 SRC",
    meaning: "One network only — may be revised or retracted",
  },
  AUTOMATED_SIGNAL: {
    glyph: "◌",
    code: "AUTO",
    meaning: "Machine detection only, nothing has confirmed it",
  },
  MODEL_ESTIMATE: {
    glyph: "≈",
    code: "MODEL",
    meaning: "Computed here, not observed",
  },
};

interface TagProps {
  provenanceClass: ProvenanceClass;
  /** The full wording, kept as the accessible name so it is never lost. */
  label: string;
  compact?: boolean;
}

export function ProvenanceTag({
  provenanceClass,
  label,
  compact = false,
}: TagProps): React.JSX.Element {
  const mark = PROVENANCE_MARKS[provenanceClass];
  return (
    <span
      className={`provenance ${provenanceClass}${compact ? " compact" : ""}`}
      title={label}
      aria-label={label}
    >
      <span className="provenance-glyph">{mark.glyph}</span>
      {compact ? null : mark.code}
    </span>
  );
}

interface Props {
  provenanceClass: ProvenanceClass;
  label: string;
  dataAgeSeconds: number | null;
}

/**
 * Provenance and freshness always travel together, on the opaque tier. This is
 * the one surface that spells the wording out in full.
 */
export function ProvenanceBadge({
  provenanceClass,
  label,
  dataAgeSeconds,
}: Props): React.JSX.Element {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <ProvenanceTag provenanceClass={provenanceClass} label={label} />
      <span style={{ fontSize: 11 }}>{label}</span>
      <span style={{ fontSize: 10, color: "var(--fg-faint)" }}>{ago(dataAgeSeconds)}</span>
    </div>
  );
}
