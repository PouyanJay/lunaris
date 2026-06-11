import { CAPABILITY_LABELS, type CapabilityStatus } from "../lib/capabilities";
import { ComputeSourceSelect } from "./explain/ComputeSourceSelect";
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

/** Shown while one or more capabilities run on their keyless local fallback ("Draft mode"). Lists
 *  each fallback as a flat status row — capability label → provider (mono), divided by hairlines,
 *  with the LLM's compute kind as a small badge — and disappears once every capability is live. */
export function DraftModeBanner({ capabilities, onOpenSettings }: DraftModeBannerProps) {
  const fallbacks = capabilities.filter((capability) => capability.mode === "fallback");
  if (fallbacks.length === 0) return null;
  // The LLM on its fallback means this user's explanations are keyless too — offer the per-device
  // compute choice right where Draft mode is announced.
  const llmIsKeyless = fallbacks.some((capability) => capability.capability === "llm");

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
      <dl className={styles.fallbacks}>
        {fallbacks.map((capability) => (
          <div key={capability.capability} className={styles.item}>
            <dt className={styles.label}>{CAPABILITY_LABELS[capability.capability]}</dt>
            <dd className={styles.value}>
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
      {llmIsKeyless && (
        <div className={styles.computeRow}>
          <ComputeSourceSelect />
        </div>
      )}
    </aside>
  );
}
