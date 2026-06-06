import type { Citation } from "../../types/course";
import { SourceTrust } from "../primitives/SourceTrust";
import styles from "./ClaimProvenance.module.css";

/** Credibility below this flags the evidence as lower-confidence in the reader (display only). */
const LOW_CREDIBILITY = 0.7;

/** The grounding lineage for one claim: the source it was grounded against, with its trust tier +
 *  credibility when the evidence was classified (P6.0). A pre-P6.0 / unclassified citation shows the
 *  source alone, no trust badge. Shared by the annotation rail and any claim surface. */
export function ClaimProvenance({ citation }: { citation: Citation }) {
  const label = citation.title ?? "Source";
  return (
    <div className={styles.provenance}>
      <span className="eyebrow">Source</span>
      {citation.url ? (
        <a className={styles.link} href={citation.url} target="_blank" rel="noopener noreferrer">
          {label}
        </a>
      ) : (
        <span className={styles.name}>{label}</span>
      )}
      {citation.trustTier && (
        <SourceTrust
          tier={citation.trustTier}
          credibility={citation.credibility ?? null}
          lowBelow={LOW_CREDIBILITY}
        />
      )}
      {citation.snippet && <p className={styles.snippet}>“{citation.snippet}”</p>}
    </div>
  );
}
