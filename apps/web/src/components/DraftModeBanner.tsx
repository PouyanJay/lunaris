import { CAPABILITY_LABELS, isLlmKeyless, type CapabilityStatus } from "../lib/capabilities";
import { ComputeSourceSelect } from "./explain/ComputeSourceSelect";
import { AccentBand } from "./primitives/AccentBand";
import styles from "./DraftModeBanner.module.css";

interface DraftModeBannerProps {
  capabilities: CapabilityStatus[];
  /** Open the Settings surface so the user can add their own keys (clears the banner). */
  onOpenSettings?: (() => void) | undefined;
}

/** The banner already says these run locally, so the redundant "(local)" suffix the server appends
 *  to a provider name is dropped — the value reads as the bare model/service name. */
function providerName(provider: string): string {
  return provider.replace(/\s*\(local\)\s*$/i, "");
}

/** Shown while one or more capabilities run on their keyless local fallback ("Draft mode").
 *  One lead line (eyebrow, caveat, the Settings action), then a hairline-topped status band
 *  where every cell shares the same label-over-value rhythm: the compute choice (a segmented
 *  control) first, then each fallback as micro-label over mono provider. Disappears once every
 *  capability is live. */
export function DraftModeBanner({ capabilities, onOpenSettings }: DraftModeBannerProps) {
  const fallbacks = capabilities.filter((capability) => capability.mode === "fallback");
  if (fallbacks.length === 0) return null;
  const llmIsKeyless = isLlmKeyless(fallbacks);

  return (
    <AccentBand className={styles.column}>
      <div className={styles.head}>
        <span className={`eyebrow ${styles.eyebrow}`}>Draft mode</span>
        <p className={styles.text}>
          Building with free local fallbacks — quality and verification are reduced.
        </p>
        {onOpenSettings && (
          <button type="button" className={styles.action} onClick={onOpenSettings}>
            Add your keys in Settings
          </button>
        )}
      </div>
      <div className={styles.statusRow}>
        {llmIsKeyless && (
          <div className={styles.cell}>
            <ComputeSourceSelect variant="compact" />
          </div>
        )}
        <dl className={styles.fallbacks}>
          {fallbacks.map((capability) => (
            <div key={capability.capability} className={styles.cell}>
              <dt className={`eyebrow ${styles.label}`}>
                {CAPABILITY_LABELS[capability.capability]}
              </dt>
              <dd className={styles.value}>
                <span className={`mono ${styles.provider}`}>
                  {providerName(capability.provider)}
                </span>
                {capability.compute && (
                  <span
                    className={styles.compute}
                    data-compute={capability.compute}
                    aria-label={`running on ${capability.compute.toUpperCase()}`}
                  >
                    {capability.compute.toUpperCase()}
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </AccentBand>
  );
}
