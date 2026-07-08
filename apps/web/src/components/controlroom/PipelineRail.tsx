import { formatDuration } from "../../lib/formatDuration";
import type { TimelinePhase } from "../../lib/buildTimeline";
import styles from "./PipelineRail.module.css";

interface PipelineRailProps {
  phases: TimelinePhase[];
}

/** The instrument rail's pipeline: the real phase list (the same fold the transcript renders),
 *  each with its status dot (done ✓ / live pulse / pending), one-line summary, and duration
 *  where stage arrivals were captured (the live path). */
export function PipelineRail({ phases }: PipelineRailProps) {
  return (
    <section className={styles.pipeline} aria-label="Pipeline">
      <p className={`eyebrow ${styles.title}`}>Pipeline</p>
      <ol className={styles.steps}>
        {phases.map((phase) => (
          <li key={phase.key} className={styles.step} data-status={phase.status}>
            <span className={styles.dot} data-status={phase.status} aria-hidden="true">
              {phase.status === "done" && (
                <svg
                  width="11"
                  height="11"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              )}
              {phase.status === "active" && <span className={styles.pulse} />}
            </span>
            <span className={styles.label}>{phase.label}</span>
            {phase.summary && (
              <span className={`${styles.summary} mono`} data-tone={phase.summaryTone}>
                {phase.summary}
              </span>
            )}
            {phase.durationMs !== null && (
              <span className={`${styles.duration} mono`}>{formatDuration(phase.durationMs)}</span>
            )}
            <span className="sr-only">
              {phase.status === "done" ? "done" : phase.status === "active" ? "in progress" : "pending"}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
