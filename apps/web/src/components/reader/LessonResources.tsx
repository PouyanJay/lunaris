import type { Resource } from "../../types/course";
import styles from "./LessonResources.module.css";

interface LessonResourcesProps {
  resources: Resource[];
}

/** The curated external resources attached to a teaching phase (P7.4) — suggested aids the learner
 *  can follow beyond the lesson. Each is a real out-bound link (new tab) with its kind, source domain
 *  (mono), trust tier badge, an optional runtime, and the one-line "why this helps". The caller
 *  renders it only when `resources` is non-empty, so a phase with no vetted aid simply omits it. */
export function LessonResources({ resources }: LessonResourcesProps) {
  return (
    <section className={styles.panel} aria-label="Resources">
      <h4 className={styles.title}>Resources</h4>
      <ul className={styles.list}>
        {resources.map((resource) => (
          <li key={resource.url} className={styles.item}>
            <div className={styles.head}>
              <span className={`mono ${styles.kind}`}>{resource.kind}</span>
              <a
                className={styles.link}
                href={resource.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {resource.title}
              </a>
              {resource.duration && (
                <span className={`mono ${styles.duration}`}>{resource.duration}</span>
              )}
            </div>
            {resource.why && <p className={styles.why}>{resource.why}</p>}
            <div className={styles.meta}>
              {resource.source && (
                <span className={`mono ${styles.source}`}>{resource.source}</span>
              )}
              <span className={`mono ${styles.trust}`} data-tier={resource.trustTier}>
                {resource.trustTier}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
