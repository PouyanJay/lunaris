import { useCourseVideo } from "../../hooks/useCourseVideo";
import { FAILED_REGEN_MODES, readyRegenModes, resolveJobId } from "../../lib/videoJobs";
import type { CourseVideos, VideoArtifact } from "../../types/course";
import { DegradedBadge } from "./DegradedBadge";
import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";
import { OutdatedBadge } from "./OutdatedBadge";
import { RegenerateMenu } from "./RegenerateMenu";
import { VideoProgress } from "./VideoProgress";
import styles from "./OverviewSection.module.css";

interface OverviewSectionProps {
  videos: CourseVideos;
  apiBaseUrl: string;
  /** The course the slots belong to — keys the derive-at-read coordinate probe (course, kind). */
  courseId: string;
}

/** The course's Overview section (explainer-video V5): the course opens with video. The SUMMARY
 *  trailer ("what this course covers, module by module") comes first, then the OVERVIEW intro ("what
 *  this topic is and why it matters"). Each is a build-time artifact whose signed URL is resolved
 *  on view; an absent kind renders no slot, and a degraded one shows an honest "couldn't generate"
 *  rather than a broken player. With neither built, the whole section is absent. Docked on the
 *  Overview tab below the scope band (CourseOverview). */
export function OverviewSection({ videos, apiBaseUrl, courseId }: OverviewSectionProps) {
  if (!videos.summary && !videos.overview) return null;

  return (
    <section className={styles.overview} aria-label="Course overview videos">
      <CourseVideoSlot
        apiBaseUrl={apiBaseUrl}
        courseId={courseId}
        artifact={videos.summary}
        eyebrow="Course trailer"
        title="What this course covers"
        coverWord="What?"
        playLabel="Play the course trailer"
      />
      <CourseVideoSlot
        apiBaseUrl={apiBaseUrl}
        courseId={courseId}
        artifact={videos.overview}
        eyebrow="Topic overview"
        title="What this topic is and why it matters"
        coverWord="Why?"
        playLabel="Play the topic overview"
      />
    </section>
  );
}

interface CourseVideoSlotProps {
  apiBaseUrl: string;
  courseId: string;
  artifact: VideoArtifact | null | undefined;
  eyebrow: string;
  title: string;
  /** The short word shown on the black cover — these two slots are always the course's "What?" and
   *  "Why?" video, so the cover uses that as its title card. */
  coverWord: string;
  playLabel: string;
}

function CourseVideoSlot({
  apiBaseUrl,
  courseId,
  artifact,
  eyebrow,
  title,
  coverWord,
  playLabel,
}: CourseVideoSlotProps) {
  const { state, regenerate, stop, refresh } = useCourseVideo(apiBaseUrl, courseId, artifact);
  if (state.phase === "absent") return null;

  return (
    <div className={styles.slot}>
      <p className="eyebrow">{eyebrow}</p>
      {/* h3: a subsection under the Overview page's course-title h2 (CourseOverview), the only place
          this section renders — one level below that title, no skip (a11y heading hierarchy). */}
      <h3 className={styles.slotTitle}>{title}</h3>
      {state.phase === "loading" && (
        <div className={styles.stage} role="status" aria-label={`Loading ${title}`}>
          <span className={styles.shimmer} aria-hidden="true" />
        </div>
      )}
      {state.phase === "working" && (
        <div className={styles.stage}>
          <VideoProgress status={state.status} label={`Generating ${title}`} onStop={stop} />
        </div>
      )}
      {state.phase === "stopped" && (
        <>
          <div className={styles.stage}>
            <p className={styles.failedLabel} role="status">
              Generation stopped.
            </p>
          </div>
          {resolveJobId(artifact) && (
            <div className={styles.regenerateRow}>
              <RegenerateMenu
                available={FAILED_REGEN_MODES}
                onSelect={regenerate}
                triggerLabel="Try again"
              />
            </div>
          )}
        </>
      )}
      {state.phase === "ready" && (
        <>
          <GeneratedVideoPlayer
            videoUrl={state.videoUrl}
            posterUrl={state.posterUrl}
            captionsUrl={state.captionsUrl}
            label={playLabel}
            refreshPlayback={refresh}
            overlayTitle={coverWord}
          />
          <div className={styles.regenerateRow}>
            {state.stale && <OutdatedBadge />}
            <DegradedBadge scenes={state.degradedScenes} />
            <RegenerateMenu available={readyRegenModes(state.captionsUrl)} onSelect={regenerate} />
          </div>
        </>
      )}
      {state.phase === "failed" && (
        <>
          <div className={styles.stage}>
            <p className={styles.failedLabel} role="status">
              {state.error ??
                "This video couldn’t be generated. The rest of the course is unaffected."}
            </p>
          </div>
          {resolveJobId(artifact) && (
            <div className={styles.regenerateRow}>
              <RegenerateMenu
                available={FAILED_REGEN_MODES}
                onSelect={regenerate}
                triggerLabel="Try again"
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
