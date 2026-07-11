import { useEffect, useState } from "react";

import { CourseCover } from "./CourseCover";
import { TypographicCover } from "./TypographicCover";
import styles from "./CourseCoverImage.module.css";
import { useCourseCover } from "../../hooks/useCourseCover";
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
   *  passes its own. */
  apiBaseUrl?: string | undefined;
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
}: CourseCoverImageProps) {
  const { state } = useCourseCover(apiBaseUrl, cover);
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
