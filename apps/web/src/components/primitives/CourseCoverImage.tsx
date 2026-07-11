import { useEffect, useState } from "react";

import { CourseCover } from "./CourseCover";
import { TypographicCover } from "./TypographicCover";
import styles from "./CourseCoverImage.module.css";
import { useCourseCover, type CourseCoverState } from "../../hooks/useCourseCover";
import { coverSeed } from "../../lib/coverSeed";
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
   *  button + the image share one source of truth), this component is purely presentational and does
   *  NOT run its own hook; card sites omit it and let the component resolve the state itself. */
  state?: CourseCoverState;
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
  // A signed URL can 404 by the time the browser loads it (it expired, or the object was purged);
  // fall back to the Typographic cover rather than showing a broken image.
  const [broken, setBroken] = useState(false);
  const imageUrl = state.phase === "image" ? state.imageUrl : null;
  useEffect(() => setBroken(false), [imageUrl]);

  if (state.phase === "image" && !broken) {
    return (
      <img
        className={styles.image}
        src={state.imageUrl}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => setBroken(true)}
      />
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
