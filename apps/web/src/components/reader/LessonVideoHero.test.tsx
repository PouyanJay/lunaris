import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { VideoArtifact } from "../../types/course";
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
    captionsUrl: null,
  };
}

function readyView(jobId = "job-1", captionsUrl: string | null = null) {
  return {
    ...queuedView(jobId),
    job: { ...queuedView(jobId).job, status: "ready" },
    videoUrl: `https://signed.example/u/course-1/${jobId}/final.mp4?token=t`,
    posterUrl: `https://signed.example/u/course-1/${jobId}/poster.jpg?token=t`,
    captionsUrl,
  };
}

function failedView(jobId = "job-1") {
  return {
    ...queuedView(jobId),
    job: { ...queuedView(jobId).job, status: "failed", error: "video generation failed" },
  };
}

const fetchMock = vi.fn<typeof fetch>();

/** No in-flight (re)generate for the slot — the default answer to the on-mount re-attach probe. */
function noActive(): Response {
  return new Response(null, { status: 204 });
}

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

    // Assert — findByRole polls until React flushes the enqueue response → working transition; the
    // status poll's promise is still pending here, so the working state (a progress bar) is observable.
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
    releasePoll(jsonResponse(200, readyView()));
    // …then the ready poster; playing mounts a native <video> on the signed URL.
    const play = await screen.findByRole("button", { name: /play lesson video/i });
    fireEvent.click(play);
    const video = document.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.src).toContain("final.mp4");
    expect(video?.poster).toContain("poster.jpg");
    expect(video?.hasAttribute("controls")).toBe(true);
    // A silent video carries no captions track and no CORS opt-in.
    expect(video?.querySelector("track")).toBeNull();
    expect(video?.hasAttribute("crossorigin")).toBe(false);
    // The enqueue was a POST to the right route (order-independent matcher).
    expect(fetchMock).toHaveBeenCalledWith(
      `${API}/api/courses/course-1/lessons/lesson-1/video`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("attaches a WebVTT captions track for a narrated video", async () => {
    // Arrange — a narrated video ships a captions URL (the silent path has none).
    const captionsUrl = "https://signed.example/u/course-1/job-1/captions.vtt?token=t";
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView()))
      .mockResolvedValue(jsonResponse(200, readyView("job-1", captionsUrl)));
    render(<LessonVideoHero {...PROPS} />);

    // Act — generate, then play.
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    fireEvent.click(await screen.findByRole("button", { name: /play lesson video/i }));

    // Assert — the player carries a default English captions <track> on the signed VTT, and the
    // <video> opts into CORS so the cross-origin track loads (WCAG 2.2 AA captions).
    const video = document.querySelector("video");
    const track = video?.querySelector("track");
    expect(track).not.toBeNull();
    expect(track?.getAttribute("kind")).toBe("captions");
    expect(track?.src).toContain("captions.vtt");
    expect(track?.hasAttribute("default")).toBe(true);
    // WCAG 2.2 AA: the track must declare its language and a human label.
    expect(track?.getAttribute("srclang")).toBe("en");
    expect(track?.getAttribute("label")).toBe("English");
    expect(video?.getAttribute("crossorigin")).toBe("anonymous");
  });

  it("shows the keyless refusal and withdraws the generate affordance", async () => {
    // Arrange — the API refuses: videos are not a Draft-tier capability.
    fetchMock.mockResolvedValueOnce(
      jsonResponse(403, { detail: "Video generation needs an Anthropic API key" }),
    );
    render(<LessonVideoHero {...PROPS} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));

    // Assert — the refusal is announced (role=status), shown verbatim, and the affordance
    // is withdrawn; no broken retry loop is offered.
    expect(await screen.findByText(/needs an anthropic api key/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/anthropic api key/i);
    expect(screen.queryByRole("button", { name: /generate video/i })).toBeNull();
  });

  it("treats a server error on enqueue as a failed state with retry", async () => {
    // Arrange — the network itself fails; the slot must degrade to the recoverable state.
    fetchMock.mockRejectedValueOnce(new Error("network down"));
    render(<LessonVideoHero {...PROPS} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));

    // Assert
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("disappears entirely when the feature is switched off", async () => {
    // Arrange — the kill-switch: the surface does not exist (404).
    fetchMock.mockResolvedValueOnce(
      jsonResponse(404, { detail: "Video generation is not enabled" }),
    );
    const { container } = render(<LessonVideoHero {...PROPS} />);

    // Act
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));

    // Assert — a kill-switched feature leaves no husk behind.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it("surfaces a failed job and regenerates from the Try again menu", async () => {
    // Arrange — enqueue accepts, the poll reports failed; the menu's Fresh take re-runs end to end.
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView())) // enqueue
      .mockResolvedValueOnce(jsonResponse(200, failedView())) // poll → failed
      .mockResolvedValueOnce(jsonResponse(202, queuedView("job-2"))) // regenerate
      .mockResolvedValue(jsonResponse(200, readyView("job-2"))); // poll → ready
    render(<LessonVideoHero {...PROPS} />);

    // Act — generate, watch it fail.
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    const tryAgain = await screen.findByRole("button", { name: /try again/i });
    expect(screen.getByText(/couldn.t generate/i)).toBeInTheDocument();

    // Act — open the menu and pick Fresh take; the regenerated job renders.
    fireEvent.click(tryAgain);
    fireEvent.click(await screen.findByRole("menuitem", { name: /fresh take/i }));

    expect(await screen.findByRole("button", { name: /play lesson video/i })).toBeInTheDocument();
    const regenerate = fetchMock.mock.calls.find(([url]) => String(url).includes("/regenerate"));
    expect(JSON.parse(String((regenerate?.[1] as RequestInit).body))).toEqual({ mode: "fresh" });
  });

  it("falls back to the failed state when a regenerate is refused (409)", async () => {
    // Arrange — generate → fail; then the menu's Retry hits a 409 (the contract can't be reused).
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView())) // enqueue
      .mockResolvedValueOnce(jsonResponse(200, failedView())) // poll → failed
      .mockResolvedValueOnce(jsonResponse(409, { detail: "hasn't finished" })); // regenerate
    render(<LessonVideoHero {...PROPS} />);
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    const tryAgain = await screen.findByRole("button", { name: /try again/i });

    // Act — open the menu, pick Fresh take, but the server refuses.
    fireEvent.click(tryAgain);
    fireEvent.click(await screen.findByRole("menuitem", { name: /fresh take/i }));

    // Assert — the slot stays failed (the Try again menu reappears), no broken player.
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play lesson video/i })).toBeNull();
  });

  it("offers Add narration on a ready silent video but not a narrated one", async () => {
    // A silent ready video (no captions) → the menu includes Add narration.
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView()))
      .mockResolvedValue(jsonResponse(200, readyView("job-1", null)));
    const { unmount } = render(<LessonVideoHero {...PROPS} />);
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    await screen.findByRole("button", { name: /play lesson video/i });

    fireEvent.click(screen.getByRole("button", { name: /^regenerate$/i }));
    expect(screen.getByRole("menuitem", { name: /add narration/i })).toBeInTheDocument();
    unmount();

    // A narrated ready video (captions present) → Add narration is hidden.
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(202, queuedView()))
      .mockResolvedValue(jsonResponse(200, readyView("job-1", "https://signed/c.vtt")));
    render(<LessonVideoHero {...PROPS} />);
    fireEvent.click(screen.getByRole("button", { name: /generate video/i }));
    await screen.findByRole("button", { name: /play lesson video/i });

    fireEvent.click(screen.getByRole("button", { name: /^regenerate$/i }));
    expect(screen.queryByRole("menuitem", { name: /add narration/i })).toBeNull();
    expect(screen.getByRole("menuitem", { name: /^retry/i })).toBeInTheDocument();
  });

  it("resolves the build-time lesson video and flags it outdated when the lesson was revised", async () => {
    // Arrange — the course shipped a lesson video; the status read reports it stale (lesson revised).
    const built: VideoArtifact = {
      kind: "lesson",
      status: "ready",
      jobId: "built-1",
      provenance: null,
      narrated: false,
    };
    fetchMock.mockImplementation((input) =>
      Promise.resolve(
        String(input).endsWith("/active")
          ? noActive()
          : jsonResponse(200, { ...readyView("built-1"), stale: true }),
      ),
    );

    // Act — no generate click: the built video resolves on its own.
    render(<LessonVideoHero {...PROPS} video={built} />);

    // Assert — it resolved the BUILT job's url, then shows the outdated badge + the regenerate menu.
    await screen.findByRole("button", { name: /play lesson video/i });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/videos/built-1"),
      expect.any(Object),
    );
    expect(screen.getByText("OUTDATED")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^regenerate$/i })).toBeInTheDocument();
  });

  it("clears the outdated badge after regenerating the built video", async () => {
    // Arrange — a built video resolves stale; the menu's Fresh take re-runs it to a fresh result.
    const built: VideoArtifact = {
      kind: "lesson",
      status: "ready",
      jobId: "built-1",
      provenance: null,
      narrated: false,
    };
    // URL-routed so the on-mount re-attach probe (/active → nothing in flight) doesn't perturb the
    // resolve → regenerate → poll-new sequence.
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/active")) return Promise.resolve(noActive());
      if (url.includes("/regenerate"))
        return Promise.resolve(jsonResponse(202, queuedView("job-2")));
      if (url.includes("/videos/built-1"))
        return Promise.resolve(jsonResponse(200, { ...readyView("built-1"), stale: true }));
      return Promise.resolve(jsonResponse(200, { ...readyView("job-2"), stale: false }));
    });
    render(<LessonVideoHero {...PROPS} video={built} />);
    await screen.findByRole("button", { name: /play lesson video/i });
    expect(screen.getByText("OUTDATED")).toBeInTheDocument();

    // Act — regenerate via Fresh take.
    fireEvent.click(screen.getByRole("button", { name: /^regenerate$/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /fresh take/i }));

    // Assert — the regenerated video plays with the badge gone.
    await waitFor(() => expect(screen.queryByText("OUTDATED")).toBeNull());
    expect(screen.getByRole("button", { name: /play lesson video/i })).toBeInTheDocument();
  });

  it("shows a fresh build-time lesson video with no outdated badge", async () => {
    const built: VideoArtifact = {
      kind: "lesson",
      status: "ready",
      jobId: "built-1",
      provenance: null,
      narrated: false,
    };
    fetchMock.mockImplementation((input) =>
      Promise.resolve(
        String(input).endsWith("/active")
          ? noActive()
          : jsonResponse(200, { ...readyView("built-1"), stale: false }),
      ),
    );

    render(<LessonVideoHero {...PROPS} video={built} />);

    await screen.findByRole("button", { name: /play lesson video/i });
    expect(screen.queryByText("OUTDATED")).toBeNull();
  });

  it("re-attaches to an in-flight regenerate after a reload (Gap 1)", async () => {
    // Arrange — the persisted built artifact is FAILED (the old job), but a regenerate is running
    // under a new job id the artifact doesn't carry. The on-mount probe re-attaches to it.
    const built: VideoArtifact = {
      kind: "lesson",
      status: "failed",
      jobId: "built-fail",
      provenance: null,
      narrated: false,
    };
    // The re-attached job renders (status=rendering) so the working progress bar is observable
    // before it would settle; /videos/regen-1 stays rendering.
    const renderingView = {
      ...readyView("regen-1"),
      videoUrl: null,
      job: { ...readyView("regen-1").job, status: "rendering" },
    };
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/active")) return Promise.resolve(jsonResponse(200, queuedView("regen-1")));
      return Promise.resolve(jsonResponse(200, renderingView));
    });

    // Act — the probe finds the live regenerate and watches it.
    render(<LessonVideoHero {...PROPS} video={built} />);

    // Assert — the slot recovers the running job and shows its progress bar (not the stale failed
    // state), keyed by the source job id we held.
    const bar = await screen.findByRole("progressbar", { name: /generating the lesson video/i });
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeGreaterThan(0);
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/videos/built-fail/active")),
    ).toBe(true);
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
