import type { CapabilityStatus } from "../lib/capabilities";
import styles from "./DraftModeBanner.module.css";

const LABELS: Record<CapabilityStatus["capability"], string> = {
  llm: "language model",
  embeddings: "embeddings",
  search: "search",
  video: "video",
};

interface DraftModeBannerProps {
  capabilities: CapabilityStatus[];
  /** Open the Settings surface so the user can add their own keys (clears the banner). */
  onOpenSettings?: (() => void) | undefined;
}

/** Shown while one or more capabilities run on their keyless local fallback ("Draft mode"). Names
 *  each fallback in effect; disappears entirely once every capability is live (its key is set). */
export function DraftModeBanner({ capabilities, onOpenSettings }: DraftModeBannerProps) {
  const fallbacks = capabilities.filter((capability) => capability.mode === "fallback");
  if (fallbacks.length === 0) return null;

  return (
    <aside className={styles.banner} role="status">
      <span className={`eyebrow ${styles.eyebrow}`}>Draft mode</span>
      <p className={styles.text}>
        Building with free local fallbacks for{" "}
        {fallbacks.map((capability, index) => (
          <span key={capability.capability}>
            {index > 0 && (index === fallbacks.length - 1 ? " and " : ", ")}
            {LABELS[capability.capability]} (<span className="mono">{capability.provider}</span>
            {capability.compute && (
              <span
                className={styles.compute}
                aria-label={`running on ${capability.compute.toUpperCase()}`}
              >
                {capability.compute.toUpperCase()}
              </span>
            )}
            )
          </span>
        ))}
        . Quality and verification are reduced.
      </p>
      {onOpenSettings && (
        <button type="button" className={styles.action} onClick={onOpenSettings}>
          Add your keys in Settings
        </button>
      )}
    </aside>
  );
}
