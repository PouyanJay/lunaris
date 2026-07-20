import { useMemo } from "react";

import { matchResourcesToChapters } from "../../lib/chapterResources";
import type { TranscriptCue, VideoChapter } from "../../lib/videoJobs";
import type { Resource } from "../../types/course";
import { CinemaPlayer } from "./CinemaPlayer";
import { LessonResources } from "./LessonResources";
import { LessonScaffold } from "./LessonScaffold";
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

/** The Watch surface (Cinema fuller mode): the ready lesson video as the lesson's front door — the
 *  chaptered, transcript-synced player — with the lesson's key takeaways and curated resources
 *  docked beneath it. Both are lesson-level (the module objectives and the phase resources, not
 *  scene-scoped), so they sit under the whole video rather than any one chapter; each dock is
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
      {takeaways.length > 0 && (
        <LessonScaffold title="Key takeaways" cue="The gist of this lesson" items={takeaways} />
      )}
      {unmatched.length > 0 && <LessonResources resources={unmatched} />}
    </div>
  );
}
