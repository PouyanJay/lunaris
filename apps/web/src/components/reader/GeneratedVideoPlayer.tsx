import { useEffect, useRef, useState } from "react";

import styles from "./GeneratedVideoPlayer.module.css";

interface GeneratedVideoPlayerProps {
  videoUrl: string;
  posterUrl: string | null;
  captionsUrl: string | null;
  /** The play button's accessible name, e.g. "Play course overview" / "Play lesson video". */
  label: string;
}

/** The shared facade for a Lunaris-generated MP4: a 16:9 stage showing the poster until clicked,
 *  then the native player on the signed URL. One component for every generated video — the lesson
 *  hero and the course-level Overview section both render through it, so the play affordance, the
 *  caption track, and keyboard handling stay identical everywhere (the YouTube ``VideoFacade`` is a
 *  separate thing — that one embeds a third-party iframe; this one plays our own artifact). */
export function GeneratedVideoPlayer({
  videoUrl,
  posterUrl,
  captionsUrl,
  label,
}: GeneratedVideoPlayerProps) {
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Playing unmounts the focused poster button — move focus onto the player so keyboard users land
  // on the controls instead of falling back to <body> (WCAG 2.4.3).
  useEffect(() => {
    if (playing) videoRef.current?.focus();
  }, [playing]);

  return (
    <div className={styles.stage}>
      {playing ? (
        /* The artifact is our own MP4 on a signed URL — a native element, no third party. A narrated
           video also ships a WebVTT track (V3); the signed URL is cross-origin, so the <video> opts
           into CORS (`crossOrigin`) for the <track> to load. A silent video has no captionsUrl. */
        <video
          ref={videoRef}
          className={styles.player}
          src={videoUrl}
          poster={posterUrl ?? undefined}
          controls
          autoPlay
          crossOrigin={captionsUrl ? "anonymous" : undefined}
        >
          {captionsUrl && (
            <track kind="captions" src={captionsUrl} srcLang="en" label="English" default />
          )}
        </video>
      ) : (
        <button
          type="button"
          className={styles.poster}
          aria-label={label}
          onClick={() => setPlaying(true)}
        >
          {posterUrl ? (
            <img className={styles.posterImage} src={posterUrl} alt="" loading="lazy" />
          ) : (
            <span className={`mono ${styles.posterGlyph}`} aria-hidden="true">
              VIDEO
            </span>
          )}
          <span className={styles.play} aria-hidden="true">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
      )}
    </div>
  );
}
