import styles from "./visuals.module.css";

interface MermaidFallbackProps {
  source: string;
}

/** Fallback when a visual carries no branded spec: present its diagram-as-code source verbatim,
 *  labelled, rather than rendering an unvalidated diagram. A plain div (not a figure) since the
 *  VisualRenderer card it sits in is already the figure. */
export function MermaidFallback({ source }: MermaidFallbackProps) {
  return (
    <div className={styles.fallback}>
      <p className="eyebrow">Diagram source</p>
      <pre className={`${styles.fallbackCode} mono`}>{source}</pre>
    </div>
  );
}
