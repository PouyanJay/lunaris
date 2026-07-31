import { useId } from "react";

import { SegmentedControl } from "../primitives/SegmentedControl";
import { Switch } from "../primitives/Switch";
import type { ComposerLevel } from "../../lib/composerLevel";
import type { Product } from "../../lib/product";
import type { DiscoveryDepth } from "../../types/course";
import styles from "./ComposerOptions.module.css";

interface ComposerOptionsProps {
  /** Which product the topic will be sent to. The row is absent from the DOM entirely unless
   *  `onModeChange` is supplied — that is how the app layer signals Lunaris is two products, so
   *  this stays presentational and never reaches for auth context itself. */
  mode: Product;
  onModeChange?: ((mode: Product) => void) | undefined;
  depth: DiscoveryDepth;
  onDepthChange: (depth: DiscoveryDepth) => void;
  level: ComposerLevel;
  onLevelChange: (level: ComposerLevel) => void;
  officialOnly: boolean;
  onOfficialOnlyChange: (value: boolean) => void;
}

const MODES: { value: Product; label: string }[] = [
  { value: "studio", label: "Studio" },
  { value: "live", label: "Live" },
];

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
  mode,
  onModeChange,
  depth,
  onDepthChange,
  level,
  onLevelChange,
  officialOnly,
  onOfficialOnlyChange,
}: ComposerOptionsProps) {
  const modeLabelId = useId();
  const depthLabelId = useId();
  const levelLabelId = useId();
  const officialLabelId = useId();
  return (
    <div className={styles.bar}>
      {/* The fork sits first: it decides what every control below it even means. */}
      {onModeChange && (
        <div className={styles.option}>
          <span id={modeLabelId} className={`eyebrow ${styles.label}`}>
            Mode
          </span>
          <SegmentedControl
            segments={MODES}
            value={mode}
            onChange={onModeChange}
            aria-labelledby={modeLabelId}
          />
        </div>
      )}
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
