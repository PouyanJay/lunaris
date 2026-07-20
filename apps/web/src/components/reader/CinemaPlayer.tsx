import { useRef, useState } from "react";

import type { ScoredResource } from "../../lib/chapterResources";
import type { TranscriptCue, VideoChapter } from "../../lib/videoJobs";
import { activeSpanIndex } from "../../lib/videoOutline";
import { ChapterResourceCard } from "./ChapterResourceCard";
import styles from "./CinemaPlayer.module.css";

interface CinemaPlayerProps {
  videoUrl: string;
  posterUrl: string | null;
  captionsUrl: string | null;
  chapters: VideoChapter[];
  transcript: TranscriptCue[];
  /** Accessible label for the video (the lesson/module title). */
  label: string;
  /** Curated resources docked under each chapter (by chapter id), most-relevant first. Absent hides
   *  the per-chapter aids (e.g. Watch mode with docks off). */
  chapterResources?: Map<string, ScoredResource[]>;
}

/** `M:SS` for a chapter's start — the video-timeline clock. */
function clock(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/** The Cinema player (Focus Flow phase 5): the generated lesson video as the front door, with a
 *  chapter rail and a synced, click-to-seek transcript. Chapters and the current cue track playback
 *  via `timeupdate`; clicking a chapter or cue seeks the video. A video with no transcript (silent)
 *  shows the chapter rail alone. */
export function CinemaPlayer({
  videoUrl,
  posterUrl,
  captionsUrl,
  chapters,
  transcript,
  label,
  chapterResources,
}: CinemaPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const activeChapter = activeSpanIndex(chapters, currentTime);
  const activeCue = activeSpanIndex(transcript, currentTime);

  const seekTo = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    void video.play?.().catch(() => {
      /* Autoplay can reject (no gesture / policy) — seeking still lands; ignore. */
    });
  };

  return (
    <div className={styles.cinema}>
      <div className={styles.main}>
        {/* The caption <track> is added only when the video is narrated (captionsUrl); a silent
            video has none to add. */}
        <video
          ref={videoRef}
          className={styles.video}
          src={videoUrl}
          poster={posterUrl ?? undefined}
          controls
          preload="metadata"
          aria-label={label}
          onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        >
          {captionsUrl && <track kind="captions" src={captionsUrl} default />}
        </video>
      </div>

      <div className={styles.rail}>
        <p className={styles.railHead}>Chapters</p>
        <nav aria-label="Video chapters">
          {chapters.map((chapter, index) => {
            const resources = chapterResources?.get(chapter.id) ?? [];
            return (
              <div key={chapter.id} className={styles.chapterGroup}>
                <button
                  type="button"
                  className={`${styles.chapter} ${index === activeChapter ? styles.chapterActive : ""}`.trim()}
                  aria-current={index === activeChapter ? "true" : undefined}
                  onClick={() => seekTo(chapter.startS)}
                >
                  <span className={styles.chapterTime}>{clock(chapter.startS)}</span>
                  <span>{chapter.title}</span>
                </button>
                {resources.map((scored) => (
                  <ChapterResourceCard key={scored.resource.url} scored={scored} />
                ))}
              </div>
            );
          })}
        </nav>

        {transcript.length > 0 && (
          <div className={styles.transcript}>
            <p className={styles.railHead}>Transcript</p>
            {transcript.map((cue, index) => (
              <button
                key={`${cue.startS}-${index}`}
                type="button"
                className={`${styles.cue} ${index === activeCue ? styles.cueActive : ""}`.trim()}
                aria-current={index === activeCue ? "true" : undefined}
                onClick={() => seekTo(cue.startS)}
              >
                {cue.text}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
