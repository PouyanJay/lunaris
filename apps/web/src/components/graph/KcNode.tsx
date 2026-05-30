import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";

import {
  DIFFICULTY_TIER_COUNT,
  UNKNOWN_ORDER,
  type KcNode as KcNodeType,
} from "../../lib/graphLayout";
import styles from "./KcNode.module.css";

/** Custom React Flow node for a knowledge component: a hairline panel, mono data, a
 *  difficulty-tier accent bar, and a goal marker. Edges attach via top/bottom handles. */
export function KcNode({ data, selected }: NodeProps<KcNodeType>) {
  const { kc, tier, order, isGoal, isKnown } = data;
  const tierStyle = { "--node-tier": `var(--tier-${tier})` } as CSSProperties;

  const classes = [
    styles.node,
    isGoal ? styles.goal : "",
    isKnown ? styles.known : "",
    selected ? styles.selected : "",
  ]
    .filter(Boolean)
    .join(" ");

  const label = [
    `${kc.label}.`,
    `Difficulty tier ${tier} of ${DIFFICULTY_TIER_COUNT}.`,
    isGoal ? "Course goal." : "",
    isKnown ? "Already known." : "",
    `Bloom ceiling ${kc.bloomCeiling}.`,
    `${kc.sources.length} ${kc.sources.length === 1 ? "source" : "sources"}.`,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes} style={tierStyle} role="group" aria-label={label}>
      <Handle type="target" position={Position.Top} />
      <span className={styles.accent} aria-hidden="true" />

      <div className={styles.head}>
        <span className={`${styles.order} mono`}>
          {order > UNKNOWN_ORDER ? String(order).padStart(2, "0") : "—"}
        </span>
        {isGoal && <span className={styles.goalTag}>GOAL</span>}
        {isKnown && <span className={styles.knownTag}>KNOWN</span>}
      </div>

      <div className={styles.label}>{kc.label}</div>
      <p className={styles.definition}>{kc.definition}</p>

      <div className={styles.meta}>
        <span className={`${styles.bloom} mono`}>{kc.bloomCeiling.toUpperCase()}</span>
        <span className={`${styles.sources} mono`}>{kc.sources.length} src</span>
      </div>

      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
