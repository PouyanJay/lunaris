import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";

import {
  DIFFICULTY_TIER_COUNT,
  UNKNOWN_ORDER,
  type KcNode as KcNodeType,
} from "../../lib/graphLayout";
import type { KcState } from "../../lib/kcStates";
import styles from "./KcNode.module.css";

const STATE_BADGE: Record<KcState, string> = {
  mastered: "MASTERED",
  up_next: "UP NEXT",
  locked: "LOCKED",
};

const STATE_SENTENCE: Record<KcState, string> = {
  mastered: "Mastered.",
  up_next: "Up next.",
  locked: "Locked — prerequisites remain.",
};

/** Custom React Flow node for a knowledge component: a hairline panel, mono data, a
 *  difficulty-tier spine, and a learning-state badge (MASTERED / UP NEXT / LOCKED — GOAL wins
 *  the face on the goal node; without progress data no state is claimed). Edges attach via
 *  top/bottom handles. */
export function KcNode({ data, selected }: NodeProps<KcNodeType>) {
  const { kc, tier, order, isGoal, state } = data;
  const tierStyle = { "--node-tier": `var(--tier-${tier})` } as CSSProperties;

  const classes = [
    styles.node,
    isGoal ? styles.goal : "",
    selected ? styles.selected : "",
  ]
    .filter(Boolean)
    .join(" ");

  // GOAL is the badge face on the goal node (the destination outranks its current state);
  // the state still reaches assistive tech through the label sentence below.
  const badge = isGoal
    ? { text: "GOAL", tone: "goal" }
    : state !== null
      ? { text: STATE_BADGE[state], tone: state }
      : null;

  const label = [
    `${kc.label}.`,
    `Difficulty tier ${tier} of ${DIFFICULTY_TIER_COUNT}.`,
    isGoal ? "Course goal." : "",
    state !== null ? STATE_SENTENCE[state] : "",
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
        {badge && (
          <span className={`${styles.badge} mono`} data-tone={badge.tone}>
            {badge.text}
          </span>
        )}
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
