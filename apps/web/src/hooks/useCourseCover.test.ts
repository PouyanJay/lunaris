import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CoverArtifact } from "../types/course";
import { useCourseCover } from "./useCourseCover";

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

function readyView(jobId: string, imageUrlLight: string | null = null): CoverJobView {
  return {
    job: { id: jobId, courseId: "c1", status: "ready", stylePreset: "nocturne", error: null },
    imageUrl: `https://signed/${jobId}.png`,
    imageUrlLight,
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
    poll.mockImplementation(async (_api, jobId, opts) => opts.onSettled(readyView(jobId)));

    const { result } = renderHook(() => useCourseCover(API, artifact("ready")));
    await waitFor(() => expect(result.current.state.phase).toBe("image"));

    act(() => result.current.regenerate());

    // The regenerate enqueues job-2 and polls it → the image swaps to the new job's signed URL.
    await waitFor(() =>
      expect(result.current.state).toEqual({
        phase: "image",
        imageUrl: "https://signed/job-2.png",
        imageUrlLight: null,
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
