import { useId, useState } from "react";

import styles from "./HtmlPreview.module.css";

interface HtmlPreviewProps {
  /** Raw HTML from a ```html-preview fence — rendered in a fully sandboxed iframe (no scripts). */
  html: string;
}

/** Renders an authored HTML snippet as a live preview inside a sandboxed iframe. The `sandbox`
 *  attribute carries NO `allow-scripts` token, so the snippet cannot run JavaScript, navigate the
 *  top frame, submit forms, or read cookies — it is inert markup. The raw source is offered behind a
 *  disclosure so the snippet stays auditable. */
export function HtmlPreview({ html }: HtmlPreviewProps) {
  const [showSource, setShowSource] = useState(false);
  const titleId = useId();

  return (
    <figure className={styles.preview}>
      <figcaption className={styles.bar}>
        <span id={titleId} className={styles.label}>
          Preview
        </span>
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={showSource}
          onClick={() => setShowSource((open) => !open)}
        >
          {showSource ? "Hide source" : "View source"}
        </button>
      </figcaption>
      <iframe
        className={styles.frame}
        sandbox=""
        srcDoc={html}
        title="HTML preview"
        aria-labelledby={titleId}
        loading="lazy"
      />
      {showSource && (
        <pre className={styles.source}>
          <code>{html}</code>
        </pre>
      )}
    </figure>
  );
}
