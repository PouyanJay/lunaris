import { useMemo, useState } from "react";

import { matchResourcesToChapters } from "../../lib/chapterResources";
import type { TranscriptCue, VideoChapter } from "../../lib/videoJobs";
import type { Resource } from "../../types/course";
import { SegmentedControl, type Segment } from "../primitives/SegmentedControl";
import { CinemaPlayer } from "./CinemaPlayer";
import { LessonResources } from "./LessonResources";
import { TakeawaysGrid } from "./TakeawaysGrid";
import styles from "./WatchSurface.module.css";

interface WatchSurfaceProps {
  videoUrl: string;
  posterUrl: string | null;
  captionsUrl: string | null;
  chapters: VideoChapter[];
  transcript: TranscriptCue[];
  /** Accessible label for the video (the lesson/module title). */
  label: string;
  /** The lesson's key takeaways (its module objectives, de-scaffolded); empty hides the dock. */
  takeaways: string[];
  /** The lesson's curated resources (across all phases, deduped); empty hides the dock. */
  resources: Resource[];
  /** Leave Watch for the written lesson — the "Read" option of the consumption control. */
  onExitToRead: () => void;
}

/** How much accompanies the video. `read` is not a resting state — it hands off to the top-level
 *  Read mode — so the surface itself is only ever `watch` (player alone) or `both` (player + docks). */
type Consumption = "watch" | "both" | "read";

const CONSUMPTION_SEGMENTS: Segment<Consumption>[] = [
  { value: "watch", label: "Watch" },
  { value: "both", label: "Both" },
  { value: "read", label: "Read" },
];

/** The lesson-level docks shown in Both: the key-takeaways grid and any resources that matched no
 *  chapter. Each is omitted when empty. */
function WatchDocks({ takeaways, unmatched }: { takeaways: string[]; unmatched: Resource[] }) {
  return (
    <>
      {takeaways.length > 0 && <TakeawaysGrid takeaways={takeaways} />}
      {unmatched.length > 0 && <LessonResources resources={unmatched} />}
    </>
  );
}

/** The Watch surface (Cinema fuller mode): the ready lesson video as the lesson's front door — the
 *  chaptered, transcript-synced player — with a Watch/Both/Read consumption control. `Both` (the
 *  default) docks the lesson's per-chapter resources, key takeaways, and any unmatched resources
 *  beneath the video; `Watch` hides them for an immersive view; `Read` hands off to the written
 *  lesson. Takeaways/resources are lesson-level, so they sit under the whole video; each dock is
 *  omitted when the lesson has none. */
export function WatchSurface({
  videoUrl,
  posterUrl,
  captionsUrl,
  chapters,
  transcript,
  label,
  takeaways,
  resources,
  onExitToRead,
}: WatchSurfaceProps) {
  const [consumption, setConsumption] = useState<Consumption>("both");
  const showDocks = consumption === "both";

  // Resources dock under the chapter whose key terms they best cover (deterministic overlap); any
  // that match no chapter fall back to a lesson-level dock beneath the takeaways.
  const { byChapter, unmatched } = useMemo(
    () => matchResourcesToChapters(chapters, resources),
    [chapters, resources],
  );

  return (
    <div className={styles.surface}>
      <div className={styles.modeRow}>
        <SegmentedControl
          segments={CONSUMPTION_SEGMENTS}
          // `consumption` only ever rests at watch/both (Read hands off), but the control's value
          // must be one of its segments — so map the never-resting `read` back to `both` here.
          value={consumption === "read" ? "both" : consumption}
          onChange={(next) => (next === "read" ? onExitToRead() : setConsumption(next))}
          label="How to take this lesson"
        />
      </div>
      <CinemaPlayer
        videoUrl={videoUrl}
        posterUrl={posterUrl}
        captionsUrl={captionsUrl}
        chapters={chapters}
        transcript={transcript}
        label={label}
        chapterResources={showDocks ? byChapter : undefined}
      />
      {showDocks && <WatchDocks takeaways={takeaways} unmatched={unmatched} />}
    </div>
  );
}
