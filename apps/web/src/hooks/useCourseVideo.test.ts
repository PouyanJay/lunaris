import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { VideoArtifact } from "../types/course";
import { useCourseVideo } from "./useCourseVideo";

vi.mock("../lib/videoJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/videoJobs")>();
  return {
    ...actual,
    regenerateVideo: vi.fn(),
    pollVideoJob: vi.fn(),
    findActiveVideoJobByCoordinates: vi.fn(),
    fetchVideoJob: vi.fn(),
    fetchFreshPlaybackUrls: vi.fn(),
  };
});
import {
  fetchVideoJob,
  findActiveVideoJobByCoordinates,
  pollVideoJob,
  type VideoJobView,
} from "../lib/videoJobs";

const probe = vi.mocked(findActiveVideoJobByCoordinates);
const poll = vi.mocked(pollVideoJob);
const fetchJob = vi.mocked(fetchVideoJob);

const API = "http://api.test";
const COURSE = "course-1";

function readyView(jobId: string, kind: VideoArtifact["kind"] = "summary"): VideoJobView {
  return {
    job: {
      id: jobId,
      userId: "user-a",
      courseId: COURSE,
      lessonId: null,
      kind,
      status: "ready",
      error: null,
    },
    videoUrl: `https://signed/${jobId}.mp4`,
    posterUrl: null,
    captionsUrl: null,
  };
}

function failedArtifact(kind: VideoArtifact["kind"], jobId: string | null): VideoArtifact {
  return { kind, status: "failed", jobId, provenance: null, narrated: false };
}

beforeEach(() => {
  probe.mockReset();
  poll.mockReset();
  fetchJob.mockReset();
  poll.mockImplementation(async (_api, jobId, opts) => {
    opts.onSettled(readyView(jobId));
  });
  fetchJob.mockImplementation(async (_api, jobId) => readyView(jobId));
});

afterEach(() => vi.clearAllMocks());

describe("useCourseVideo — coordinate-keyed derive-at-read", () => {
  it("resolves a FAILED course-video pointer to its now-READY job by coordinates", async () => {
    // Arrange — the Overview SUMMARY slot's payload says FAILED, but the job is READY in the queue.
    probe.mockResolvedValue(readyView("sum-job"));

    // Act
    const { result } = renderHook(() =>
      useCourseVideo(API, COURSE, failedArtifact("summary", "sum-job")),
    );

    // Assert — the slot plays; the probe was keyed by (course, kind) on the null-lesson path.
    await waitFor(() => expect(result.current.state.phase).toBe("ready"));
    expect(probe).toHaveBeenCalledWith(API, COURSE, "summary", undefined, expect.anything());
  });

  it("settles FAILED when the probe finds no live job for a failed course video", async () => {
    // Arrange — genuinely failed: no live job, no successful take.
    probe.mockResolvedValue(null);

    // Act
    const { result } = renderHook(() =>
      useCourseVideo(API, COURSE, failedArtifact("overview", "ovr-job")),
    );

    // Assert — the honest failed state once the probe settles.
    await waitFor(() => expect(result.current.state.phase).toBe("failed"));
    expect(probe).toHaveBeenCalledWith(API, COURSE, "overview", undefined, expect.anything());
  });

  it("does not probe an absent slot (no artifact, no course video built)", async () => {
    // Act — an absent course-video slot renders nothing and needs no probe (no kind to key on).
    const { result } = renderHook(() => useCourseVideo(API, COURSE, null));

    // Assert
    await waitFor(() => expect(result.current.state.phase).toBe("absent"));
    expect(probe).not.toHaveBeenCalled();
  });
});
