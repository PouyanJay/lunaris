import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CoverArtifact } from "../types/course";
import { useCourseCover } from "./useCourseCover";

vi.mock("../lib/coverJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/coverJobs")>();
  return { ...actual, fetchCoverJob: vi.fn(), pollCoverJob: vi.fn() };
});
import { fetchCoverJob, pollCoverJob, type CoverJobView } from "../lib/coverJobs";

const fetchJob = vi.mocked(fetchCoverJob);
const poll = vi.mocked(pollCoverJob);

const API = "http://api.test";

function readyView(jobId: string): CoverJobView {
  return {
    job: { id: jobId, courseId: "c1", status: "ready", stylePreset: "nocturne", error: null },
    imageUrl: `https://signed/${jobId}.png`,
    provenance: null,
  };
}

function artifact(status: CoverArtifact["status"], jobId: string | null = "job-1"): CoverArtifact {
  return { status, jobId, provenance: null };
}

beforeEach(() => {
  fetchJob.mockReset();
  poll.mockReset();
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
      }),
    );
  });

  it("does not fetch or poll without an API base URL", () => {
    const { result } = renderHook(() => useCourseCover(undefined, artifact("ready")));
    expect(result.current.state).toEqual({ phase: "fallback" });
    expect(fetchJob).not.toHaveBeenCalled();
    expect(poll).not.toHaveBeenCalled();
  });
});
