import { useMemo, useState, type ReactNode } from "react";

import { buildTimeline, consoleEntries, type StageTimes } from "../../lib/buildTimeline";
import type { AgentEvent, ProgressEvent } from "../../types/course";
import { SegmentedControl } from "../primitives/SegmentedControl";
import { BuildTimeline } from "../transcript/BuildTimeline";
import { ConsoleTicker } from "./ConsoleTicker";
import { PipelineRail } from "./PipelineRail";
import styles from "./BuildControlRoom.module.css";

type BuildView = "room" | "transcript";

const VIEWS: { value: BuildView; label: string }[] = [
  { value: "room", label: "Control room" },
  { value: "transcript", label: "Transcript" },
];

interface BuildControlRoomProps {
  topic: string;
  events: ProgressEvent[];
  agentEvents: AgentEvent[];
  /** Client-stamped stage arrivals (live path only) — replay omits them, so no durations there. */
  stageTimes?: StageTimes | undefined;
  /** The run has finished (terminal course frame or run_completed in the log) — every phase
   *  renders done even when tail progress events were coalesced (the Verify-freeze fix). */
  complete?: boolean;
  /** Extra instrument for the rail (the videos-finishing meter after publish). */
  videosPanel?: ReactNode;
}

/** The build control room (P8): one lens over the same event streams the transcript renders —
 *  a blueprint canvas (dominant), the agent-console ticker (bottom strip), and the instrument
 *  rail (pipeline + grounding instruments). The full branded transcript stays one toggle away;
 *  both views fold the identical (events, agentEvents) inputs, live or replayed. */
export function BuildControlRoom({
  topic,
  events,
  agentEvents,
  stageTimes,
  complete = false,
  videosPanel,
}: BuildControlRoomProps) {
  const [view, setView] = useState<BuildView>("room");
  const phases = useMemo(
    () => buildTimeline(events, agentEvents, stageTimes ?? {}, { complete }),
    [events, agentEvents, stageTimes, complete],
  );
  const ticker = useMemo(() => consoleEntries(agentEvents), [agentEvents]);

  return (
    <div
      className={styles.room}
      role="region"
      aria-label={`Building ${topic}`}
      data-view={view}
    >
      <div className={styles.viewBar}>
        <SegmentedControl segments={VIEWS} value={view} onChange={setView} label="Build view" />
      </div>

      {view === "transcript" ? (
        <div className={`${styles.transcript} scroller`}>
          <BuildTimeline
            topic={topic}
            events={events}
            agentEvents={agentEvents}
            {...(stageTimes ? { stageTimes } : {})}
          />
        </div>
      ) : (
        <div className={styles.grid}>
          <div className={styles.main}>
            <section className={styles.blueprint} aria-label="Blueprint">
              <header className={styles.blueprintHead}>
                <span className="eyebrow">Blueprint</span>
                <span className={styles.strapline}>
                  Assembling the prerequisite graph — nothing is placed before what it depends on.
                </span>
              </header>
              <div className={styles.blueprintBody}>
                {/* The structured graph payload lands in T2; until then (and for runs recorded
                    before it existed) the canvas states what's happening rather than faking nodes. */}
                <p className={styles.blueprintFallback}>
                  The prerequisite graph appears here as concepts are mapped.
                </p>
              </div>
            </section>
            <ConsoleTicker entries={ticker} live={!complete} />
          </div>
          <aside className={styles.rail}>
            <PipelineRail phases={phases} />
            {videosPanel}
          </aside>
        </div>
      )}
    </div>
  );
}
