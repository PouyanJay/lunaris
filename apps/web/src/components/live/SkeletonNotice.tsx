import styles from "./SkeletonNotice.module.css";

/** A wait, shaped like the transcript it stands in for, so nothing jumps when the real thing lands
 *  (a spinner where a transcript will be is a blank flash). Live to assistive tech once, on arrival,
 *  through the status role; the skeleton lines are decoration. Shared by both surfaces (P2c T7):
 *  the transcript's opening and warming waits, and the panel's warming wait in the composer's
 *  place, so the two cannot wait differently. */
export function SkeletonNotice({ lead, lines }: { lead: string; lines: number }) {
  return (
    <div className={styles.notice} role="status">
      <p className={styles.lead}>{lead}</p>
      <div className={styles.lines} aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <span key={index} className={index === lines - 1 ? styles.short : styles.line} />
        ))}
      </div>
    </div>
  );
}

/** The honest wait (P2c T2): the interview has run out and the map is not there yet. Nothing to
 *  answer; the host's poll moves the session on. One notice on both surfaces. */
export function Warming() {
  return <SkeletonNotice lead="Almost ready. Setting up your first lesson…" lines={2} />;
}
