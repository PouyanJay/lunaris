import { CAPABILITY_LABELS } from "../../lib/capabilities";
import type { CapabilityBuildTag } from "../../types/course";
import styles from "./BuildProvenance.module.css";

interface BuildProvenanceProps {
  buildCapabilities: CapabilityBuildTag[];
}

/** The per-course build tag (keyless-fallbacks T5): the persistent, honest record of which keyless
 *  fallback produced this course's content. Distinct from the live capability badge — this is
 *  captured at finalize and pinned to the course, so it never flips when a key is later stored; it
 *  only changes when the course is rebuilt. Renders nothing for a fully-live build (no fallbacks to
 *  disclose). The uppercase-mono "DRAFT" tag and the per-row provider carry the signal — never
 *  colour alone — so the learner is never shown a Draft course as if it were authoritative. */
export function BuildProvenance({ buildCapabilities }: BuildProvenanceProps) {
  const fallbacks = buildCapabilities.filter((tag) => tag.mode === "fallback");
  if (fallbacks.length === 0) return null;
  return (
    <section className={styles.band} aria-label="Build provenance">
      <div className={styles.head}>
        <p className={styles.eyebrow}>Built in Draft mode</p>
        <span className={`mono ${styles.tag}`}>DRAFT</span>
      </div>
      <p className={styles.note}>
        This course was built with keyless local fallbacks, so its depth and verification are
        lighter than a fully-keyed build. Add the matching keys and rebuild to upgrade it.
      </p>
      <ul className={styles.list} aria-label="Fallback providers used">
        {fallbacks.map((tag) => (
          <li key={tag.capability} className={styles.row}>
            <span className={styles.name}>{CAPABILITY_LABELS[tag.capability]}</span>
            <span className={`mono ${styles.provider}`}>{tag.provider}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
