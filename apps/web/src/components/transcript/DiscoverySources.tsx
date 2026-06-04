import type { SourceEvaluation } from "../../types/course";
import { SourceTrust } from "../primitives/SourceTrust";
import styles from "./DiscoverySources.module.css";

interface DiscoverySourcesProps {
  /** Each source the discovery sub-graph fetched + vetted, in arrival order (streams in live). */
  sources: SourceEvaluation[];
}

// Below this blended credibility a kept source is flagged low (⚠) — the same threshold the lesson's
// grounded citations use, so "thin evidence" reads identically across the build canvas and reader.
const LOW_CREDIBILITY = 0.7;

/** The live source-vetting table for the Grounding phase: each source the discovery loop fetched,
 *  with its domain, trust tier + credibility, and the keep/skip verdict + reason. Sources arrive
 *  one at a time as the sub-graph scores them (the streaming state); a kept/skipped tally heads the
 *  table so the outcome is legible at a glance. Trust is shown to the user on purpose — the
 *  transparency is the point; the in-graph relevance judge stays blind to it. */
export function DiscoverySources({ sources }: DiscoverySourcesProps) {
  const kept = sources.filter((source) => source.accepted).length;
  return (
    <section className={styles.panel} aria-label="Discovered sources">
      <header className={styles.head}>
        <span className={styles.title}>Evidence vetting</span>
        <span className={`mono ${styles.tally}`}>
          {kept} kept · {sources.length - kept} skipped
        </span>
      </header>
      <ul className={styles.rows}>
        {sources.map((source, index) => (
          // The list is append-only as sources stream in, so the index is a stable key (a domain
          // can recur across concepts, so it isn't unique on its own).
          <li key={index} className={styles.row} data-accepted={source.accepted}>
            <span className={styles.verdict} aria-hidden="true">
              {source.accepted ? "✓" : "✕"}
            </span>
            <span className={`mono ${styles.domain}`}>{source.domain}</span>
            <span className={styles.trust}>
              {source.trustTier ? (
                <SourceTrust
                  tier={source.trustTier}
                  credibility={source.credibility}
                  lowBelow={LOW_CREDIBILITY}
                />
              ) : (
                <span className={styles.untiered}>unrated</span>
              )}
            </span>
            <span className={styles.reason}>
              <span className="sr-only">{source.accepted ? "Kept: " : "Skipped: "}</span>
              {source.reason}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
