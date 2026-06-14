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

/** No in-flight (re)generate for the slot — the default answer to the on-mount re-attach probe. */
function noActive(): Response {
  return new Response(null, { status: 204 });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  // GET /api/videos/{jobId}/active → 204 (nothing in flight); GET /api/videos/{jobId} → its URLs.
  fetchMock.mockImplementation((input) => {
    const url = String(input);
    if (url.endsWith("/active")) return Promise.resolve(noActive());
    const jobId = url.split("/videos/")[1] ?? "job";
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
    const noJobId: VideoArtifact = {
      kind: "summary",
      status: "ready",
      provenance: null,
      narrated: false,
    };

    // Act
    render(<OverviewSection videos={{ summary: noJobId }} apiBaseUrl={API} />);

    // Assert — the honest message, and no network call (there is no jobId to fetch).
    expect(screen.getByText(/couldn.t be generated/i)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a loading skeleton while the signed URL resolves, then the player", async () => {
    // Arrange — hold the FIRST fetch (the ready-fetch effect, declared before the re-attach probe in
    // useCourseVideo) open so the transient loading state is observable; later calls (incl. the
    // /active probe) fall through to the beforeEach router (204 → no re-attach).
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

  it("offers a Regenerate menu on a ready course video and re-runs it", async () => {
    // Arrange — a ready summary; its menu's Fresh take re-runs the course video.
    render(<OverviewSection videos={{ summary: artifact("summary", "sum-1") }} apiBaseUrl={API} />);
    await screen.findByRole("button", { name: /play the course trailer/i });

    // Act — open the regenerate menu and pick Fresh take.
    fireEvent.click(screen.getByRole("button", { name: /^regenerate$/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /fresh take/i }));

    // Assert — the POST targeted the source job with the chosen mode.
    const regen = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/videos/sum-1/regenerate"),
    );
    expect(JSON.parse(String((regen?.[1] as RequestInit).body))).toEqual({ mode: "fresh" });
  });

  it("shows the outdated badge when a ready course video reports stale", async () => {
    // The stale flag from the status read plumbs through useCourseVideo to the slot's badge. /active
    // is routed to 204 so the badge is asserted on the ready-fetch path, not the re-attach probe.
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/active")) return Promise.resolve(noActive());
      const jobId = url.split("/videos/")[1] ?? "job";
      return Promise.resolve(jsonResponse(200, { ...readyView(jobId), stale: true }));
    });

    render(<OverviewSection videos={{ summary: artifact("summary", "sum-1") }} apiBaseUrl={API} />);

    await screen.findByRole("button", { name: /play the course trailer/i });
    expect(screen.getByText("OUTDATED")).toBeInTheDocument();
  });

  it("offers a Try again menu on a failed course video and regenerates it", async () => {
    // Arrange — a FAILED artifact that still carries its job id (V6), so the slot can re-run it.
    const failed: VideoArtifact = {
      kind: "summary",
      status: "failed",
      jobId: "sum-fail",
      provenance: null,
      narrated: false,
    };
    fetchMock.mockReset();
    const queued = { ...readyView("sum-2"), job: { ...readyView("sum-2").job, status: "queued" } };
    // URL-routed (not call-order): /active → nothing in flight, /regenerate → the queued new job,
    // /videos/{id} → its ready URLs — so the on-mount re-attach probe doesn't perturb the sequence.
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/active")) return Promise.resolve(noActive());
      if (url.includes("/regenerate")) return Promise.resolve(jsonResponse(202, queued));
      return Promise.resolve(jsonResponse(200, readyView("sum-2")));
    });
    render(<OverviewSection videos={{ summary: failed }} apiBaseUrl={API} />);

    // Act — the failed slot states it plainly and offers a Try again menu; Fresh take re-runs it.
    expect(screen.getByText(/couldn.t be generated/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /fresh take/i }));

    // Assert — the regenerated job polls to a playable trailer; the POST hit the source job.
    await screen.findByRole("button", { name: /play the course trailer/i });
    const regen = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/videos/sum-fail/regenerate"),
    );
    expect(JSON.parse(String((regen?.[1] as RequestInit).body))).toEqual({ mode: "fresh" });
  });

  it("re-attaches to an in-flight regenerate the failed artifact doesn't know about (Gap 1)", async () => {
    // Arrange — the persisted artifact is the OLD failed job, but a regenerate is running under a
    // NEW job id it doesn't carry (the user regenerated, then navigated away and back / refreshed).
    const failed: VideoArtifact = {
      kind: "summary",
      status: "failed",
      jobId: "sum-fail",
      provenance: null,
      narrated: false,
    };
    const activeJob = {
      ...readyView("sum-regen"),
      videoUrl: null,
      posterUrl: null,
      job: { ...readyView("sum-regen").job, status: "queued" },
    };
    fetchMock.mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/active")) return Promise.resolve(jsonResponse(200, activeJob));
      return Promise.resolve(jsonResponse(200, readyView("sum-regen")));
    });

    // Act — the on-mount probe discovers the live regenerate and watches it to a verdict.
    render(<OverviewSection videos={{ summary: failed }} apiBaseUrl={API} />);

    // Assert — the slot recovers the running job and plays it; it does NOT strand on "couldn't
    // generate" (the "nothing happening" bug). The probe was keyed by the source job we held.
    await screen.findByRole("button", { name: /play the course trailer/i });
    expect(screen.queryByText(/couldn.t be generated/i)).toBeNull();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).endsWith("/videos/sum-fail/active")),
    ).toBe(true);
  });

  it("shows a labelled progress bar while a re-attached course video renders (Gap 2)", async () => {
    // Arrange — the persisted artifact failed, but a regenerate is mid-render; the re-attach probe
    // finds it and the slot reports its progress instead of a featureless shimmer.
    const failed: VideoArtifact = {
      kind: "summary",
      status: "failed",
      jobId: "sum-fail",
      provenance: null,
      narrated: false,
    };
    const rendering = {
      ...readyView("sum-regen"),
      videoUrl: null,
      posterUrl: null,
      job: { ...readyView("sum-regen").job, status: "rendering" },
    };
    // /active → the rendering job; the status poll stays rendering, so the bar is observable.
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(200, rendering)));

    // Act
    render(<OverviewSection videos={{ summary: failed }} apiBaseUrl={API} />);

    // Assert — a determinate, labelled progress bar with the plain-language stage caption.
    const bar = await screen.findByRole("progressbar", {
      name: /generating what this course covers/i,
    });
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeGreaterThan(0);
    expect(screen.getByText(/rendering the scenes/i)).toBeInTheDocument();
  });

  it("renders nothing when neither course video was built", () => {
    // Arrange / Act — a video-on build where both course-level renders were absent.
    const { container } = render(<OverviewSection videos={{}} apiBaseUrl={API} />);

    // Assert — no Overview section husk.
    expect(container).toBeEmptyDOMElement();
  });
});
