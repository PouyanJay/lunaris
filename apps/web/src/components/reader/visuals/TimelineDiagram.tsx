import type { TimelineSpec } from "../../../types/course";
import styles from "./visuals.module.css";

interface TimelineDiagramProps {
  spec: TimelineSpec;
}

/** A branded vertical timeline: ordered events, each with an optional time marker and detail. */
export function TimelineDiagram({ spec }: TimelineDiagramProps) {
  return (
    <ol className={styles.timeline}>
      {spec.events.map((event, index) => (
        <li key={index} className={styles.event}>
          <span className={styles.eventDot} aria-hidden="true" />
          <div className={styles.eventBody}>
            {event.when && <span className={`${styles.eventWhen} mono`}>{event.when}</span>}
            <p className={styles.eventLabel}>{event.label}</p>
            {event.detail && <p className={styles.eventDetail}>{event.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
