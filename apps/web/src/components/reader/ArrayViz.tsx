import { useId, useState } from "react";

import styles from "./ArrayViz.module.css";

interface ArrayVizProps {
  /** The array contents — a `[…]` literal or a comma/space separated list, e.g. "240, 180, 195". */
  values?: string;
  /** Optional caption shown above the cells. */
  caption?: string;
}

/** Parse a "[240, 180, 195]" / "240 180 195" string into trimmed cell labels. */
function parseCells(raw: string): string[] {
  return raw
    .trim()
    .replace(/^\[/, "")
    .replace(/\]$/, "")
    .split(/[,\s]+/)
    .map((cell) => cell.trim())
    .filter((cell) => cell.length > 0);
}

/** An indexed array visual (lifted from a ```array fence or a standalone `[…]` literal). Each value
 *  sits in a cell over its 0-based index — the teaching point arrays turn on. Selecting a cell (click
 *  or keyboard) highlights it and announces "index N → value" through a live region, so the
 *  value↔index mapping is explorable and accessible. The raw list is also exposed as text for screen
 *  readers and as a fallback. */
export function ArrayViz({ values, caption }: ArrayVizProps) {
  const cells = parseCells(values ?? "");
  const [active, setActive] = useState<number | null>(null);
  const statusId = useId();

  if (cells.length === 0) return null;

  return (
    <figure className={styles.array} aria-label={caption ?? "Array"}>
      {caption && <figcaption className={styles.caption}>{caption}</figcaption>}
      <ol className={styles.cells}>
        {cells.map((value, index) => (
          <li key={index} className={styles.cell}>
            <button
              type="button"
              className={`${styles.value} ${active === index ? styles.valueActive : ""} mono`}
              aria-label={`Index ${index}, value ${value}`}
              aria-pressed={active === index}
              onClick={() => setActive((prev) => (prev === index ? null : index))}
            >
              {value}
            </button>
            <span className={`${styles.index} mono`} aria-hidden="true">
              {index}
            </span>
          </li>
        ))}
      </ol>
      <p id={statusId} className={styles.status} role="status" aria-live="polite">
        {active === null
          ? "Select a cell to read its index."
          : `Index ${active} → ${cells[active]}`}
      </p>
    </figure>
  );
}
