import type { DegradedScene } from "../../types/course";
import styles from "./DegradedBadge.module.css";

interface DegradedBadgeProps {
  /** The scenes the build shipped flagged; the badge renders nothing for an empty list. */
  scenes: DegradedScene[];
}

/** The "degraded" signal on a video the build shipped best-effort (explainer-video quality-hardening
 *  D1): a muted warning dot + an UPPERCASE-MONO scene count, with the per-scene issues on hover so
 *  the artifact is honest about what is imperfect instead of presenting a degraded video as clean.
 *  Sits beside the regenerate menu — the recovery path — exactly like the outdated badge; degradation
 *  never auto-regenerates (cost stays user-controlled). */
export function DegradedBadge({ scenes }: DegradedBadgeProps) {
  if (scenes.length === 0) return null;
  const count = scenes.length;
  const label = `${count} ${count === 1 ? "scene" : "scenes"} degraded`;
  // The flattened, de-duplicated issue lines, shown on hover (a quoted scene may repeat an issue).
  const issues = [...new Set(scenes.flatMap((scene) => scene.issues))];
  return (
    <span className={styles.badge} role="status" title={issues.join("\n")}>
      <span className={styles.dot} aria-hidden="true" />
      <span className={styles.label}>{label}</span>
      <span className={styles.hint}>some scenes shipped with minor issues</span>
    </span>
  );
}
