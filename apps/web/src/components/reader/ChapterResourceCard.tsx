import type { ScoredResource } from "../../lib/chapterResources";
import { KIND_GLYPH } from "./resourceKind";
import styles from "./ChapterResourceCard.module.css";

/** A compact resource card docked under a chapter in the Cinema rail: a leading kind-glyph marks it as
 *  a resource (and names its type at a glance), then a link to the vetted aid with its source,
 *  runtime, and a relevance score (the share of the chapter's key terms it covers). */
export function ChapterResourceCard({ scored }: { scored: ScoredResource }) {
  const { resource, rel } = scored;
  return (
    <a className={styles.card} href={resource.url} target="_blank" rel="noopener noreferrer">
      <span className={`mono ${styles.glyph}`} aria-hidden="true">
        {KIND_GLYPH[resource.kind]}
      </span>
      <span className={styles.body}>
        <span className={styles.title}>{resource.title}</span>
        <span className={`mono ${styles.meta}`}>
          {resource.source}
          {resource.duration ? ` · ${resource.duration}` : ""} ·{" "}
          <span className={styles.rel}>REL {rel}%</span>
        </span>
      </span>
    </a>
  );
}
