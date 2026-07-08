import type { GroundingLedger } from "../../lib/instruments";
import styles from "./GroundingLedgerPanel.module.css";

/** Trust-mix bar colors: the tier ramp's first step for reputable, success for official, muted
 *  for everything else — mirroring the design's ledger swatches on real tokens. */
const TIER_COLOR: Record<string, string> = {
  official: "var(--success)",
  reputable: "var(--tier-1)",
  vouched: "var(--tier-2)",
  open: "var(--text-muted)",
  blocked: "var(--danger)",
};

interface GroundingLedgerPanelProps {
  ledger: GroundingLedger;
}

/** The grounding ledger (P8 instrument rail): claim verdict tallies and the trust mix of the
 *  accepted discovery sources — every figure summed from real stream events. */
export function GroundingLedgerPanel({ ledger }: GroundingLedgerPanelProps) {
  return (
    <section className={styles.panel} aria-label="Grounding ledger">
      <p className={`eyebrow ${styles.title}`}>Grounding ledger</p>
      <dl className={styles.tallies}>
        <div className={styles.tally}>
          <dd className={`${styles.figure} mono`} data-tone="success">
            {ledger.supported}
          </dd>
          <dt className={`${styles.figureLabel} mono`}>Supported</dt>
        </div>
        <div className={styles.tally}>
          <dd className={`${styles.figure} mono`} data-tone={ledger.cut > 0 ? "danger" : undefined}>
            {ledger.cut}
          </dd>
          <dt className={`${styles.figureLabel} mono`}>Cut</dt>
        </div>
        <div className={styles.tally}>
          <dd className={`${styles.figure} mono`}>{ledger.sources}</dd>
          <dt className={`${styles.figureLabel} mono`}>Sources</dt>
        </div>
      </dl>
      {ledger.trustMix.length > 0 && (
        <>
          <p className={`${styles.mixLabel} mono`}>Trust mix of accepted sources</p>
          <div className={styles.mixBar} role="img" aria-label="Trust mix of accepted sources">
            {ledger.trustMix.map((slice) => (
              <span
                key={slice.tier}
                style={{ width: `${slice.pct}%`, background: TIER_COLOR[slice.tier] }}
              />
            ))}
          </div>
          <div className={styles.mixKey}>
            {ledger.trustMix.map((slice) => (
              <span key={slice.tier} className={`${styles.mixEntry} mono`}>
                <span
                  className={styles.swatch}
                  style={{ background: TIER_COLOR[slice.tier] }}
                  aria-hidden="true"
                />
                {slice.tier} {slice.pct}%
              </span>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
