import { useId } from "react";

import { SegmentedControl } from "../primitives/SegmentedControl";
import { Switch } from "../primitives/Switch";
import type { ComposerLevel } from "../../lib/composerLevel";
import type { DiscoveryDepth } from "../../types/course";
import styles from "./ComposerOptions.module.css";

interface ComposerOptionsProps {
  depth: DiscoveryDepth;
  onDepthChange: (depth: DiscoveryDepth) => void;
  level: ComposerLevel;
  onLevelChange: (level: ComposerLevel) => void;
  officialOnly: boolean;
  onOfficialOnlyChange: (value: boolean) => void;
}

const DEPTHS: { value: DiscoveryDepth; label: string }[] = [
  { value: "standard", label: "Standard" },
  { value: "thorough", label: "Thorough" },
];

const LEVELS: { value: ComposerLevel; label: string }[] = [
  { value: "recommended", label: "Recommended" },
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

/** The composer's options bar (P5): the quick build controls that sit under the topic input —
 *  search Depth, target Level (maps to the clarifier's level answer), and the "Official sources
 *  only" trust switch. The deeper personalization brief stays reachable below; these are the
 *  one-glance knobs. All feed straight into the build. */
export function ComposerOptions({
  depth,
  onDepthChange,
  level,
  onLevelChange,
  officialOnly,
  onOfficialOnlyChange,
}: ComposerOptionsProps) {
  const depthLabelId = useId();
  const levelLabelId = useId();
  const officialLabelId = useId();
  return (
    <div className={styles.bar}>
      <div className={styles.option}>
        <span id={depthLabelId} className={`eyebrow ${styles.label}`}>
          Depth
        </span>
        <SegmentedControl
          segments={DEPTHS}
          value={depth}
          onChange={onDepthChange}
          aria-labelledby={depthLabelId}
        />
      </div>
      <div className={styles.option}>
        <span id={levelLabelId} className={`eyebrow ${styles.label}`}>
          Level
        </span>
        <SegmentedControl
          segments={LEVELS}
          value={level}
          onChange={onLevelChange}
          aria-labelledby={levelLabelId}
        />
      </div>
      <div className={`${styles.option} ${styles.switchOption}`}>
        <span id={officialLabelId} className={`eyebrow ${styles.label}`}>
          Official sources only
        </span>
        <Switch
          checked={officialOnly}
          onChange={onOfficialOnlyChange}
          aria-labelledby={officialLabelId}
        />
      </div>
    </div>
  );
}
