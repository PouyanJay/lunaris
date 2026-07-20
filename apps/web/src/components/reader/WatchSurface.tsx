import type { TranscriptCue, VideoChapter } from "../../lib/videoJobs";
import { CinemaPlayer } from "./CinemaPlayer";
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
}

/** The Watch surface (Cinema fuller mode): the ready lesson video as the lesson's front door — the
 *  chaptered, transcript-synced player — with the lesson's key takeaways docked beneath it. The
 *  takeaways are lesson-level (the module objectives, not scene-scoped), so they sit under the whole
 *  video rather than any one chapter; the dock is omitted when the lesson has none. */
export function WatchSurface({
  videoUrl,
  posterUrl,
  captionsUrl,
  chapters,
  transcript,
  label,
  takeaways,
}: WatchSurfaceProps) {
  return (
    <div className={styles.surface}>
      <CinemaPlayer
        videoUrl={videoUrl}
        posterUrl={posterUrl}
        captionsUrl={captionsUrl}
        chapters={chapters}
        transcript={transcript}
        label={label}
      />
      {takeaways.length > 0 && (
        <LessonScaffold title="Key takeaways" cue="The gist of this lesson" items={takeaways} />
      )}
    </div>
  );
}
