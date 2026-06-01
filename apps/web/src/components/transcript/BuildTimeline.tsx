import { useCallback, useEffect, useMemo, useRef, useState, type Ref } from "react";

import {
  buildTimeline,
  latestPlan,
  type StageTimes,
  type TimelinePhase,
} from "../../lib/buildTimeline";
import { formatDuration } from "../../lib/formatDuration";
import type { AgentEvent, ProgressEvent } from "../../types/course";
import { TodoList } from "./TodoList";
import { ToolCallCard } from "./ToolCallCard";
import styles from "./BuildTimeline.module.css";

interface BuildTimelineProps {
  topic: string;
  events: ProgressEvent[];
  agentEvents: AgentEvent[];
  /** Client-stamped stage arrival times, for per-phase durations. Optional (omitted in tests/replay). */
  stageTimes?: StageTimes | undefined;
}

/** The live build canvas: a pinned plan panel (the agent's todos + overall progress) over a vertical
 *  timeline of the pipeline's major phases. Each phase is a node on a hairline spine (dot + label +
 *  summary + duration + status); every phase with content is expanded by default and streams its
 *  reasoning and tool calls — the user can collapse any of them. Replaces the horizontal StageRail. */
export function BuildTimeline({ topic, events, agentEvents, stageTimes }: BuildTimelineProps) {
  const phases = useMemo(
    () => buildTimeline(events, agentEvents, stageTimes),
    [events, agentEvents, stageTimes],
  );
  const plan = useMemo(() => latestPlan(agentEvents), [agentEvents]);
  const activeKey = phases.find((phase) => phase.status === "active")?.key ?? null;

  // Phases are expanded by default; this tracks the ones the user manually COLLAPSED, so newly
  // streamed content is always visible without a click while staying dismissible.
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const toggle = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  // Keep the active phase in view as its events stream in.
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLLIElement>(null);
  useEffect(() => {
    const node = activeRef.current;
    const container = containerRef.current;
    if (node && container) container.scrollTop = node.offsetTop;
  }, [agentEvents.length, activeKey, collapsed]);

  return (
    <div
      className={styles.timeline}
      ref={containerRef}
      role="region"
      aria-label={`Building ${topic}`}
      tabIndex={0}
    >
      <p className="sr-only" role="status" aria-live="polite">
        {activeKey ? `Building: ${phases.find((p) => p.key === activeKey)?.label}` : "Starting…"}
      </p>
      {plan && (
        <div className={styles.plan}>
          <TodoList todos={plan} />
        </div>
      )}
      <ol className={styles.phases}>
        {phases.map((phase) => {
          const hasBody = phase.entries.length > 0;
          return (
            <PhaseNode
              key={phase.key}
              phase={phase}
              expanded={hasBody && !collapsed.has(phase.key)}
              expandable={hasBody}
              onToggle={() => toggle(phase.key)}
              nodeRef={phase.status === "active" ? activeRef : undefined}
            />
          );
        })}
      </ol>
    </div>
  );
}

interface PhaseNodeProps {
  phase: TimelinePhase;
  expanded: boolean;
  expandable: boolean;
  onToggle: () => void;
  // Explicit `| undefined` for the repo's exactOptionalPropertyTypes (the active node passes the ref;
  // the others pass undefined).
  nodeRef?: Ref<HTMLLIElement> | undefined;
}

function PhaseNode({ phase, expanded, expandable, onToggle, nodeRef }: PhaseNodeProps) {
  const duration = phase.durationMs !== null ? formatDuration(phase.durationMs) : null;
  const header = (
    <>
      <span className={styles.dot} data-status={phase.status} aria-hidden="true" />
      <span className={styles.label}>{phase.label}</span>
      {phase.summary && <span className={`mono ${styles.summary}`}>{phase.summary}</span>}
      {phase.status === "active" && (
        <span className={`mono ${styles.live}`} aria-hidden="true">
          running…
        </span>
      )}
      {duration && <span className={`mono ${styles.duration}`}>{duration}</span>}
    </>
  );

  return (
    <li className={styles.phase} data-status={phase.status} ref={nodeRef}>
      {expandable ? (
        <button
          type="button"
          className={styles.header}
          onClick={onToggle}
          aria-expanded={expanded}
          aria-label={`${phase.label}${phase.summary ? ` — ${phase.summary}` : ""}${
            duration ? ` (${duration})` : ""
          }`}
        >
          {header}
        </button>
      ) : (
        <div className={styles.header}>{header}</div>
      )}

      {expanded && (
        <div className={styles.body}>
          {phase.entries.map((entry) =>
            entry.kind === "reasoning" ? (
              <p key={entry.key} className={styles.reasoning}>
                {entry.text}
              </p>
            ) : (
              <ToolCallCard
                key={entry.key}
                tool={entry.tool}
                args={entry.args}
                result={entry.result}
              />
            ),
          )}
        </div>
      )}
    </li>
  );
}
