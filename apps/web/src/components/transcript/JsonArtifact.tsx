import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { VisualSpec } from "../../types/course";
import { ComparisonTable } from "../reader/visuals/ComparisonTable";
import { FlowDiagram } from "../reader/visuals/FlowDiagram";
import { StepsDiagram } from "../reader/visuals/StepsDiagram";
import { TimelineDiagram } from "../reader/visuals/TimelineDiagram";
import { useExplainApi } from "./ExplainContext";
import styles from "./JsonArtifact.module.css";

interface JsonArtifactProps {
  /** The JSON/code blob, lifted from a reasoning beat or a tool result. */
  source: string;
  /** False while the blob is still streaming in (unterminated) — render bounded, never unbounded. */
  closed: boolean;
}

/** A JSON/code blob rendered as a *bounded* artifact instead of a raw dump that takes over (and keeps
 *  growing in) the transcript. A recognised visual spec draws as its branded diagram; other valid
 *  JSON shows a one-line summary over a collapsible, syntax-highlighted, scrollable tree; anything
 *  unparsed (or still streaming) shows a bounded, scrollable raw view. */
export function JsonArtifact({ source, closed }: JsonArtifactProps) {
  const parsed = useMemo(() => (closed ? tryParse(source) : undefined), [source, closed]);
  const spec = useMemo(() => asVisualSpec(parsed), [parsed]);
  const summary = useMemo(
    () => summarize(parsed, spec, source, closed),
    [parsed, spec, source, closed],
  );
  // A diagram or a still-streaming blob opens by default; a finished raw/JSON blob collapses to its
  // summary so a long dump never floods the view — the user expands it on demand.
  const [open, setOpen] = useState(() => spec !== null || !closed);

  // Finished, substantial, non-diagram blobs auto-explain: a plain-language summary streams in
  // below on its own (no click). Diagrams explain themselves; trivial blobs need no narration.
  const shouldExplain = closed && spec === null && isSubstantial(parsed, source);
  const { explanation, explaining, explainError } = useExplainState(source, shouldExplain);

  return (
    <div className={styles.artifact}>
      <button
        type="button"
        className={styles.head}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className={`eyebrow ${styles.kind}`}>{spec ? "diagram" : "json"}</span>
        <span className={`mono ${styles.summary}`}>{summary}</span>
        <span className={styles.chevron} data-open={open} aria-hidden="true" />
      </button>
      {explaining && <p className={styles.explaining}>Explaining…</p>}
      {explanation && <p className={styles.explanation}>{explanation}</p>}
      {explainError && (
        <p className={styles.explainError} role="status">
          {explainError}
        </p>
      )}
      {open && (
        <div className={styles.body} data-diagram={spec !== null}>
          {spec ? (
            <SpecBody spec={spec} />
          ) : parsed !== undefined ? (
            <pre className={`mono ${styles.code}`}>{colorizeJson(parsed)}</pre>
          ) : (
            <pre className={`mono ${styles.code}`}>{source}</pre>
          )}
        </div>
      )}
    </div>
  );
}

/** Render a recognised spec with the branded reader diagrams. Mirrors VisualRenderer's switch on
 *  purpose: the transcript wants a bare diagram, not the reader's captioned figure chrome. */
function SpecBody({ spec }: { spec: VisualSpec }) {
  switch (spec.type) {
    case "flow":
    case "tree":
      return <FlowDiagram spec={spec} />;
    case "steps":
      return <StepsDiagram spec={spec} />;
    case "comparison":
      return <ComparisonTable spec={spec} />;
    case "timeline":
      return <TimelineDiagram spec={spec} />;
  }
}

function tryParse(source: string): unknown {
  const trimmed = source.trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return undefined;
  }
}

/** Narrow a parsed value to a VisualSpec only when its discriminant AND the field its diagram reads
 *  are both present — so a malformed spec falls back to the raw tree rather than crashing a diagram. */
function asVisualSpec(value: unknown): VisualSpec | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  switch (candidate.type) {
    case "flow":
      return Array.isArray(candidate.nodes) && Array.isArray(candidate.edges)
        ? (value as VisualSpec)
        : null;
    case "tree":
      return Array.isArray(candidate.nodes) ? (value as VisualSpec) : null;
    case "steps":
      return Array.isArray(candidate.steps) ? (value as VisualSpec) : null;
    case "comparison":
      return Array.isArray(candidate.columns) && Array.isArray(candidate.rows)
        ? (value as VisualSpec)
        : null;
    case "timeline":
      return Array.isArray(candidate.events) ? (value as VisualSpec) : null;
    default:
      return null;
  }
}

const plural = (count: number, noun: string) => `${count} ${noun}${count === 1 ? "" : "s"}`;

function summarize(
  parsed: unknown,
  spec: VisualSpec | null,
  source: string,
  closed: boolean,
): string {
  if (spec) return specSummary(spec);
  if (Array.isArray(parsed)) return `array · ${plural(parsed.length, "item")}`;
  if (parsed && typeof parsed === "object") {
    return `object · ${plural(Object.keys(parsed).length, "key")}`;
  }
  if (!closed) return "streaming…";
  return plural(source.trimEnd().split("\n").length, "line");
}

function specSummary(spec: VisualSpec): string {
  switch (spec.type) {
    case "flow":
      return `flow · ${plural(spec.nodes.length, "node")} · ${plural(spec.edges.length, "edge")}`;
    case "tree":
      return `tree · ${plural(spec.nodes.length, "node")}`;
    case "steps":
      return `steps · ${plural(spec.steps.length, "step")}`;
    case "comparison":
      return `comparison · ${plural(spec.rows.length, "row")}`;
    case "timeline":
      return `timeline · ${plural(spec.events.length, "event")}`;
    case "before-after":
      return "before/after · 2 sides";
  }
}

// Strings (incl. keys, captured with a trailing colon), keywords, and numbers — the JSON token kinds
// worth colouring distinctly (the renderjson convention).
const JSON_TOKEN =
  /("(?:\\.|[^"\\])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

/** Pretty-print a value and wrap each token in a type-coloured span. */
function colorizeJson(value: unknown): ReactNode[] {
  const text = JSON.stringify(value, null, 2);
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (let match = JSON_TOKEN.exec(text); match !== null; match = JSON_TOKEN.exec(text)) {
    if (match.index > last) out.push(text.slice(last, match.index));
    out.push(
      <span key={key++} className={styles[tokenClass(match[0])]}>
        {match[0]}
      </span>,
    );
    last = JSON_TOKEN.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function tokenClass(token: string): "key" | "str" | "bool" | "nul" | "num" {
  if (token.startsWith('"')) return token.trimEnd().endsWith(":") ? "key" : "str";
  if (token === "true" || token === "false") return "bool";
  if (token === "null") return "nul";
  return "num";
}

// A blob is worth narrating once its source is this long, or it carries at least this many entries —
// below both, the summary already says all there is to say, so auto-explain stays quiet.
const SUBSTANTIAL_SOURCE_CHARS = 100;
const SUBSTANTIAL_ENTRY_COUNT = 3;

/** Whether a blob is worth a plain-language explanation: a long source, or a non-trivial object /
 *  array. Tiny blobs (a lone judgment) are self-evident from their summary and aren't auto-explained. */
function isSubstantial(parsed: unknown, source: string): boolean {
  if (source.length >= SUBSTANTIAL_SOURCE_CHARS) return true;
  if (Array.isArray(parsed)) return parsed.length >= SUBSTANTIAL_ENTRY_COUNT;
  if (parsed && typeof parsed === "object") {
    return Object.keys(parsed).length >= SUBSTANTIAL_ENTRY_COUNT;
  }
  return false;
}

/** The auto-Explain lifecycle for one blob: when `auto` and the service is available, fetch a
 *  plain-language explanation exactly once and expose its in-flight / result / error state. Kept out
 *  of the component body so it stays focused on rendering. */
function useExplainState(source: string, auto: boolean) {
  const { available, explain } = useExplainApi();
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const requestedRef = useRef(false);

  useEffect(() => {
    if (!auto || !available || requestedRef.current) return;
    requestedRef.current = true;
    setExplaining(true);
    explain(source)
      .then((result) => setExplanation(result))
      .catch(() => setExplainError("Couldn't explain this right now."))
      .finally(() => setExplaining(false));
  }, [auto, available, explain, source]);

  return { explanation, explaining, explainError };
}
