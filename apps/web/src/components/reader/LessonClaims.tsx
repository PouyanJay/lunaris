import type { Citation, Claim, VerifierStatus } from "../../types/course";
import { StatusDot, type StatusTone } from "../primitives/StatusDot";
import styles from "./LessonClaims.module.css";

/** Map the verifier's verdict to the house status tones. */
const STATUS_TONE: Record<VerifierStatus, StatusTone> = {
  supported: "success",
  revise: "warning",
  cut: "danger",
  unverified: "neutral",
};

/** The grounding lineage for one claim: the citation it was supported by. */
function Provenance({ citation }: { citation: Citation }) {
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
      {citation.snippet && <p className={styles.snippet}>“{citation.snippet}”</p>}
    </div>
  );
}

interface LessonClaimsProps {
  claims: Claim[];
  citations: Map<string, Citation>;
}

/** A segment's factual claims with their verification status and, where supported, the source they
 *  were grounded against — making each fact's provenance visible to the learner. */
export function LessonClaims({ claims, citations }: LessonClaimsProps) {
  return (
    <ul className={styles.claims} aria-label="Claims and sources">
      {claims.map((claim, index) => {
        const citation = claim.supportedBy ? citations.get(claim.supportedBy) : undefined;
        return (
          <li key={index} className={styles.claim}>
            <div className={styles.head}>
              <StatusDot label={claim.verifierStatus} tone={STATUS_TONE[claim.verifierStatus]} />
              <p className={styles.text}>{claim.text}</p>
            </div>
            {citation ? (
              <Provenance citation={citation} />
            ) : (
              <p className={styles.uncited}>No source on record</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
