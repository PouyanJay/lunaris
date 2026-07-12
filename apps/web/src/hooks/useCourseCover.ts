import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchCoverJob,
  isCoverTerminal,
  pollCoverJob,
  regenerateCover,
  resolveCoverJobId,
  type CoverJobStatus,
  type CoverJobView,
} from "../lib/coverJobs";
import type { CoverArtifact } from "../types/course";
import type { Theme } from "./useTheme";

export const COURSE_COVER_POLL_INTERVAL_MS = 3000;

/** The cover image URL to show for the app `theme` — the INVERTED / contrast mapping: the app's
 *  LIGHT theme shows the DARK cover (it pops against the light chrome) and the DARK theme shows the
 *  LIGHT cover. Falls back to the dark image when there is no light twin (a dark-only or
 *  pre-dual-theme cover), and returns null when the state is not a resolved image. */
export function coverImageUrlForTheme(state: CourseCoverState, theme: Theme): string | null {
  return coverVariantForTheme(state, theme)?.master ?? null;
}

/** The cover VARIANT the app `theme` shows — the one decision both URL selectors read off, so they
 *  can never disagree about which artwork is on screen (the card and the lightbox must show one
 *  cover). Encodes the inverted/contrast mapping in ONE place: the app's LIGHT theme shows the DARK
 *  cover, its DARK theme the LIGHT one, falling back to the dark cover when there is no light twin.
 *
 *  Each variant is a `master` (the full 2048x1152 render) and its `thumb` (the same artwork resized
 *  by storage to display size, or null when the cover has none). Null when the state is not a
 *  resolved image. */
export function coverVariantForTheme(
  state: CourseCoverState,
  theme: Theme,
): { master: string; thumb: string | null } | null {
  if (state.phase !== "image") return null;
  if (theme === "dark" && state.imageUrlLight !== null) {
    return { master: state.imageUrlLight, thumb: state.thumbUrlLight };
  }
  return { master: state.imageUrl, thumb: state.thumbUrl };
}

/** The cover THUMB URL to show for the app `theme` — the storage-resized derivative of whichever
 *  variant `coverImageUrlForTheme` would pick, so the two selectors can never disagree about which
 *  artwork is on screen.
 *
 *  This is what the card and Overview frames load. A cover master is 2048x1152; handing it to a
 *  260px card and letting the browser shrink it is what makes a card cover look soft (a browser
 *  downscales with a cheap filter, and a composed cover's typography and hairlines alias into mush).
 *  Falls back to the master when there is no derivative — an older cover, or storage without image
 *  transformations — so a cover always renders. Null when the state is not a resolved image. */
export function coverThumbUrlForTheme(state: CourseCoverState, theme: Theme): string | null {
  const variant = coverVariantForTheme(state, theme);
  if (variant === null) return null;
  // The variant is chosen FIRST (above), and only then its derivative preferred over its master.
  // Choosing among thumbs first would let a light cover with no light thumb fall back to the DARK
  // thumb — the card and the lightbox would then be showing two different covers.
  return variant.thumb ?? variant.master;
}

/** What a surface knows about a course's AI cover, resolved from its payload artifact.
 *
 *  - `fallback` — no on-brand image to show (keyless account, a failed/cancelled cover, or none):
 *    the surface renders the **Typographic** cover. This is the resting state, NOT the constellation.
 *  - `generating` — a cover is in flight (the payload carries a non-terminal artifact, or the reader
 *    just triggered a regenerate): the surface shows the constellation as the LOADING state and this
 *    hook polls until it settles.
 *  - `image` — a READY cover whose short-lived signed URL resolved: the surface renders the image.
 *    `imageUrl` is the DARK cover; `imageUrlLight` is its LIGHT-theme twin (dual-theme covers) or
 *    null for a dark-only cover — the surface picks by the app theme (light theme → dark image, dark
 *    theme → light image), falling back to the dark image when there is no light one. Each variant
 *    also carries a `thumb…` — the same artwork resized by storage to display size. Card/Overview
 *    frames load the thumb (`coverThumbUrlForTheme`); the full-size lightbox loads the master
 *    (`coverImageUrlForTheme`). A thumb is null when the cover predates them or storage cannot
 *    resize, and the selectors fall back to the master. */
export type CourseCoverState =
  | { phase: "fallback" }
  | { phase: "generating"; status: CoverJobStatus }
  | {
      phase: "image";
      imageUrl: string;
      imageUrlLight: string | null;
      thumbUrl: string | null;
      thumbUrlLight: string | null;
    };

/** Resolve a course's cover to a renderable state, and let the reader regenerate it
 *  (course-cover-images T9 + T10).
 *
 *  A READY artifact carries a ``jobId`` handle (never a raw URL — URLs expire), exchanged for a
 *  short-lived signed URL via ``GET /api/covers/{jobId}``; a non-terminal artifact is polled to its
 *  verdict so a cover that finishes while the reader watches swaps in without a refresh. Everything
 *  else — no artifact, a FAILED/CANCELLED one, an account with no OpenAI key (which never enqueues a
 *  cover, so its artifact is absent) — resolves to ``fallback`` (the Typographic cover).
 *  ``regenerate()`` re-runs the artifact's job (READY *or* FAILED — both carry ``jobId``) and polls
 *  the new job to a verdict, so a reader can ask for a fresh cover on demand (T10). */
export function useCourseCover(
  apiBaseUrl: string | undefined,
  artifact: CoverArtifact | null | undefined,
  pollIntervalMs: number = COURSE_COVER_POLL_INTERVAL_MS,
): { state: CourseCoverState; regenerate: () => void; regenerating: boolean } {
  const status = artifact?.status ?? null;
  const jobId = resolveCoverJobId(artifact);
  const [state, setState] = useState<CourseCoverState>({ phase: "fallback" });
  const [regenerating, setRegenerating] = useState(false);
  // The controller for an in-flight regenerate poll — aborted on a new regenerate or on unmount, so
  // a stale poll never writes state after the component is gone (or a second regenerate started).
  const regenController = useRef<AbortController | null>(null);

  const applyView = useCallback((view: CoverJobView | null) => {
    setState(
      view?.job.status === "ready" && view.imageUrl
        ? {
            phase: "image",
            imageUrl: view.imageUrl,
            imageUrlLight: view.imageUrlLight ?? null,
            thumbUrl: view.thumbUrl ?? null,
            thumbUrlLight: view.thumbUrlLight ?? null,
          }
        : { phase: "fallback" },
    );
  }, []);

  useEffect(() => {
    // No key / no cover / a settled non-READY cover → the Typographic fallback, no fetch.
    if (!apiBaseUrl || !jobId || status === null || status === "failed" || status === "cancelled") {
      setState({ phase: "fallback" });
      return;
    }
    const controller = new AbortController();

    if (status === "ready") {
      setState({ phase: "generating", status });
      void fetchCoverJob(apiBaseUrl, jobId, controller.signal).then((view) => {
        if (controller.signal.aborted) return;
        applyView(view); // READY → image (both URLs), else fallback — one mapping, shared
      });
      return () => controller.abort();
    }

    // A non-terminal (in-flight) cover: show the constellation loading state and poll to a verdict.
    setState({ phase: "generating", status });
    void pollCoverJob(apiBaseUrl, jobId, {
      signal: controller.signal,
      intervalMs: pollIntervalMs,
      onWorking: (working) => {
        if (!controller.signal.aborted) setState({ phase: "generating", status: working });
      },
      onSettled: (view) => {
        if (!controller.signal.aborted) applyView(view);
      },
    });
    return () => controller.abort();
  }, [apiBaseUrl, jobId, status, pollIntervalMs, applyView]);

  useEffect(() => () => regenController.current?.abort(), []);

  const regenerate = useCallback(() => {
    if (!apiBaseUrl || !jobId || regenerating) return;
    regenController.current?.abort();
    const controller = new AbortController();
    regenController.current = controller;
    setRegenerating(true);
    setState({ phase: "generating", status: "queued" });
    void regenerateCover(apiBaseUrl, jobId).then((view) => {
      if (controller.signal.aborted) return;
      const newJobId = view?.job.id;
      if (!newJobId) {
        setRegenerating(false);
        setState({ phase: "fallback" });
        return;
      }
      void pollCoverJob(apiBaseUrl, newJobId, {
        signal: controller.signal,
        intervalMs: pollIntervalMs,
        onWorking: (working) => {
          if (!controller.signal.aborted) setState({ phase: "generating", status: working });
        },
        onSettled: (settled) => {
          if (controller.signal.aborted) return;
          applyView(settled);
          setRegenerating(false);
        },
      });
    });
  }, [apiBaseUrl, jobId, regenerating, pollIntervalMs, applyView]);

  // A settled-but-not-ready status is defensively coerced to the fallback (the effect already does
  // this; the guard keeps the returned state honest if the artifact changes between renders).
  const coerced =
    status !== null && isCoverTerminal(status) && status !== "ready" && !regenerating
      ? { phase: "fallback" as const }
      : state;
  return { state: coerced, regenerate, regenerating };
}
