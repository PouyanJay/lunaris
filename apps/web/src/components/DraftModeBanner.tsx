import { CAPABILITY_LABELS, type CapabilityStatus } from "../lib/capabilities";
import styles from "./DraftModeBanner.module.css";

interface DraftModeBannerProps {
  capabilities: CapabilityStatus[];
  /** Open the Settings surface so the user can add their own keys (clears the banner). */
  onOpenSettings?: (() => void) | undefined;
}

/** The banner already says these run locally, so the redundant "(local)" suffix the server appends
 *  to a provider name is dropped — the chip reads as the bare model/service name. */
function providerName(provider: string): string {
  return provider.replace(/\s*\(local\)\s*$/i, "");
}

/** Shown while one or more capabilities run on their keyless local fallback ("Draft mode"). Lists
 *  each fallback as a labelled chip (capability → provider, with the LLM's compute kind); disappears
 *  entirely once every capability is live (its key is set). */
export function DraftModeBanner({ capabilities, onOpenSettings }: DraftModeBannerProps) {
  const fallbacks = capabilities.filter((capability) => capability.mode === "fallback");
  if (fallbacks.length === 0) return null;

  return (
    <aside className={styles.banner} role="status">
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
      <dl className={styles.chips}>
        {fallbacks.map((capability) => (
          <div key={capability.capability} className={styles.chip}>
            <dt className={styles.chipLabel}>{CAPABILITY_LABELS[capability.capability]}</dt>
            <dd className={styles.chipValue}>
              <span className={`mono ${styles.provider}`}>{providerName(capability.provider)}</span>
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
    </aside>
  );
}
