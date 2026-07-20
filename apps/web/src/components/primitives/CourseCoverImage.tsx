import { useEffect, useMemo, useRef, useState } from "react";

import { CourseCover } from "./CourseCover";
import { TypographicCover } from "./TypographicCover";
import styles from "./CourseCoverImage.module.css";
import {
  coverVariantForTheme,
  useCourseCover,
  type CourseCoverState,
} from "../../hooks/useCourseCover";
import type { Theme } from "../../hooks/useTheme";
import { useThemeValue } from "../../hooks/useThemeValue";
import { coverSeed } from "../../lib/coverSeed";
import { hasSeenImage, markImageSeen, storageImageCacheKey } from "../../lib/imageCache";
import type { CoverArtifact } from "../../types/course";

interface CourseCoverImageProps {
  /** Course id — seeds the constellation accents (stable per course). */
  courseId: string;
  /** Course topic — the word set on the Typographic fallback. */
  topic: string;
  /** The course's cover artifact (payload handle), if any. Absent → the Typographic fallback. */
  cover?: CoverArtifact | null | undefined;
  /** API base URL for exchanging a READY cover's jobId for a short-lived signed image URL. Defaults
   *  to the build-time ``VITE_API_URL`` so the many card call sites need not thread it; the Overview
   *  passes its own. Ignored when ``state`` is supplied. */
  apiBaseUrl?: string | undefined;
  /** A pre-resolved cover state. When supplied (the Overview, which owns the hook so its regenerate
   *  button + the image share one source of truth; or a card with a pre-signed summary thumb), this
   *  component is purely presentational and does NOT run its own hook. Omitted / undefined → the
   *  component resolves the state itself from the `cover` handle. */
  state?: CourseCoverState | undefined;
  /** Above-the-fold priority — the first row of the grid loads its cover eagerly with a high fetch
   *  priority so it paints without waiting for lazy intersection; below-the-fold covers stay lazy. */
  priority?: boolean;
}

/** A course's cover, resolved to the right treatment (course-cover-images T9): the AI **image**
 *  (its signed URL, with the constellation as the load skeleton), the **constellation** as the
 *  LOADING state while a cover is still generating, or the **Typographic** cover as the resting
 *  fallback (keyless / failed / none). One component so every surface — card, Home, Overview —
 *  applies the same precedence. Decorative: callers wrap it in an `aria-hidden` frame and the
 *  adjacent title carries the name. */
export function CourseCoverImage({
  courseId,
  topic,
  cover,
  apiBaseUrl = import.meta.env.VITE_API_URL as string | undefined,
  state: providedState,
  priority = false,
}: CourseCoverImageProps) {
  // Own the hook only when no state is provided (card sites). The Overview passes its own hook's
  // state so the regenerate button and this image never diverge; calling the hook with a null
  // artifact there keeps the hooks-count stable without doing any work.
  const owned = useCourseCover(
    providedState ? undefined : apiBaseUrl,
    providedState ? null : cover,
  );
  const state = providedState ?? owned.state;
  const seed = coverSeed(courseId);
  const theme = useThemeValue();
  const { src, onError } = useCoverImageSource(state, theme);
  const { imgRef, loaded, onLoad } = useImageLoaded(src);

  if (src) {
    return (
      <div className={styles.frame}>
        {/* The seeded constellation fills the frame instantly as the load placeholder, so the box is
            composed from the first frame and the AI cover crossfades in over it (no empty→image
            pop, no layout shift — the frame already owns the aspect ratio). */}
        <div className={styles.placeholder}>
          <CourseCover seed={seed} />
        </div>
        <img
          // Keyed on the src so a fall to the next rung remounts rather than reusing the errored node.
          key={src}
          ref={imgRef}
          className={styles.image}
          data-loaded={loaded || undefined}
          src={src}
          alt=""
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : "auto"}
          decoding="async"
          onLoad={onLoad}
          onError={onError}
        />
      </div>
    );
  }
  if (state.phase === "generating") {
    // The constellation is the LOADING state — it swaps to the image the moment the poll settles.
    return (
      <div className={styles.loading}>
        <CourseCover seed={seed} />
      </div>
    );
  }
  return <TypographicCover topic={topic} seed={seed} />;
}

/** Whether two rung lists show the same ARTWORK — equal token-stripped cache keys, in order. A
 *  revalidation that only re-signed the same objects (rotated tokens) compares equal. */
function sameArtwork(a: string[], b: string[]): boolean {
  return (
    a.length === b.length &&
    a.every((url, i) => storageImageCacheKey(url) === storageImageCacheKey(b[i] as string))
  );
}

/** The cover URL to display for the theme's variant, plus the error handler that walks the load
 *  ladder. The ladder tries, sharpest-and-lightest first:
 *    1. the storage-RESIZED derivative — what a card or the Overview should show. A cover master is
 *       2048x1152; letting the browser shrink that into a ~260px card frame is what made card covers
 *       look soft (a cheap downscale aliases a composed cover's typography and hairlines into mush).
 *    2. the MASTER — for a cover minted before derivatives existed, or storage that cannot resize.
 *    3. nothing (→ the Typographic cover) — the signed URL 404'd (expired / purged); never a broken
 *       image. Each rung is tried on the previous one's error. The rungs are DEDUPED: a cover with no
 *  derivative has thumb === master, and a repeated URL would re-render the identical key/src, so
 *  React would never remount the <img>, the browser would never retry, and the frame would sit on a
 *  broken image forever instead of reaching the fallback.
 *
 *  The src is STABLE across token rotation: every list revalidation re-signs the same objects with a
 *  fresh token, and adopting each new URL would remount the <img> (it is keyed on src) and replay
 *  the whole load ladder + crossfade on artwork that hasn't changed — the "covers reload on every
 *  visit" bug. So new URLs are adopted only when they show DIFFERENT artwork (a regenerate, a theme
 *  flip to the other variant); a rotated token keeps the held URLs. If a held URL errors (its token
 *  expired AND the service worker has no cached bytes), the error handler first retries the same
 *  artwork at its freshest URL, and only then walks down the ladder. */
function useCoverImageSource(
  state: CourseCoverState,
  theme: Theme,
): { src: string | undefined; onError: () => void } {
  const variant = coverVariantForTheme(state, theme);
  const master = variant?.master ?? null;
  const thumb = variant?.thumb ?? null;
  const incoming = useMemo(
    () => [...new Set([thumb, master].filter((url): url is string => url !== null))],
    [thumb, master],
  );
  const [adopted, setAdopted] = useState(incoming);
  const [rung, setRung] = useState(0);
  const incomingRef = useRef(incoming);
  incomingRef.current = incoming;
  useEffect(() => {
    setAdopted((held) => {
      if (sameArtwork(held, incoming)) return held; // a rotated token — keep the held src
      setRung(0); // genuinely new artwork — re-enter the ladder at the top
      return incoming;
    });
  }, [incoming]);
  const onError = () => {
    // A held URL whose token expired (and missed the cache): retry the SAME artwork at its freshest
    // signing before giving the rung up entirely.
    setAdopted((held) => {
      const current = held[rung];
      const fresh = incomingRef.current.find(
        (url) => current !== undefined && storageImageCacheKey(url) === storageImageCacheKey(current),
      );
      if (fresh !== undefined && fresh !== current) {
        return held.map((url, i) => (i === rung ? fresh : url));
      }
      setRung((r) => r + 1);
      return held;
    });
  };
  return { src: adopted[rung], onError };
}

/** Crossfade bookkeeping for one image src: the image starts transparent and `loaded` flips true
 *  once it has decoded, so a card is never empty and covers don't pop in one by one. Artwork the
 *  session has ALREADY painted (see markImageSeen) mounts pre-loaded — the crossfade softens a
 *  first, genuinely-loading render, not a service-worker-served repeat. A cached image can also be
 *  `complete` before `onLoad` attaches, so that is reflected on mount — otherwise the image would
 *  strand invisible behind a fade that will never fire. */
function useImageLoaded(src: string | undefined): {
  imgRef: React.RefObject<HTMLImageElement | null>;
  loaded: boolean;
  onLoad: () => void;
} {
  const imgRef = useRef<HTMLImageElement>(null);
  const [loaded, setLoaded] = useState(() => (src !== undefined ? hasSeenImage(src) : false));
  useEffect(() => {
    setLoaded(src !== undefined && hasSeenImage(src));
    if (imgRef.current?.complete && imgRef.current.naturalWidth > 0) setLoaded(true);
  }, [src]);
  const onLoad = () => {
    if (src !== undefined) markImageSeen(src);
    setLoaded(true);
  };
  return { imgRef, loaded, onLoad };
}
