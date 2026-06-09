import type { CapabilityStatus } from "../../lib/capabilities";
import styles from "./CapabilityBadges.module.css";

const LABELS: Record<CapabilityStatus["capability"], string> = {
  llm: "Language model",
  embeddings: "Embeddings",
  search: "Web search",
  video: "Video",
};

interface CapabilityBadgesProps {
  capabilities: CapabilityStatus[];
}

/** Per-capability active provider: which capabilities run live (their key is set) vs on a keyless
 *  local fallback. The uppercase-mono mode word carries the state — never colour alone — and a row
 *  flips to LIVE the moment its key is stored. */
export function CapabilityBadges({ capabilities }: CapabilityBadgesProps) {
  if (capabilities.length === 0) return null;
  return (
    <ul className={styles.list} aria-label="Capability providers">
      {capabilities.map((capability) => (
        <li key={capability.capability} className={styles.row} data-mode={capability.mode}>
          <span className={styles.name}>{LABELS[capability.capability]}</span>
          <span className={`mono ${styles.provider}`}>{capability.provider}</span>
          <span className={`mono ${styles.mode}`}>
            {capability.mode === "fallback" ? "FALLBACK" : "LIVE"}
          </span>
        </li>
      ))}
    </ul>
  );
}
