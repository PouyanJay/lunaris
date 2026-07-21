import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import type { ScoredResource } from "../../lib/chapterResources";
import { formatMediaDuration } from "../../lib/mediaDuration";
import { highlightTerms } from "../../lib/transcriptHighlight";
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
  chapterResources?: Map<string, ScoredResource[]> | undefined;
}

function PlayGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor" aria-hidden="true">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function PauseGlyph() {
  return (
    <svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor" aria-hidden="true">
      <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
    </svg>
  );
}

/** Arrow-key seek granularity. */
const SEEK_STEP_S = 5;

/** The current spoken line overlaid on the video, with the chapter's key terms accented. Marked
 *  aria-hidden — the captions `<track>` serves assistive tech, and a live-updating caption would
 *  otherwise spam a screen reader on every cue. */
function CaptionOverlay({ cue, keyTerms }: { cue: TranscriptCue; keyTerms: string[] }) {
  return (
    <p className={styles.caption} aria-hidden="true">
      {highlightTerms(cue.text, keyTerms).map((segment, index) =>
        segment.highlight ? (
          <mark key={index} className={styles.captionTerm}>
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </p>
  );
}

interface TransportProps {
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  playedPercent: number;
  chapters: VideoChapter[];
  activeChapter: number;
  currentChapter: VideoChapter | undefined;
  onToggle: () => void;
  onSeekPointer: (event: PointerEvent<HTMLDivElement>) => void;
  onSeekKey: (event: KeyboardEvent<HTMLDivElement>) => void;
}

/** The transport row: play/pause, a chapter-tick scrubber (click + keyboard seek, `role="slider"`),
 *  and a time + current-chapter readout. */
function TransportControls({
  isPlaying,
  currentTime,
  duration,
  playedPercent,
  chapters,
  activeChapter,
  currentChapter,
  onToggle,
  onSeekPointer,
  onSeekKey,
}: TransportProps) {
  return (
    <div className={styles.controls}>
      <button
        type="button"
        className={styles.playButton}
        onClick={onToggle}
        aria-label={isPlaying ? "Pause" : "Play"}
      >
        {isPlaying ? <PauseGlyph /> : <PlayGlyph />}
      </button>

      <div
        className={styles.scrubber}
        role="slider"
        tabIndex={0}
        aria-label="Seek"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(currentTime)}
        aria-valuetext={`${formatMediaDuration(currentTime)} of ${formatMediaDuration(duration)}`}
        onPointerDown={onSeekPointer}
        onKeyDown={onSeekKey}
      >
        <span className={styles.scrubberFill} style={{ width: `${playedPercent}%` }} />
        {duration > 0 &&
          chapters.map((chapter, index) =>
            index === 0 ? null : (
              <span
                key={chapter.id}
                className={styles.tick}
                style={{ left: `${(chapter.startS / duration) * 100}%` }}
                aria-hidden="true"
              />
            ),
          )}
      </div>

      <span className={`mono ${styles.readout}`}>
        {formatMediaDuration(currentTime)} / {formatMediaDuration(duration)}
        {currentChapter ? ` · CH ${activeChapter + 1} — ${currentChapter.title.toUpperCase()}` : ""}
      </span>
    </div>
  );
}

interface ChapterRailProps {
  chapters: VideoChapter[];
  activeChapter: number;
  maxWatched: number;
  chapterResources: Map<string, ScoredResource[]> | undefined;
  onSeek: (seconds: number) => void;
}

/** The chapter rail: each chapter (watched ones struck through) with its docked resources. */
function ChapterRail({
  chapters,
  activeChapter,
  maxWatched,
  chapterResources,
  onSeek,
}: ChapterRailProps) {
  return (
    <div className={styles.rail}>
      <p className={styles.railHead}>Chapters</p>
      <nav aria-label="Video chapters">
        {chapters.map((chapter, index) => {
          const resources = chapterResources?.get(chapter.id) ?? [];
          // Passed its end and not the one playing now — the current chapter stays highlighted.
          const watched = index !== activeChapter && maxWatched >= chapter.endS;
          const className = [
            styles.chapter,
            index === activeChapter && styles.chapterActive,
            watched && styles.chapterDone,
          ]
            .filter(Boolean)
            .join(" ");
          return (
            <div key={chapter.id} className={styles.chapterGroup}>
              <button
                type="button"
                className={className}
                aria-current={index === activeChapter ? "true" : undefined}
                onClick={() => onSeek(chapter.startS)}
              >
                <span className={styles.chapterTime}>{formatMediaDuration(chapter.startS)}</span>
                <span>{chapter.title}</span>
                {watched && <span className="sr-only"> (watched)</span>}
              </button>
              {resources.map((scored) => (
                <ChapterResourceCard key={scored.resource.url} scored={scored} />
              ))}
            </div>
          );
        })}
      </nav>
    </div>
  );
}

/** The Cinema player (cinematic upgrade): the generated lesson video with a purpose-built,
 *  keyboard-operable transport — a play/pause overlay, a chapter-tick scrubber that seeks on click
 *  and arrow keys, and a time + current-chapter readout — plus an overlaid synced caption and a
 *  chapter rail with per-chapter resources. Chapters and the current cue track playback via
 *  `timeupdate`; watched chapters (this session) read as struck through. The captions `<track>` is
 *  kept for assistive tech even though native controls are replaced. A silent video (no transcript)
 *  shows no caption. */
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
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  // The furthest point reached this session — chapters whose end has been passed read as watched.
  // Reset when the video changes so one lesson's progress never bleeds into the next.
  const [maxWatched, setMaxWatched] = useState(0);
  useEffect(() => {
    setCurrentTime(0);
    setDuration(0);
    setIsPlaying(false);
    setMaxWatched(0);
  }, [videoUrl]);

  const activeChapter = activeSpanIndex(chapters, currentTime);
  const activeCue = activeSpanIndex(transcript, currentTime);
  const playedPercent = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;
  const currentChapter = activeChapter >= 0 ? chapters[activeChapter] : undefined;
  const currentCue = activeCue >= 0 ? transcript[activeCue] : undefined;

  const seekTo = (seconds: number) => {
    // Optimistically move the UI (the video's own `timeupdate` reconciles); clamp to the media when
    // its duration is known (before metadata loads we only floor at 0).
    const bounded = duration > 0 ? Math.min(duration, Math.max(0, seconds)) : Math.max(0, seconds);
    const video = videoRef.current;
    if (video) video.currentTime = bounded;
    setCurrentTime(bounded);
  };

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) void video.play?.().catch(() => {});
    else video.pause?.();
  };

  const onSeekPointer = (event: PointerEvent<HTMLDivElement>) => {
    if (duration <= 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0) return;
    const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    seekTo(fraction * duration);
  };

  const onSeekKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (duration <= 0) return;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = currentTime + SEEK_STEP_S;
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown")
      next = currentTime - SEEK_STEP_S;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = duration;
    if (next === null) return;
    event.preventDefault();
    seekTo(next);
  };

  return (
    <div className={styles.cinema}>
      <div className={styles.main}>
        <div className={styles.stage}>
          {/* Native controls are replaced by the custom transport below; the caption <track> stays
              for assistive tech (a silent video has none to add). */}
          <video
            ref={videoRef}
            className={styles.video}
            src={videoUrl}
            poster={posterUrl ?? undefined}
            preload="metadata"
            aria-label={label}
            onClick={togglePlay}
            onTimeUpdate={(event) => {
              const time = event.currentTarget.currentTime;
              setCurrentTime(time);
              setMaxWatched((prev) => Math.max(prev, time));
            }}
            onLoadedMetadata={(event) =>
              setDuration(
                Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0,
              )
            }
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
            onEnded={() => setIsPlaying(false)}
          >
            {captionsUrl && <track kind="captions" src={captionsUrl} default />}
          </video>
          {!isPlaying && (
            <button
              type="button"
              className={styles.playOverlay}
              onClick={togglePlay}
              aria-label="Play video"
            >
              <span className={styles.playOverlayIcon}>
                <PlayGlyph />
              </span>
            </button>
          )}
          {currentCue && (
            <CaptionOverlay cue={currentCue} keyTerms={currentChapter?.keyTerms ?? []} />
          )}
        </div>

        <TransportControls
          isPlaying={isPlaying}
          currentTime={currentTime}
          duration={duration}
          playedPercent={playedPercent}
          chapters={chapters}
          activeChapter={activeChapter}
          currentChapter={currentChapter}
          onToggle={togglePlay}
          onSeekPointer={onSeekPointer}
          onSeekKey={onSeekKey}
        />
      </div>

      <ChapterRail
        chapters={chapters}
        activeChapter={activeChapter}
        maxWatched={maxWatched}
        chapterResources={chapterResources}
        onSeek={seekTo}
      />
    </div>
  );
}
