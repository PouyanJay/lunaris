import { useCallback, useEffect, useRef, useState } from "react";

import styles from "./GeneratedVideoPlayer.module.css";

interface GeneratedVideoPlayerProps {
  videoUrl: string;
  posterUrl: string | null;
  captionsUrl: string | null;
  /** The play button's accessible name, e.g. "Play course overview" / "Play lesson video". */
  label: string;
  /** Called when the <video> fails to load — typically because the signed URL expired (~1h TTL).
   *  Should re-fetch the job and update `videoUrl` so the player remounts on a live URL. Omit where
   *  there is nothing to re-mint (the standalone unit tests). */
  refreshPlayback?: () => void | Promise<void>;
  /** A title drawn over the poster (the design's title-over-poster treatment) — decorative, gone
   *  once the native player owns the stage. The play `label` stays the accessible name. */
  overlayTitle?: string | undefined;
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
  refreshPlayback,
  overlayTitle,
}: GeneratedVideoPlayerProps) {
  const [playing, setPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  // The signed URLs we've already tried to re-mint after a load error. A Set, not a flag: one play
  // session can outlive several expiries (URL A re-mints to B, B later expires to C), and each URL
  // earns exactly one re-mint — so a genuinely dead URL fails once instead of looping the re-fetch.
  const refreshedUrlsRef = useRef<Set<string>>(new Set());

  // Playing — or a re-mint that remounts the keyed element — replaces the focused control: move
  // focus onto the player so keyboard users land on the controls, not <body> (WCAG 2.4.3).
  useEffect(() => {
    if (playing) videoRef.current?.focus();
  }, [playing, videoUrl]);

  // The signed URL expired while the reader sat on the page: re-mint it once. The fresh URL flows
  // back as a new `videoUrl` prop, remounting the keyed <video> (below) so it autoplays on the
  // live URL — no page refresh. Guarded per-URL so a truly dead URL doesn't loop the re-fetch.
  const handleError = useCallback(() => {
    if (!refreshPlayback || refreshedUrlsRef.current.has(videoUrl)) return;
    refreshedUrlsRef.current.add(videoUrl);
    void refreshPlayback();
  }, [refreshPlayback, videoUrl]);

  return (
    <div className={styles.stage}>
      {playing ? (
        /* The artifact is our own MP4 on a signed URL — a native element, no third party. A narrated
           video also ships a WebVTT track (V3); the signed URL is cross-origin, so the <video> opts
           into CORS (`crossOrigin`) for the <track> to load. A silent video has no captionsUrl.
           Keyed by the URL so a re-minted (post-expiry) URL remounts the element and autoplays. */
        <video
          key={videoUrl}
          ref={videoRef}
          className={styles.player}
          src={videoUrl}
          poster={posterUrl ?? undefined}
          controls
          autoPlay
          crossOrigin={captionsUrl ? "anonymous" : undefined}
          onError={handleError}
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
          {overlayTitle && (
            <span className={styles.overlayTitle} aria-hidden="true">
              {overlayTitle}
              <span className={styles.overlayRule} />
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
