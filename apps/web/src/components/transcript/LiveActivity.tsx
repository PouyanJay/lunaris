import { useEffect, useState } from "react";

import { LunarSpinner } from "./LunarSpinner";
import styles from "./LiveActivity.module.css";

/** Phase-scoped "spinner verbs": the personality layer (à la Claude Code), cycling while a phase
 *  runs. The literal actions (tool cards, reasoning) already stream in the timeline body, so these
 *  stay evocative rather than re-stating them. Keyed by ProgressStage (+ the pre-stage "intro"). */
const VERBS: Record<string, readonly string[]> = {
  intro: ["Planning the build…", "Thinking it through…", "Getting started…"],
  brief_interpreted: ["Interpreting the request…", "Framing the goal…", "Reading the level…"],
  standard_researched: [
    "Researching the standard…",
    "Vetting the sources…",
    "Grounding the targets…",
  ],
  learner_modeled: ["Modeling the learner…", "Gauging what you know…", "Finding your edge…"],
  concepts_extracted: ["Reading the topic…", "Extracting concepts…", "Naming the pieces…"],
  graph_built: ["Mapping prerequisites…", "Ordering concepts…", "Untangling dependencies…"],
  curriculum_designed: ["Designing the curriculum…", "Sequencing modules…", "Setting objectives…"],
  module_authored: ["Authoring lessons…", "Writing worked examples…", "Composing each phase…"],
  claims_verified: ["Grounding claims…", "Weighing the evidence…", "Verifying against the corpus…"],
  run_completed: ["Finalizing…", "Assembling the course…", "Wrapping up…"],
};
const DEFAULT_VERBS = ["Working…", "Thinking…"] as const;
const CYCLE_MS = 2400;

interface LiveActivityProps {
  /** The active phase's key (a ProgressStage, or "intro" for the pre-stage node). Picks the verbs. */
  phaseKey: string;
  /** When this phase became active (ms epoch), for the live elapsed clock. Omitted in tests/replay. */
  startedAt?: number | undefined;
}

/** The active-phase status line: the branded moon spinner + a shimmering, cycling verb + a live
 *  elapsed clock. Decorative (`aria-hidden`) — the timeline's sr-only live region announces the
 *  active phase to screen readers, so this layer is purely visual personality. */
export function LiveActivity({ phaseKey, startedAt }: LiveActivityProps) {
  const verbs = VERBS[phaseKey] ?? DEFAULT_VERBS;
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
    const id = setInterval(() => setIndex((i) => (i + 1) % verbs.length), CYCLE_MS);
    return () => clearInterval(id);
  }, [phaseKey, verbs.length]);

  // `index` is reset to 0 on every phase change and only ever advanced `(i + 1) % length`, so the
  // modulo keeps the read in range; the array is non-empty by construction.
  const verb = verbs[index % verbs.length]!;

  return (
    <span className={styles.activity} aria-hidden="true">
      <LunarSpinner />
      {/* `key={verb}` remounts on change so the shimmer restarts its sweep each verb. */}
      <span key={verb} className={styles.verb}>
        {verb}
      </span>
      {startedAt !== undefined && <Elapsed startedAt={startedAt} />}
    </span>
  );
}

function Elapsed({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000));
  return <span className={`mono ${styles.elapsed}`}>{formatClock(seconds)}</span>;
}

/** Seconds → `m:ss` (a running clock; minutes are not zero-padded, e.g. `0:07`, `2:05`). */
function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}
