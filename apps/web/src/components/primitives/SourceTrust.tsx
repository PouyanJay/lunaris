import type { TrustTier } from "../../types/course";
import styles from "./SourceTrust.module.css";

interface SourceTrustProps {
  /** The source's authority tier, shown as an uppercase mono word (never colour alone — WCAG). */
  tier: TrustTier;
  /** 0..1 blended quality score; null or 0 hides the percentage. */
  credibility?: number | null;
  /** Credibility strictly below this is flagged low (adds a ⚠ + warning tone). Omit to never flag. */
  lowBelow?: number;
}

/** The house trust signal for a source: its authority TIER as an uppercase mono word plus an
 *  optional credibility percentage. Shared by the lesson's grounded citations and its curated
 *  resources (and the P6.3 discovery canvas) so trust reads identically everywhere. Renders a
 *  fragment so it slots into an existing flex row. */
export function SourceTrust({ tier, credibility = null, lowBelow }: SourceTrustProps) {
  const hasScore = credibility != null && credibility > 0;
  const pct = hasScore ? Math.round(credibility * 100) : 0;
  const isLowCredibility = hasScore && lowBelow != null && credibility < lowBelow;
  return (
    <>
      <span className={`mono ${styles.tier}`} data-tier={tier}>
        {tier}
      </span>
      {hasScore && (
        <span
          className={`mono ${styles.credibility}`}
          aria-label={`Credibility ${pct}%${isLowCredibility ? ", low" : ""}`}
        >
          {pct}%
          {isLowCredibility && (
            <span className={styles.warn} aria-hidden="true">
              {" "}
              ⚠
            </span>
          )}
        </span>
      )}
    </>
  );
}
