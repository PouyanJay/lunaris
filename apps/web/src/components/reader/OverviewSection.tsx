import { useCourseVideo } from "../../hooks/useCourseVideo";
import { FAILED_REGEN_MODES, readyRegenModes } from "../../lib/videoJobs";
import type { CourseVideos, VideoArtifact } from "../../types/course";
import { GeneratedVideoPlayer } from "./GeneratedVideoPlayer";
import { OutdatedBadge } from "./OutdatedBadge";
import { RegenerateMenu } from "./RegenerateMenu";
import styles from "./OverviewSection.module.css";

interface OverviewSectionProps {
  videos: CourseVideos;
  apiBaseUrl: string;
}

/** The course's Overview section (explainer-video V5): the course opens with video. The SUMMARY
 *  trailer ("what this course covers, module by module") comes first, then the OVERVIEW intro ("what
 *  this topic is and why it matters"). Each is a build-time artifact whose signed URL is resolved
 *  on view; an absent kind renders no slot, and a degraded one shows an honest "couldn't generate"
 *  rather than a broken player. With neither built, the whole section is absent. */
export function OverviewSection({ videos, apiBaseUrl }: OverviewSectionProps) {
  if (!videos.summary && !videos.overview) return null;

  return (
    <section className={styles.overview} aria-label="Course overview videos">
      <CourseVideoSlot
        apiBaseUrl={apiBaseUrl}
        artifact={videos.summary}
        eyebrow="Course trailer"
        title="What this course covers"
        playLabel="Play the course trailer"
      />
      <CourseVideoSlot
        apiBaseUrl={apiBaseUrl}
        artifact={videos.overview}
        eyebrow="Topic overview"
        title="What this topic is and why it matters"
        playLabel="Play the topic overview"
      />
    </section>
  );
}

interface CourseVideoSlotProps {
  apiBaseUrl: string;
  artifact: VideoArtifact | null | undefined;
  eyebrow: string;
  title: string;
  playLabel: string;
}

function CourseVideoSlot({
  apiBaseUrl,
  artifact,
  eyebrow,
  title,
  playLabel,
}: CourseVideoSlotProps) {
  const { state, regenerate } = useCourseVideo(apiBaseUrl, artifact);
  if (state.phase === "absent") return null;

  return (
    <div className={styles.slot}>
      <p className="eyebrow">{eyebrow}</p>
      {/* h2: a peer of the lesson title under the course h1 — the Overview renders before the lesson,
          so an h3 here would skip a level (a11y heading hierarchy). */}
      <h2 className={styles.slotTitle}>{title}</h2>
      {(state.phase === "loading" || state.phase === "working") && (
        <div className={styles.stage} role="status" aria-label={`Loading ${title}`}>
          <span className={styles.shimmer} aria-hidden="true" />
        </div>
      )}
      {state.phase === "ready" && (
        <>
          <GeneratedVideoPlayer
            videoUrl={state.videoUrl}
            posterUrl={state.posterUrl}
            captionsUrl={state.captionsUrl}
            label={playLabel}
          />
          <div className={styles.regenerateRow}>
            {state.stale && <OutdatedBadge />}
            <RegenerateMenu available={readyRegenModes(state.captionsUrl)} onSelect={regenerate} />
          </div>
        </>
      )}
      {state.phase === "failed" && (
        <>
          <div className={styles.stage}>
            <p className={styles.failedLabel} role="status">
              This video couldn’t be generated. The rest of the course is unaffected.
            </p>
          </div>
          {artifact?.jobId && (
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
