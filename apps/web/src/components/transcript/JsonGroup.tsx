import { useMemo, useState } from "react";

import styles from "./JsonArtifact.module.css";

interface JsonGroupProps {
  /** The small JSON blobs coalesced from a flood (e.g. one prerequisite judgment per pair). */
  sources: string[];
  /** False while the run is still streaming in. */
  closed: boolean;
}

// Even expanded, never render more than this many rows — a flood is summarised, not unrolled into
// hundreds of children.
const MAX_SHOWN = 50;

/** A run of many small JSON blobs collapsed into ONE bounded artifact: a deterministic summary line
 *  (a count, plus a true/false tally when the blobs share a boolean key — no model call needed) over
 *  a collapsed, capped, scrollable preview. Replaces the flood of tiny cards that blocked scrolling. */
export function JsonGroup({ sources, closed }: JsonGroupProps) {
  const summary = useMemo(() => groupSummary(sources, closed), [sources, closed]);
  const [open, setOpen] = useState(false);
  const shown = sources.slice(0, MAX_SHOWN);
  const hidden = sources.length - shown.length;

  return (
    <div className={styles.artifact}>
      <button
        type="button"
        className={styles.head}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className={`eyebrow ${styles.kind}`}>json</span>
        <span className={`mono ${styles.summary}`}>{summary}</span>
        <span className={styles.chevron} data-open={open} aria-hidden="true" />
      </button>
      {open && (
        <div className={styles.body}>
          <pre className={`mono ${styles.code}`}>{shown.map((s) => s.trim()).join("\n")}</pre>
          {hidden > 0 && <p className={styles.more}>…and {hidden} more</p>}
        </div>
      )}
    </div>
  );
}

function groupSummary(sources: string[], closed: boolean): string {
  const total = sources.length;
  const objects = sources.map(parseObject);
  if (objects.every((obj): obj is Record<string, unknown> => obj !== null)) {
    const key = commonBooleanKey(objects);
    if (key) {
      const yes = objects.filter((obj) => obj[key] === true).length;
      return `${total} × ${key} — ${yes} true, ${total - yes} false`;
    }
  }
  return `${total} snippets${closed ? "" : " · streaming…"}`;
}

function parseObject(source: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(source.trim());
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** A key that is a boolean in every object (so its true/false split is a meaningful tally), or null. */
function commonBooleanKey(objects: Record<string, unknown>[]): string | null {
  const first = objects[0];
  if (!first) return null;
  for (const key of Object.keys(first)) {
    if (objects.every((obj) => typeof obj[key] === "boolean")) return key;
  }
  return null;
}
