import { useId, useState, type ReactNode } from "react";

import styles from "./GlossaryTerm.module.css";

interface GlossaryTermProps {
  /** The definition text, lowered from `:term[word]{title="…"}`. */
  definition?: string;
  children?: ReactNode;
}

/** An inline glossary term: the word stays in the reading flow with a dotted underline, and its
 *  definition is revealed on hover AND on keyboard focus (a real `button`, so it is operable without
 *  a pointer). The definition is wired with `aria-describedby` so assistive tech announces it. */
export function GlossaryTerm({ definition, children }: GlossaryTermProps) {
  const [open, setOpen] = useState(false);
  const tooltipId = useId();

  if (!definition) return <>{children}</>;

  return (
    <span className={styles.wrap}>
      <button
        type="button"
        className={styles.term}
        aria-describedby={open ? tooltipId : undefined}
        aria-expanded={open}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        {children}
      </button>
      <span role="tooltip" id={tooltipId} hidden={!open} className={styles.tooltip}>
        {definition}
      </span>
    </span>
  );
}
