import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LessonVideoHero } from "./LessonVideoHero";

const API = "http://api.test";
const PROPS = {
  apiBaseUrl: API,
  courseId: "course-1",
  lessonId: "lesson-1",
  pollIntervalMs: 1,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function queuedView(jobId = "job-1") {
  return {
    job: {
      id: jobId,
      userId: "user-a",
      courseId: "course-1",
      lessonId: "lesson-1",
      kind: "lesson",
      status: "queued",
      error: null,
    },
    videoUrl: null,
    posterUrl: null,
  };
}

function readyView(jobId = "job-1") {
  return {
    ...queuedView(jobId),
    job: { ...queuedView(jobId).job, status: "ready" },
    videoUrl: `https://signed.example/u/course-1/${jobId}/final.mp4?token=t`,
    posterUrl: `https://signed.example/u/course-1/${jobId}/poster.jpg?token=t`,
  };
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("LessonVideoHero", () => {
  it("starts as a quiet generate affordance and calls nothing", () => {
    render(<LessonVideoHero {...PROPS} />);

    expect(screen.getByRole("button", { name: /generate video/i })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("walks generate → working → ready and plays the signed MP4 inline", async () => {
    // Arrange — enqueue accepts; the first status poll stays pending until the test releases
    // it, so the working state is deterministically observable.
    let releasePoll: (response: Response) => void = () => {};
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView()))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (releasePoll = resolve)))
      .mockResolvedValue(jsonResponse(200, readyView()));
    render(<LessonVideoHero {...PROPS} />);

    // Act — the user asks for the video.
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));

    // Assert — a live status while the job works…
    expect(await screen.findByRole("status")).toBeInTheDocument();
    releasePoll(jsonResponse(200, readyView()));
    // …then the ready poster; playing mounts a native <video> on the signed URL.
    const play = await screen.findByRole("button", { name: /play lesson video/i });
    fireEvent.click(play);
    const video = document.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.src).toContain("final.mp4");
    expect(video?.poster).toContain("poster.jpg");
    // The enqueue hit the right route.
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(
      `${API}/api/courses/course-1/lessons/lesson-1/video`,
    );
  });

  it("shows the keyless refusal and withdraws the generate affordance", async () => {
    // Arrange — the API refuses: videos are not a Draft-tier capability.
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { detail: "Video generation needs an Anthropic API key" }),
    );
    render(<LessonVideoHero {...PROPS} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));

    // Assert — the refusal is shown verbatim; no broken retry loop is offered.
    expect(await screen.findByText(/needs an anthropic api key/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /generate video/i })).toBeNull();
  });

  it("disappears entirely when the feature is switched off", async () => {
    // Arrange — the kill-switch: the surface does not exist (404).
    fetchMock.mockResolvedValueOnce(jsonResponse(404, { detail: "Video generation is not enabled" }));
    const { container } = render(<LessonVideoHero {...PROPS} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));

    // Assert — a kill-switched feature leaves no husk behind.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("surfaces a failed job with a retry that re-enqueues", async () => {
    // Arrange — enqueue accepts, the poll reports the job failed, the retry enqueues again.
    const failed = {
      ...queuedView(),
      job: { ...queuedView().job, status: "failed", error: "video generation failed" },
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView()))
      .mockResolvedValueOnce(jsonResponse(200, failed))
      .mockResolvedValueOnce(jsonResponse(202, queuedView("job-2")))
      .mockResolvedValue(jsonResponse(200, readyView("job-2")));
    render(<LessonVideoHero {...PROPS} />);

    // Act — generate, watch it fail.
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    const retry = await screen.findByRole("button", { name: /try again/i });
    expect(screen.getByText(/couldn.t generate/i)).toBeInTheDocument();

    // Act — retry succeeds end-to-end.
    fireEvent.click(retry);
    expect(await screen.findByRole("button", { name: /play lesson video/i })).toBeInTheDocument();
  });

  it("resets to idle when the lesson changes", async () => {
    // Arrange — lesson-1's job is ready…
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView()))
      .mockResolvedValue(jsonResponse(200, readyView()));
    const { rerender } = render(<LessonVideoHero {...PROPS} />);
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    await screen.findByRole("button", { name: /play lesson video/i });

    // Act — …then the reader navigates to lesson-2.
    rerender(<LessonVideoHero {...PROPS} lessonId="lesson-2" />);

    // Assert — the slot belongs to the new lesson: back to the generate affordance.
    expect(screen.getByRole("button", { name: /generate video/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play lesson video/i })).toBeNull();
  });
});
