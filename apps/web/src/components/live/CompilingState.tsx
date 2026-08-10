import { ProgressBar } from "../primitives/ProgressBar";
import type { CompileProgress } from "../../lib/streamGraph";
import styles from "./CompilingState.module.css";

interface CompilingStateProps {
  topic: string;
  /** The compiler's latest beat, or null before it has said anything. */
  progress: CompileProgress | null;
}

/** What each phase is doing, in the learner's terms rather than the compiler's. The wire carries
 *  counts, not copy, so this is the only place the phases are put into words. */
const PHASE_COPY: Record<CompileProgress["phase"], string> = {
  decomposing: "Working out which ideas this is made of",
  authoring: "Writing the teaching notes for each idea",
  assembling: "Putting them in the order they have to be learned",
};

/** The screen a learner spends the compile on — minutes, so it has to be worth watching.
 *
 *  Two shapes, because the compile has two shapes. Decomposition is one long call with nothing
 *  countable in it, so it is narrated; authoring is one call per concept, so it is measured. A bar
 *  sitting at zero through the first minute would read as a stall, which is why the bar only
 *  appears once there is something real for it to show. */
export function CompilingState({ topic, progress }: CompilingStateProps) {
  const phase = progress?.phase ?? "decomposing";
  const total = progress?.total ?? 0;
  const done = progress?.done ?? 0;

  return (
    <div className={styles.compiling}>
      <div className={styles.head}>
        {/* Only the phase line is live. Putting the whole header in the region would re-announce
            the topic on every phase change, and the count is deliberately outside it too: twelve
            announcements for twelve concepts is noise, three for three phases is progress. */}
        <p className={`eyebrow ${styles.eyebrow}`} role="status">
          {PHASE_COPY[phase]}
        </p>
        <h1 className={styles.title}>{topic}</h1>
      </div>

      {total > 0 ? (
        <div className={styles.measure}>
          <ProgressBar value={done / total} label="Concepts written" />
          <p className={styles.count}>
            <span className="mono">
              {done} / {total}
            </span>{" "}
            concepts
          </p>
        </div>
      ) : (
        <p className={styles.body}>
          Live is reading the subject end to end before it writes anything. This takes a couple of
          minutes, and the map is worth more than the wait.
        </p>
      )}

      {/* A skeleton of the levels being built, rather than a spinner: it shows the shape the
          answer will take, and it keeps the canvas from jumping when the map lands. */}
      <div className={styles.skeleton} aria-hidden="true">
        {[3, 2, 4].map((width, level) => (
          <div key={level} className={styles.skeletonLevel}>
            {Array.from({ length: width }, (_, index) => (
              <div key={index} className={styles.skeletonNode} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
