import { useMemo } from "react";

import { matchResourcesToChapters } from "../../lib/chapterResources";
import type { TranscriptCue, VideoChapter } from "../../lib/videoJobs";
import type { Resource } from "../../types/course";
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
}

/** The lesson-level docks beneath the player: the key-takeaways grid and any resources that matched
 *  no chapter. Each is omitted when empty. */
function WatchDocks({ takeaways, unmatched }: { takeaways: string[]; unmatched: Resource[] }) {
  return (
    <>
      {takeaways.length > 0 && <TakeawaysGrid takeaways={takeaways} />}
      {unmatched.length > 0 && <LessonResources resources={unmatched} />}
    </>
  );
}

/** The Watch surface (Cinema): the ready lesson video as the lesson's front door — the chaptered,
 *  transcript-synced player with all its functionality. Navigable chapters and their per-chapter
 *  resources ride the rail on the right; the lesson's key takeaways and any unmatched resources dock
 *  beneath the video. Takeaways/resources are lesson-level, so they sit under the whole video; each
 *  dock is omitted when the lesson has none. */
export function WatchSurface({
  videoUrl,
  posterUrl,
  captionsUrl,
  chapters,
  transcript,
  label,
  takeaways,
  resources,
}: WatchSurfaceProps) {
  // Resources dock under the chapter whose key terms they best cover (deterministic overlap); any
  // that match no chapter fall back to a lesson-level dock beneath the takeaways.
  const { byChapter, unmatched } = useMemo(
    () => matchResourcesToChapters(chapters, resources),
    [chapters, resources],
  );

  return (
    <div className={styles.surface}>
      <CinemaPlayer
        videoUrl={videoUrl}
        posterUrl={posterUrl}
        captionsUrl={captionsUrl}
        chapters={chapters}
        transcript={transcript}
        label={label}
        chapterResources={byChapter}
      />
      <WatchDocks takeaways={takeaways} unmatched={unmatched} />
    </div>
  );
}
