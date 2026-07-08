import { useMemo, useState, type ReactNode } from "react";

import { blueprintFromEvents } from "../../lib/blueprint";
import { buildTimeline, consoleEntries, type StageTimes } from "../../lib/buildTimeline";
import { groundingLedger, readinessScorecard } from "../../lib/instruments";
import type { AgentEvent, ProgressEvent } from "../../types/course";
import { SegmentedControl } from "../primitives/SegmentedControl";
import { BuildTimeline } from "../transcript/BuildTimeline";
import { BlueprintCanvas } from "./BlueprintCanvas";
import { ConsoleTicker } from "./ConsoleTicker";
import { GroundingLedgerPanel } from "./GroundingLedgerPanel";
import { PipelineRail } from "./PipelineRail";
import { ReadinessScorecard } from "./ReadinessScorecard";
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
  /** Whether the feed is live (pulses the console dot). Defaults to `!complete`; a static
   *  replay of a past run passes false — a still log must not claim liveness. */
  live?: boolean;
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
  live = !complete,
  videosPanel,
}: BuildControlRoomProps) {
  const [view, setView] = useState<BuildView>("room");
  const phases = useMemo(
    () => buildTimeline(events, agentEvents, stageTimes ?? {}, { complete }),
    [events, agentEvents, stageTimes, complete],
  );
  const ticker = useMemo(() => consoleEntries(agentEvents), [agentEvents]);
  const blueprint = useMemo(() => blueprintFromEvents(events, complete), [events, complete]);
  const ledger = useMemo(() => groundingLedger(events, agentEvents), [events, agentEvents]);
  const gauges = useMemo(() => readinessScorecard(events, agentEvents), [events, agentEvents]);

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
                {blueprint?.mappedCount != null && (
                  <span className={`${styles.mapped} mono`}>
                    {blueprint.mappedCount} / {blueprint.totalCount} mapped
                  </span>
                )}
              </header>
              <div className={styles.blueprintBody}>
                {blueprint ? (
                  <BlueprintCanvas blueprint={blueprint} />
                ) : (
                  /* No structured graph yet (early phases / pre-P8 run logs): say what's
                     happening rather than faking nodes. */
                  <p className={styles.blueprintFallback}>
                    The prerequisite graph appears here as concepts are mapped.
                  </p>
                )}
              </div>
            </section>
            <ConsoleTicker entries={ticker} live={live && !complete} />
          </div>
          <aside className={styles.rail}>
            <PipelineRail phases={phases} />
            {gauges.length > 0 && <ReadinessScorecard gauges={gauges} />}
            {ledger && <GroundingLedgerPanel ledger={ledger} />}
            {videosPanel}
          </aside>
        </div>
      )}
    </div>
  );
}
