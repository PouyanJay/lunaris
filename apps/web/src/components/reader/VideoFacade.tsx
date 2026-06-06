import { useState } from "react";

import { VideoLightbox } from "./VideoLightbox";
import { youTubeEmbed, youTubeThumbnail } from "./youtube";
import styles from "./VideoFacade.module.css";

interface VideoFacadeProps {
  videoId: string;
  /** The resource title — used for the play label, iframe title, and lightbox heading. */
  title: string;
}

/** A YouTube video that plays inside the reader instead of leaving for youtube.com. It starts as a
 *  lightweight poster (just the thumbnail image + a play affordance — NO third-party iframe), then on
 *  click expands the privacy-enhanced `nocookie` player in place. A second control opens the same
 *  video in a focus-trapped fullscreen lightbox. The iframe is created only on a user gesture, so the
 *  facade stays cheap and tracker-free until played. The card's title link → youtube.com is
 *  unchanged, so opening on YouTube remains one click away. */
export function VideoFacade({ videoId, title }: VideoFacadeProps) {
  const [inline, setInline] = useState(false);
  const [lightbox, setLightbox] = useState(false);
  const [imageOk, setImageOk] = useState(true);

  return (
    <span className={styles.facade}>
      {inline ? (
        <iframe
          className={styles.frame}
          src={youTubeEmbed(videoId, { autoplay: true })}
          title={title}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      ) : (
        <button
          type="button"
          className={styles.poster}
          aria-label={`Play video: ${title}`}
          onClick={() => setInline(true)}
        >
          {imageOk ? (
            <img
              className={styles.image}
              src={youTubeThumbnail(videoId)}
              alt=""
              loading="lazy"
              width={320}
              height={180}
              onError={() => setImageOk(false)}
            />
          ) : (
            <span className={`mono ${styles.glyph}`} aria-hidden="true">
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

      <button
        type="button"
        className={styles.expand}
        aria-label={`Play video in full screen: ${title}`}
        onClick={() => setLightbox(true)}
      >
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
        </svg>
      </button>

      {lightbox && (
        <VideoLightbox videoId={videoId} title={title} onClose={() => setLightbox(false)} />
      )}
    </span>
  );
}
