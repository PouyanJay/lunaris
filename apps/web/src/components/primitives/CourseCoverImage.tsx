import { useEffect, useMemo, useState } from "react";

import { CourseCover } from "./CourseCover";
import { TypographicCover } from "./TypographicCover";
import styles from "./CourseCoverImage.module.css";
import {
  coverVariantForTheme,
  useCourseCover,
  type CourseCoverState,
} from "../../hooks/useCourseCover";
import { useThemeValue } from "../../hooks/useThemeValue";
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
  // The cover contrasts with the app chrome (dual-theme): light theme shows the DARK image, dark
  // theme shows the LIGHT one (falling back to dark when there is no light twin). Read-only theme
  // observer so this many-call-site component reacts to a toggle without owning the theme.
  const theme = useThemeValue();
  // The load ladder for the theme's variant, sharpest-and-lightest first:
  //   1. the storage-RESIZED derivative — what a card or the Overview should show. A cover master is
  //      2048x1152; letting the browser shrink that into a ~260px card frame is what made card
  //      covers look soft (a browser downscales with a cheap filter, so a composed cover's
  //      typography and hairline callouts alias into mush). Storage resamples properly, once.
  //   2. the MASTER — for a cover minted before derivatives existed, or storage that cannot resize.
  //   3. the Typographic cover — the signed URL 404'd (expired / purged); never a broken image.
  // Each rung is tried on the previous one's error. The rungs are DEDUPED: a cover with no
  // derivative has thumb === master, and a repeated URL would re-render the identical `key`/`src`,
  // so React would never remount the <img>, the browser would never retry, no second error would
  // fire — and the frame would sit on a broken image forever instead of reaching the fallback.
  const variant = coverVariantForTheme(state, theme);
  const master = variant?.master ?? null;
  const thumb = variant?.thumb ?? null;
  const rungs = useMemo(
    () => [...new Set([thumb, master].filter((url): url is string => url !== null))],
    [thumb, master],
  );
  const [rung, setRung] = useState(0);
  // Re-enter at the top when the displayed cover changes (a theme toggle picks the other variant, a
  // regenerate lands a new one), so a transient failure never strands the surface on a lower rung.
  useEffect(() => setRung(0), [thumb, master]);
  const src = rungs[rung];

  if (src) {
    return (
      <img
        // Keyed on the src so a fall to the next rung remounts rather than reusing the errored node.
        key={src}
        className={styles.image}
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        onError={() => setRung((current) => current + 1)}
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
