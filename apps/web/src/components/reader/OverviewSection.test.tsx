import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CourseVideos, VideoArtifact } from "../../types/course";
import { OverviewSection } from "./OverviewSection";

const API = "http://api.test";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function artifact(
  kind: VideoArtifact["kind"],
  jobId: string,
  status: VideoArtifact["status"] = "ready",
): VideoArtifact {
  return {
    kind,
    status,
    provenance:
      status === "ready"
        ? {
            jobId,
            courseId: "course-1",
            lessonId: null,
            kind,
            model: "m",
            contractHash: "h",
            inputHash: "h",
            claimIds: [],
            generatedAt: "2026-01-01T00:00:00+00:00",
          }
        : null,
    narrated: false,
    durationS: 80,
  };
}

function readyView(jobId: string) {
  return {
    job: {
      id: jobId,
      userId: "user-a",
      courseId: "course-1",
      lessonId: null,
      kind: "summary",
      status: "ready",
      error: null,
    },
    videoUrl: `https://signed.example/u/course-1/${jobId}/final.mp4?token=t`,
    posterUrl: `https://signed.example/u/course-1/${jobId}/poster.jpg?token=t`,
    captionsUrl: null,
  };
}

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  // Each GET /api/videos/{jobId} resolves to that job's signed URLs.
  fetchMock.mockImplementation((input) => {
    const jobId = String(input).split("/videos/")[1] ?? "job";
    return Promise.resolve(jsonResponse(200, readyView(jobId)));
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

describe("OverviewSection", () => {
  it("opens the course with the trailer first, then the topic overview", async () => {
    // Arrange — both course videos built.
    const videos: CourseVideos = {
      summary: artifact("summary", "sum-1"),
      overview: artifact("overview", "ovr-1"),
    };

    // Act
    render(<OverviewSection videos={videos} apiBaseUrl={API} />);

    // Assert — both play affordances resolve, and the trailer precedes the overview in reading order
    // (the course opens "what this course covers" → "what this topic is and why it matters").
    await screen.findByRole("button", { name: /play the course trailer/i });
    await screen.findByRole("button", { name: /play the topic overview/i });
    const headings = screen.getAllByRole("heading").map((h) => h.textContent);
    expect(headings).toEqual(["What this course covers", "What this topic is and why it matters"]);
  });

  it("plays a course video's signed MP4 in place", async () => {
    // Arrange / Act
    render(<OverviewSection videos={{ summary: artifact("summary", "sum-1") }} apiBaseUrl={API} />);
    fireEvent.click(await screen.findByRole("button", { name: /play the course trailer/i }));

    // Assert — a native <video> on the job's signed URL, no third party.
    const video = document.querySelector("video");
    expect(video?.src).toContain("sum-1/final.mp4");
    expect(video?.poster).toContain("sum-1/poster.jpg");
    expect(video?.hasAttribute("controls")).toBe(true);
  });

  it("renders only the slots that were built", async () => {
    // Arrange — a summary-only build (the overview was skipped, e.g. a briefless course).
    render(<OverviewSection videos={{ summary: artifact("summary", "sum-1") }} apiBaseUrl={API} />);

    // Assert — the trailer slot only; no empty overview husk.
    await screen.findByRole("button", { name: /play the course trailer/i });
    expect(screen.queryByText("What this topic is and why it matters")).toBeNull();
  });

  it("shows an honest message for a degraded video instead of a broken player", async () => {
    // Arrange — the overview render failed; the summary is fine.
    const videos: CourseVideos = {
      summary: artifact("summary", "sum-1"),
      overview: artifact("overview", "ovr-1", "failed"),
    };

    // Act — await the summary resolving so the failed overview is asserted against a settled tree.
    render(<OverviewSection videos={videos} apiBaseUrl={API} />);
    await screen.findByRole("button", { name: /play the course trailer/i });

    // Assert — the failed slot states it plainly and offers no broken play target; the course is
    // still usable. A FAILED artifact never hits the network (no jobId to resolve).
    expect(screen.getByText(/couldn.t be generated/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /play the topic overview/i })).toBeNull();
    // The failed artifact has no jobId to resolve, so it never hits the network in any call shape.
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/videos/ovr-1"))).toBe(false);
  });

  it("shows the honest message when a ready artifact carries no resolvable jobId", () => {
    // Arrange — a READY artifact with no provenance (e.g. a pre-provenance worker); it can't resolve
    // a signed URL, so it degrades like a failure rather than rendering a broken player.
    const noJobId: VideoArtifact = { kind: "summary", status: "ready", provenance: null, narrated: false };

    // Act
    render(<OverviewSection videos={{ summary: noJobId }} apiBaseUrl={API} />);

    // Assert — the honest message, and no network call (there is no jobId to fetch).
    expect(screen.getByText(/couldn.t be generated/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a loading skeleton while the signed URL resolves, then the player", async () => {
    // Arrange — hold the signed-URL fetch open so the transient loading state is observable.
    let releaseUrl: (response: Response) => void = () => {};
    fetchMock.mockImplementationOnce(
      () => new Promise<Response>((resolve) => (releaseUrl = resolve)),
    );

    // Act
    render(<OverviewSection videos={{ summary: artifact("summary", "sum-1") }} apiBaseUrl={API} />);

    // Assert — the skeleton announces itself while resolving…
    expect(
      await screen.findByRole("status", { name: /loading what this course covers/i }),
    ).toBeInTheDocument();
    // …then the URL lands and the play affordance replaces it (no skeleton left behind).
    releaseUrl(jsonResponse(200, readyView("sum-1")));
    await screen.findByRole("button", { name: /play the course trailer/i });
    expect(screen.queryByRole("status", { name: /loading/i })).toBeNull();
  });

  it("renders nothing when neither course video was built", () => {
    // Arrange / Act — a video-on build where both course-level renders were absent.
    const { container } = render(<OverviewSection videos={{}} apiBaseUrl={API} />);

    // Assert — no Overview section husk.
    expect(container).toBeEmptyDOMElement();
  });
});
