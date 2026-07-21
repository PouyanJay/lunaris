import { useState } from "react";

import type { ResourceKind } from "../../types/course";
import { KIND_GLYPH } from "./resourceKind";
import { youTubeId, youTubeThumbnail } from "./youtube";
import styles from "./ResourceThumb.module.css";

interface ResourceThumbProps {
  kind: ResourceKind;
  url: string;
  /** The resource title, for the image alt text. */
  title: string;
}

/** The visual for a resource card (req 3): a real YouTube frame + play overlay so a video reads as a
 *  video, else a tokened kind-glyph tile. Handles the image lifecycle — a skeleton while loading and
 *  a graceful glyph fallback if the frame 404s — so a missing thumbnail never leaves a broken image.
 *  Decorative: the card's title link is the action, so the thumbnail adds no duplicate link, tab
 *  stop, or screen-reader target (the image still carries its title as alt for when it is the
 *  accessible context). */
export function ResourceThumb({ kind, url, title }: ResourceThumbProps) {
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);
  const videoId = kind === "video" ? youTubeId(url) : null;
  const showImage = videoId !== null && !errored;

  return (
    <span className={styles.thumb}>
      {showImage ? (
        <>
          {!loaded && <span className={styles.skeleton} aria-hidden="true" />}
          <img
            className={`${styles.image} ${loaded ? styles.imageLoaded : ""}`}
            src={youTubeThumbnail(videoId)}
            alt={title}
            loading="lazy"
            width={320}
            height={180}
            onLoad={() => setLoaded(true)}
            onError={() => setErrored(true)}
          />
        </>
      ) : (
        <span className={`mono ${styles.glyph}`}>{KIND_GLYPH[kind]}</span>
      )}
      {/* The play affordance sits over a real video frame; a non-YouTube video falls back to the
          "VIDEO" glyph (which already reads as a video) rather than a triangle over a blank tile. */}
      {showImage && (
        <span className={styles.play} aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        </span>
      )}
    </span>
  );
}
