import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { VideoArtifact } from "../types/course";
import { useLessonVideo } from "./useLessonVideo";

// Keep the pure helpers (resolveJobId, videoProgress) real; stub only the network functions.
vi.mock("../lib/videoJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/videoJobs")>();
  return {
    ...actual,
    enqueueLessonVideo: vi.fn(),
    regenerateVideo: vi.fn(),
    pollVideoJob: vi.fn(),
    findActiveVideoJobByCoordinates: vi.fn(),
    fetchVideoJob: vi.fn(),
    fetchFreshPlaybackUrls: vi.fn(),
  };
});
import { findActiveVideoJobByCoordinates, pollVideoJob, type VideoJobView } from "../lib/videoJobs";

const probe = vi.mocked(findActiveVideoJobByCoordinates);
const poll = vi.mocked(pollVideoJob);

const API = "http://api.test";
const COURSE = "course-1";
const LESSON = "lesson-1";

function readyView(jobId: string): VideoJobView {
  return {
    job: {
      id: jobId,
      userId: "user-a",
      courseId: COURSE,
      lessonId: LESSON,
      kind: "lesson",
      status: "ready",
      error: null,
    },
    videoUrl: `https://signed/${jobId}.mp4`,
    posterUrl: null,
    captionsUrl: null,
  };
}

function failedArtifact(jobId: string | null): VideoArtifact {
  return { kind: "lesson", status: "failed", jobId, provenance: null, narrated: false };
}

beforeEach(() => {
  probe.mockReset();
  poll.mockReset();
  // The default watch: settle the watched job READY immediately (the hook calls this after a probe
  // surfaces a job). Each test overrides as needed.
  poll.mockImplementation(async (_api, jobId, opts) => {
    opts.onSettled(readyView(jobId));
  });
});

afterEach(() => vi.clearAllMocks());

describe("useLessonVideo — coordinate-keyed derive-at-read", () => {
  it("resolves a FAILED-payload slot to its now-READY job via the coordinate probe", async () => {
    // Arrange — the prod bug: the payload pointer is FAILED (carrying its build job id), but that
    // same job has since gone READY. The coordinate probe surfaces it; no source job id needed.
    probe.mockResolvedValue(readyView("build-job"));

    // Act
    const { result } = renderHook(() =>
      useLessonVideo(API, COURSE, LESSON, 10, failedArtifact("build-job")),
    );

    // Assert — the slot recovers to ready, and the probe was keyed by the slot's coordinates.
    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(probe).toHaveBeenCalledWith(API, COURSE, "lesson", LESSON, expect.anything());
  });

  it("watches a built-READY slot's coordinates and adopts a newer regenerate take", async () => {
    // Arrange — the payload shipped a READY video, but a newer regenerate for the slot has since
    // finished. The coordinate probe surfaces the newer take and the slot re-resolves to it.
    const built: VideoArtifact = {
      kind: "lesson",
      status: "ready",
      jobId: "built-1",
      provenance: {
        jobId: "built-1",
        courseId: COURSE,
        lessonId: LESSON,
        kind: "lesson",
        model: "m",
        contractHash: "h",
        inputHash: "h",
        claimIds: [],
        generatedAt: "2026-01-01T00:00:00+00:00",
      },
      narrated: false,
    };
    probe.mockResolvedValue(readyView("regen-2"));

    // Act
    const { result } = renderHook(() => useLessonVideo(API, COURSE, LESSON, 10, built));

    // Assert — it ends ready, and the probe was keyed by the slot's coordinates.
    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(probe).toHaveBeenCalledWith(API, COURSE, "lesson", LESSON, expect.anything());
  });

  it("does not double-poll when the probe echoes the job the first effect already watches", async () => {
    // Arrange — a built-READY slot. The first effect watches its job; the coordinate probe returns
    // that SAME job (no newer take). The dedup guard (view.job.id !== jobIdRef.current) must skip it,
    // so the slot polls exactly once — not twice for one job.
    const built: VideoArtifact = {
      kind: "lesson",
      status: "ready",
      jobId: "built-1",
      provenance: {
        jobId: "built-1",
        courseId: COURSE,
        lessonId: LESSON,
        kind: "lesson",
        model: "m",
        contractHash: "h",
        inputHash: "h",
        claimIds: [],
        generatedAt: "2026-01-01T00:00:00+00:00",
      },
      narrated: false,
    };
    probe.mockResolvedValue(readyView("built-1")); // the probe sees the same job

    // Act
    const { result } = renderHook(() => useLessonVideo(API, COURSE, LESSON, 10, built));

    // Assert — settled ready, and the job was watched once (the probe's echo was skipped).
    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(poll).toHaveBeenCalledTimes(1);
    expect(poll.mock.calls[0]?.[1]).toBe("built-1");
  });

  it("settles FAILED when the probe finds no live job for a failed payload slot", async () => {
    // Arrange — genuinely failed: nothing in flight and no successful take.
    probe.mockResolvedValue(null);

    // Act
    const { result } = renderHook(() =>
      useLessonVideo(API, COURSE, LESSON, 10, failedArtifact("build-job")),
    );

    // Assert — the honest failed state (deferred until the probe settled, not flashed first).
    await waitFor(() => expect(result.current.state.phase).toBe("failed"));
  });

  it("stays a quiet idle affordance with no built video, and never probes", async () => {
    // Arrange / Act — a lesson the build shipped no video for (no `video` argument). The finalize
    // fold is never null, so an absent built artifact means there is no slot to re-resolve; the hero
    // stays the quiet "Generate video" affordance and makes no network probe (no per-nav chatter).
    const { result } = renderHook(() => useLessonVideo(API, COURSE, LESSON, 10));

    // Assert — the idle gate (`builtStatus === null`) returns synchronously, so the probe is never
    // reached. waitFor confirms the no-call holds (not a single-microtask false-safety yield).
    await waitFor(() => expect(result.current.state.phase).toBe("idle"));
    expect(probe).not.toHaveBeenCalled();
  });
});
