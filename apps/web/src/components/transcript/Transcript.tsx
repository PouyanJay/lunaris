import { useEffect, useRef } from "react";

import { groupAgentEvents, latestTodos } from "../../lib/groupAgentEvents";
import type { AgentEvent, ProgressEvent } from "../../types/course";
import { StageRail } from "./StageRail";
import { TodoList } from "./TodoList";
import { ToolCallCard } from "./ToolCallCard";
import styles from "./Transcript.module.css";

interface TranscriptProps {
  topic: string;
  events: ProgressEvent[];
  agentEvents: AgentEvent[];
}

/** The live build canvas: a compact stage rail, the agent's current plan, and the streaming
 *  transcript of its reasoning and tool calls. Replaces the flat BuildProgress checklist. */
export function Transcript({ topic, events, agentEvents }: TranscriptProps) {
  const entries = groupAgentEvents(agentEvents);
  const todos = latestTodos(agentEvents);
  const feedRef = useRef<HTMLDivElement>(null);

  // Follow the live feed: keep the newest beat in view as events stream in.
  useEffect(() => {
    const feed = feedRef.current;
    if (feed) feed.scrollTop = feed.scrollHeight;
  }, [agentEvents.length, todos]);

  return (
    <section className={styles.transcript} aria-label={`Building ${topic}`}>
      <StageRail events={events} />
      {todos && (
        <div className={styles.planRegion}>
          <TodoList todos={todos} />
        </div>
      )}
      {/* Focusable + labelled so keyboard users can scroll the feed; not a live region (the stage
          rail announces progress, so the transcript stays quiet for screen readers). */}
      <div
        className={styles.feed}
        ref={feedRef}
        tabIndex={0}
        role="region"
        aria-label="Agent transcript"
      >
        {entries.length === 0 ? (
          <p className={styles.waiting}>The agent is starting its work…</p>
        ) : (
          <ol className={styles.entries}>
            {entries.map((entry) => (
              <li key={entry.key} className={styles.entry}>
                {entry.kind === "reasoning" ? (
                  <p className={styles.reasoning}>{entry.text}</p>
                ) : (
                  <ToolCallCard tool={entry.tool} args={entry.args} result={entry.result} />
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
