import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  buildTimeline,
  latestPlan,
  type StageTimes,
  type TimelinePhase,
} from "../../lib/buildTimeline";
import { formatDuration } from "../../lib/formatDuration";
import type { AgentEvent, ProgressEvent, ProgressStage } from "../../types/course";
import { DiscoverySources } from "./DiscoverySources";
import { LiveActivity } from "./LiveActivity";
import { ReasoningBeat } from "./ReasoningBeat";
import { TodoList } from "./TodoList";
import { ToolCallCard } from "./ToolCallCard";
import styles from "./BuildTimeline.module.css";

// Within this many px of the bottom the user counts as "pinned" — auto-scroll keeps following.
const SCROLL_PIN_PX = 80;

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
  // When the active phase began (its stage's arrival), so its status line can show a live clock.
  // The pre-stage "intro" node isn't a stage, so it carries no timer.
  const activeStartedAt = isTimedPhase(activeKey) ? stageTimes?.[activeKey] : undefined;

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

  // Follow the newest content as it streams — but only while the user is pinned near the bottom.
  // Once they scroll up to read, stop yanking them back (it resumes when they return to the bottom),
  // so a long stream never traps them at the foot of the transcript.
  const containerRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);
  const onScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const fromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    pinnedRef.current = fromBottom < SCROLL_PIN_PX;
  }, []);
  useEffect(() => {
    const container = containerRef.current;
    if (container && pinnedRef.current) container.scrollTop = container.scrollHeight;
  }, [agentEvents.length, events.length, collapsed]);

  return (
    <div
      className={styles.timeline}
      ref={containerRef}
      onScroll={onScroll}
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
              startedAt={phase.status === "active" ? activeStartedAt : undefined}
            />
          );
        })}
      </ol>
    </div>
  );
}

/** A phase keyed by a real ProgressStage (so it has a stage-arrival time) — i.e. not the pre-stage
 *  "intro" node and not the no-active-phase (`null`) case. */
function isTimedPhase(key: string | null): key is ProgressStage {
  return key !== null && key !== "intro";
}

interface PhaseNodeProps {
  phase: TimelinePhase;
  expanded: boolean;
  expandable: boolean;
  onToggle: () => void;
  /** When the active phase began (ms epoch), for its live clock; undefined for non-active nodes. */
  startedAt?: number | undefined;
}

function PhaseNode({ phase, expanded, expandable, onToggle, startedAt }: PhaseNodeProps) {
  const duration = phase.durationMs !== null ? formatDuration(phase.durationMs) : null;
  // Split the vetted sources (rendered as one grouped table) from the reasoning/tool beats.
  const sources = phase.entries.flatMap((entry) => (entry.kind === "source" ? [entry.source] : []));
  const beats = phase.entries.filter((entry) => entry.kind !== "source");
  const header = (
    <>
      <span className={styles.dot} data-status={phase.status} aria-hidden="true" />
      <span className={styles.label}>{phase.label}</span>
      {phase.summary && <span className={`mono ${styles.summary}`}>{phase.summary}</span>}
      {phase.status === "active" && <LiveActivity phaseKey={phase.key} startedAt={startedAt} />}
      {duration && <span className={`mono ${styles.duration}`}>{duration}</span>}
    </>
  );

  return (
    <li className={styles.phase} data-status={phase.status}>
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
          {/* The vetted sources are grouped into one streaming table (the source-vetting view),
              ahead of the phase's reasoning/tool beats; other phases have none. */}
          {sources.length > 0 && <DiscoverySources sources={sources} />}
          {beats.map((entry, index) => {
            if (entry.kind === "tool") {
              return (
                <ToolCallCard
                  key={entry.key}
                  tool={entry.tool}
                  args={entry.args}
                  result={entry.result}
                />
              );
            }
            // The live caret shows only on the active phase's latest beat while it is still
            // streaming — the visible signal the agent's reasoning is forming token-by-token.
            const isLiveCaret =
              entry.streaming === true && phase.status === "active" && index === beats.length - 1;
            return <ReasoningBeat key={entry.key} text={entry.text} streaming={isLiveCaret} />;
          })}
        </div>
      )}
    </li>
  );
}
