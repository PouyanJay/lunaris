import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { CSSProperties } from "react";

import type { BlueprintNodeState } from "../../lib/blueprint";
import { UNKNOWN_ORDER, type KcNodeData } from "../../lib/graphLayout";
import type { Node } from "@xyflow/react";
import styles from "./BlueprintNode.module.css";

/** The blueprint node's data: the Map node's layout data plus its assembly state (null when the
 *  log carried structure but no module mapping — the card renders without a state claim). */
export interface BlueprintNodeData extends KcNodeData {
  buildState: BlueprintNodeState | null;
}

export type BlueprintFlowNode = Node<BlueprintNodeData, "blueprint">;

const STATE_BADGE: Record<BlueprintNodeState, string> = {
  queued: "QUEUED",
  mapping: "MAPPING",
  mapped: "MAPPED",
};

const STATE_SENTENCE: Record<BlueprintNodeState, string> = {
  queued: "Queued.",
  mapping: "Mapping.",
  mapped: "Mapped.",
};

/** A concept assembling on the live blueprint (P8): the Map card compacted to scaffolding —
 *  tier spine, mono order, assembly badge; dashed and dim while queued, pulsing while its
 *  module is being authored. */
export function BlueprintNode({ data }: NodeProps<BlueprintFlowNode>) {
  const { kc, tier, order, isGoal, buildState } = data;
  const tierStyle = { "--node-tier": `var(--tier-${tier})` } as CSSProperties;

  const label = [
    `${kc.label}.`,
    buildState ? STATE_SENTENCE[buildState] : "",
    isGoal ? "Course goal." : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={styles.node}
      style={tierStyle}
      data-state={buildState ?? undefined}
      data-goal={isGoal || undefined}
      role="group"
      aria-label={label}
    >
      <Handle type="target" position={Position.Top} />
      {buildState === "mapping" && <span className={styles.pulse} aria-hidden="true" />}
      <span className={styles.spine} aria-hidden="true" />
      <div className={styles.head}>
        <span className={`${styles.order} mono`}>
          {order > UNKNOWN_ORDER ? String(order).padStart(2, "0") : "—"}
        </span>
        {(buildState || isGoal) && (
          <span className={`${styles.badge} mono`} data-tone={isGoal ? "goal" : buildState}>
            {isGoal ? "GOAL" : STATE_BADGE[buildState!]}
          </span>
        )}
      </div>
      <div className={styles.title}>{kc.label}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
