import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CoverArtifact } from "../types/course";
import {
  coverImageUrlForTheme,
  coverThumbUrlForTheme,
  useCourseCover,
  type CourseCoverState,
} from "./useCourseCover";

vi.mock("../lib/coverJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/coverJobs")>();
  return {
    ...actual,
    fetchCoverJob: vi.fn(),
    pollCoverJob: vi.fn(),
    regenerateCover: vi.fn(),
  };
});
import { fetchCoverJob, pollCoverJob, regenerateCover, type CoverJobView } from "../lib/coverJobs";

const fetchJob = vi.mocked(fetchCoverJob);
const poll = vi.mocked(pollCoverJob);
const regen = vi.mocked(regenerateCover);

const API = "http://api.test";

const DARK = "https://signed/cover.png";
const LIGHT = "https://signed/cover-light.png";
const DARK_THUMB = "https://signed/cover.png?width=1280";
const LIGHT_THUMB = "https://signed/cover-light.png?width=1280";

/** A resolved-image state: each variant's master plus its storage-resized derivative. */
function imageState(imageUrl: string, imageUrlLight: string | null): CourseCoverState {
  return {
    phase: "image",
    imageUrl,
    imageUrlLight,
    thumbUrl: DARK_THUMB,
    thumbUrlLight: imageUrlLight === null ? null : LIGHT_THUMB,
  };
}

function readyView(jobId: string, imageUrlLight: string | null = null): CoverJobView {
  return {
    job: { id: jobId, courseId: "c1", status: "ready", stylePreset: "nocturne", error: null },
    imageUrl: `https://signed/${jobId}.png`,
    imageUrlLight,
    thumbUrl: `https://signed/${jobId}.png?width=1280`,
    thumbUrlLight: imageUrlLight === null ? null : LIGHT_THUMB,
    provenance: null,
  };
}

function artifact(status: CoverArtifact["status"], jobId: string | null = "job-1"): CoverArtifact {
  return { status, jobId, provenance: null };
}

beforeEach(() => {
  fetchJob.mockReset();
  poll.mockReset();
  regen.mockReset();
});

afterEach(() => vi.clearAllMocks());

describe("useCourseCover", () => {
  it("resolves a READY cover to its signed image URL", async () => {
    fetchJob.mockResolvedValue(readyView("job-1"));
    const { result } = renderHook(() => useCourseCover(API, artifact("ready")));
    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: "image",
        imageUrl: "https://signed/job-1.png",
        imageUrlLight: null,
        thumbUrl: "https://signed/job-1.png?width=1280",
        thumbUrlLight: null,
      }),
    );
  });

  it("carries the light twin's URL for a dual-theme READY cover", async () => {
    fetchJob.mockResolvedValue(readyView("job-1", "https://signed/job-1-light.png"));
    const { result } = renderHook(() => useCourseCover(API, artifact("ready")));
    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: "image",
        imageUrl: "https://signed/job-1.png",
        imageUrlLight: "https://signed/job-1-light.png",
        thumbUrl: "https://signed/job-1.png?width=1280",
        thumbUrlLight: LIGHT_THUMB,
      }),
    );
  });

  it("falls back when a READY cover's signed URL can't be minted (expired / purged)", async () => {
    fetchJob.mockResolvedValue(null);
    const { result } = renderHook(() => useCourseCover(API, artifact("ready")));
    await waitFor(() => expect(result.current.state).toEqual({ phase: "fallback" }));
  });

  it("shows the fallback for a FAILED cover, never a broken image", async () => {
    const { result } = renderHook(() => useCourseCover(API, artifact("failed")));
    await waitFor(() => expect(result.current.state).toEqual({ phase: "fallback" }));
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it("shows the fallback when there is no cover artifact (keyless / none)", async () => {
    const { result } = renderHook(() => useCourseCover(API, null));
    expect(result.current.state).toEqual({ phase: "fallback" });
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it("polls a generating cover and swaps to the image when it settles READY", async () => {
    poll.mockImplementation(async (_api, jobId, opts) => {
      opts.onWorking("rendering");
      opts.onSettled(readyView(jobId));
    });
    const { result } = renderHook(() => useCourseCover(API, artifact("art_directing")));
    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: "image",
        imageUrl: "https://signed/job-1.png",
        imageUrlLight: null,
        thumbUrl: "https://signed/job-1.png?width=1280",
        thumbUrlLight: null,
      }),
    );
  });

  it("does not fetch or poll without an API base URL", () => {
    const { result } = renderHook(() => useCourseCover(undefined, artifact("ready")));
    expect(result.current.state).toEqual({ phase: "fallback" });
    expect(fetchJob).not.toHaveBeenCalled();
    expect(poll).not.toHaveBeenCalled();
  });

  it("regenerate() re-runs the cover job and swaps in the new image when it settles", async () => {
    fetchJob.mockResolvedValue(readyView("job-1"));
    regen.mockResolvedValue({
      job: { id: "job-2", courseId: "c1", status: "queued", stylePreset: "nocturne", error: null },
      imageUrl: null,
      provenance: null,
    });
    poll.mockImplementation(async (_api, jobId, opts) =>
      opts.onSettled(readyView(jobId, `https://signed/${jobId}-light.png`)),
    );

    const { result } = renderHook(() => useCourseCover(API, artifact("ready")));
    await waitFor(() => expect(result.current.state.phase).toBe("image"));

    act(() => result.current.regenerate());

    // The regenerate enqueues job-2 and polls it → the image swaps to the new job's signed URLs
    // (dark + light both carried through the settle handler).
    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: "image",
        imageUrl: "https://signed/job-2.png",
        imageUrlLight: "https://signed/job-2-light.png",
        thumbUrl: "https://signed/job-2.png?width=1280",
        thumbUrlLight: LIGHT_THUMB,
      }),
    );
    expect(regen).toHaveBeenCalledWith(API, "job-1");
    expect(result.current.regenerating).toBe(false);
  });

  it("regenerate() is a no-op when there is no cover job to regenerate", () => {
    const { result } = renderHook(() => useCourseCover(API, null));
    act(() => result.current.regenerate());
    expect(regen).not.toHaveBeenCalled();
  });

  // T11 variant sweep: every cover status resolves to the right precedence phase.
  const IN_FLIGHT = ["queued", "art_directing", "rendering", "qa", "uploading"] as const;
  it.each(IN_FLIGHT)(
    "resolves an in-flight %s cover to the generating (loading) phase",
    async (s) => {
      poll.mockImplementation(async (_api, _jobId, opts) => opts.onWorking(s));
      const { result } = renderHook(() => useCourseCover(API, artifact(s)));
      await waitFor(() => expect(result.current.state).toEqual({ phase: "generating", status: s }));
    },
  );

  it.each(["failed", "cancelled"] as const)(
    "resolves a terminal %s cover to the fallback phase",
    async (s) => {
      const { result } = renderHook(() => useCourseCover(API, artifact(s)));
      await waitFor(() => expect(result.current.state).toEqual({ phase: "fallback" }));
      expect(fetchJob).not.toHaveBeenCalled();
    },
  );
});

describe("coverImageUrlForTheme (inverted mapping variant sweep)", () => {
  const dual = imageState(DARK, LIGHT);
  const darkOnly = imageState(DARK, null);

  // theme × variant → the image the reader should show (light theme → dark image; dark theme →
  // light image, falling back to the dark image when there is no light twin).
  it.each([
    ["light" as const, dual, DARK],
    ["dark" as const, dual, LIGHT],
    ["light" as const, darkOnly, DARK],
    ["dark" as const, darkOnly, DARK], // no light twin → the dark image in both themes
  ])("theme=%s picks the contrasting image", (theme, state, expected) => {
    expect(coverImageUrlForTheme(state, theme)).toBe(expected);
  });

  it.each(["light" as const, "dark" as const])(
    "returns null for a non-image state in theme=%s",
    (theme) => {
      expect(coverImageUrlForTheme({ phase: "fallback" }, theme)).toBeNull();
      expect(coverImageUrlForTheme({ phase: "generating", status: "rendering" }, theme)).toBeNull();
    },
  );
});

describe("coverThumbUrlForTheme (the derivative the card + Overview frames load)", () => {
  // theme × variant → the DERIVATIVE of whichever variant `coverImageUrlForTheme` picks. The two
  // selectors must always name the same artwork: the card and the lightbox show one cover.
  it.each([
    ["light" as const, imageState(DARK, LIGHT), DARK_THUMB],
    ["dark" as const, imageState(DARK, LIGHT), LIGHT_THUMB],
    ["light" as const, imageState(DARK, null), DARK_THUMB],
    ["dark" as const, imageState(DARK, null), DARK_THUMB], // no light twin → the dark derivative
  ])("theme=%s picks the contrasting variant's derivative", (theme, state, expected) => {
    expect(coverThumbUrlForTheme(state, theme)).toBe(expected);
  });

  it("falls back to the master when a cover has no derivative (an older cover)", () => {
    // Covers minted before derivatives existed carry no thumb — they must still render, at the
    // master, rather than showing nothing.
    const noThumbs: CourseCoverState = {
      phase: "image",
      imageUrl: DARK,
      imageUrlLight: null,
      thumbUrl: null,
      thumbUrlLight: null,
    };
    expect(coverThumbUrlForTheme(noThumbs, "light")).toBe(DARK);
    expect(coverThumbUrlForTheme(noThumbs, "dark")).toBe(DARK);
  });

  it("falls back to the DARK master, not the light thumb, when only the dark derivative is missing", () => {
    // The mirror of the case below — closing the theme x variant x thumb-present/absent matrix.
    const darkMasterOnly: CourseCoverState = {
      phase: "image",
      imageUrl: DARK,
      imageUrlLight: LIGHT,
      thumbUrl: null,
      thumbUrlLight: LIGHT_THUMB,
    };
    expect(coverThumbUrlForTheme(darkMasterOnly, "light")).toBe(DARK);
  });

  it("falls back to the LIGHT master, not the dark thumb, when only the light derivative is missing", () => {
    // The variant is chosen FIRST, then thumb-or-master within it. Choosing among thumbs first would
    // show the dark artwork on the card while the lightbox showed the light one — two covers.
    const lightMasterOnly: CourseCoverState = {
      phase: "image",
      imageUrl: DARK,
      imageUrlLight: LIGHT,
      thumbUrl: DARK_THUMB,
      thumbUrlLight: null,
    };
    expect(coverThumbUrlForTheme(lightMasterOnly, "dark")).toBe(LIGHT);
  });

  it.each(["light" as const, "dark" as const])(
    "returns null for a non-image state in theme=%s",
    (theme) => {
      expect(coverThumbUrlForTheme({ phase: "fallback" }, theme)).toBeNull();
      expect(coverThumbUrlForTheme({ phase: "generating", status: "rendering" }, theme)).toBeNull();
    },
  );
});
