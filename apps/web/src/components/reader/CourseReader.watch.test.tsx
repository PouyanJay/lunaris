import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeCourse, routedFetch } from "../../test/fixtures";
import type { VideoArtifact } from "../../types/course";
import { CourseReader, READER_MODE_KEY } from "./CourseReader";

/** The reader-mode toggle — now just Learn/Watch (Read is retired, and the in-Watch consumption
 *  sub-control is gone). */
function readerModeToggle() {
  return within(screen.getByRole("radiogroup", { name: /reading mode/i }));
}

/** A build-time lesson video the course shipped (resolved ready via the video route below). */
const READY_VIDEO: VideoArtifact = {
  kind: "lesson",
  status: "ready",
  jobId: "built-1",
  provenance: null,
  narrated: false,
};

/** GET /api/videos/{id} for a ready video whose outline carries two chapters + one spoken cue —
 *  the Cinema data the Watch surface renders. */
function chapteredVideoView() {
  return {
    job: {
      id: "built-1",
      userId: "u",
      courseId: "course-test",
      lessonId: "m-binary_search-l0",
      kind: "lesson",
      status: "ready",
      error: null,
    },
    videoUrl: "https://signed.example/u/course-test/built-1/final.mp4?token=t",
    posterUrl: "https://signed.example/u/course-test/built-1/poster.jpg?token=t",
    captionsUrl: null,
    stale: false,
    provenance: { degradedScenes: [] },
    chapters: [
      { id: "S1_intro", title: "Intro", startS: 0, endS: 20 },
      { id: "S2_mechanism", title: "How it halves", startS: 20, endS: 60 },
    ],
    transcript: [{ startS: 0, endS: 5, text: "Welcome to binary search." }],
  };
}

/** A ready but un-narrated video: chapters navigate, but there is no transcript. */
function silentVideoView() {
  return { ...chapteredVideoView(), transcript: [] };
}

/** A ready video rendered before Cinema shipped: no chapter outline at all. */
function preCinemaVideoView() {
  return { ...chapteredVideoView(), chapters: [], transcript: [] };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** routedFetch for the reader's other routes, with the video routes intercepted to serve the given
 *  view: the ready-job poll and the coordinate re-attach probe (GET), plus an on-demand generate
 *  enqueue (POST /lessons/{id}/video) that is accepted and resolves to the same view. */
function videoFetch(view: unknown = chapteredVideoView()) {
  const base = routedFetch({ progress: { courseId: "course-test", objectives: [], lessons: [] } });
  return vi.fn((input: Parameters<typeof fetch>[0], init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (/\/lessons\/[^/?]+\/video$/.test(url) && method === "POST") {
      return Promise.resolve(jsonResponse(200, view)); // enqueue accepted → the view's job
    }
    if (url.split("?")[0]!.endsWith("/videos/active")) {
      return Promise.resolve(new Response(null, { status: 204 })); // nothing newer in flight
    }
    if (/\/api\/videos\/[^/?]+/.test(url)) {
      return Promise.resolve(jsonResponse(200, view));
    }
    return base(input as never, init as never);
  });
}

/** A course whose focused (first) lesson shipped a ready video. */
function courseWithVideo() {
  const course = makeCourse();
  course.modules[0]!.lessons[0]!.video = READY_VIDEO;
  return course;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("CourseReader — Watch mode (Cinema)", () => {
  it("offers a Watch mode when the lesson has a ready chaptered video, and plays it", async () => {
    // Arrange
    vi.stubGlobal("fetch", videoFetch());

    // Act
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);

    // Assert — once the video resolves, the top toggle grows a Watch option and (front-door) the
    // chaptered player is on screen.
    await screen.findByRole("navigation", { name: /video chapters/i });
    expect(readerModeToggle().getByRole("radio", { name: /watch/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /how it halves/i })).toBeInTheDocument();
    expect(document.querySelector("video")).not.toBeNull();
  });

  it("offers Watch even with no video, opening on the generate affordance that builds one in place", async () => {
    // Arrange — the default course ships no lesson video → the lifted hook stays idle.
    vi.stubGlobal("fetch", videoFetch());

    // Act — Watch is offered online; the front-door default is Learn (no ready video).
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);
    const watch = await readerModeToggle().findByRole("radio", { name: /watch/i });
    expect(readerModeToggle().getByRole("radio", { name: /learn/i })).toBeChecked();

    // Act — enter Watch: with no video, the surface is the generate affordance.
    fireEvent.click(watch);
    const generate = screen.getByRole("button", { name: /generate video/i });
    expect(generate).toBeInTheDocument();

    // Act — generate: the enqueue is accepted and the built chaptered player takes over in place.
    fireEvent.click(generate);

    // Assert
    expect(await screen.findByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
  });

  it("opens in Watch (front door) when a video is ready and no mode was chosen", async () => {
    // Arrange — no persisted preference; a ready chaptered video exists.
    vi.stubGlobal("fetch", videoFetch());

    // Act — no click: the front-door default should land the learner in Watch.
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);

    // Assert — the Cinema surface is on screen unprompted, and Watch is the selected top-level mode.
    expect(await screen.findByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
    expect(readerModeToggle().getByRole("radio", { name: /watch/i })).toBeChecked();
  });

  it("docks the lesson's key takeaways in the Watch surface", async () => {
    // Arrange — front-door Watch; the takeaways derive from the module's objective.
    vi.stubGlobal("fetch", videoFetch());

    // Act
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);

    // Assert — the takeaways grid, de-scaffolded from "Given a sorted array, locate a target…".
    expect(await screen.findByText(/locate a target with binary search/i)).toBeInTheDocument();
    expect(screen.getByText(/^Takeaway 1$/i)).toBeInTheDocument();
  });

  it("docks the lesson's resources in the Watch surface", async () => {
    // Arrange — front-door Watch; the default lesson carries one curated resource (demonstrate phase).
    vi.stubGlobal("fetch", videoFetch());

    // Act
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);

    // Assert — the curated resource is docked under the video.
    expect(await screen.findByRole("heading", { name: /resources/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /binary search visualised/i })).toBeInTheDocument();
  });

  it("respects a saved Learn preference over the front door", async () => {
    // Arrange — the learner has chosen Learn before; a ready video exists but must not hijack it.
    localStorage.setItem(READER_MODE_KEY, "learn");
    vi.stubGlobal("fetch", videoFetch());

    // Act
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);
    const watch = await screen.findByRole("radio", { name: /watch/i });

    // Assert — Watch is offered but Learn stays selected (no Cinema surface unprompted).
    expect(watch).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /learn/i })).toBeChecked();
    expect(screen.queryByRole("navigation", { name: /video chapters/i })).not.toBeInTheDocument();
  });

  it("migrates a legacy stored Read preference to the front-door default", async () => {
    // Arrange — a browser that persisted the retired "read" mode before this change.
    localStorage.setItem(READER_MODE_KEY, "read");
    vi.stubGlobal("fetch", videoFetch());

    // Act — a video-less lesson: the stale value must degrade to the default, not stick or crash.
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);
    const learn = await readerModeToggle().findByRole("radio", { name: /learn/i });

    // Assert — the front-door default (Learn) is selected; the toggle offers only Learn and Watch.
    expect(learn).toBeChecked();
    expect(readerModeToggle().getByRole("radio", { name: /watch/i })).not.toBeChecked();
    expect(readerModeToggle().getAllByRole("radio")).toHaveLength(2);
  });

  it("keeps a saved Watch preference on a video-less lesson, showing the generate affordance", async () => {
    // Arrange — a persisted Watch preference, but this lesson shipped no video.
    localStorage.setItem(READER_MODE_KEY, "watch");
    vi.stubGlobal("fetch", videoFetch());

    // Act
    render(<CourseReader course={makeCourse()} apiBaseUrl="http://api.test" />);
    const watch = await readerModeToggle().findByRole("radio", { name: /watch/i });

    // Assert — Watch stays selected (it no longer clamps to Learn) and shows the generate CTA; the
    // preference is intact.
    expect(watch).toBeChecked();
    expect(screen.getByRole("button", { name: /generate video/i })).toBeInTheDocument();
    expect(localStorage.getItem(READER_MODE_KEY)).toBe("watch");
  });

  it("persists a Learn choice made from Watch, and honours it on the next visit", async () => {
    // Arrange — front-door Watch (a ready chaptered video exists).
    vi.stubGlobal("fetch", videoFetch());
    const { unmount } = render(
      <CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />,
    );
    await screen.findByRole("navigation", { name: /video chapters/i });

    // Act — choose Learn; the preference is written back.
    fireEvent.click(readerModeToggle().getByRole("radio", { name: /learn/i }));
    expect(localStorage.getItem(READER_MODE_KEY)).toBe("learn");
    unmount();

    // Assert — a fresh reader honours it over the front door, even though the video is ready.
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);
    const learn = await readerModeToggle().findByRole("radio", { name: /learn/i });
    expect(learn).toBeChecked();
    expect(screen.queryByRole("navigation", { name: /video chapters/i })).not.toBeInTheDocument();
  });

  it("a silent video shows chapters + docks but no transcript", async () => {
    // Arrange — a ready, un-narrated video (front-door → Watch).
    vi.stubGlobal("fetch", videoFetch(silentVideoView()));

    // Act
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);

    // Assert — chapters navigate and the docks render, but there is no synced caption overlay.
    expect(await screen.findByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
    expect(screen.getByText(/^Takeaway 1$/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /resources/i })).toBeInTheDocument();
    expect(screen.queryByText(/^transcript$/i)).not.toBeInTheDocument();
  });

  it("plays a pre-Cinema video (no chapters) inside Watch as the plain player", async () => {
    // Arrange — a ready video that predates Cinema (no chapter outline).
    vi.stubGlobal("fetch", videoFetch(preCinemaVideoView()));

    // Act — Watch is offered; the front door stays Learn (no chaptered video), so enter Watch.
    render(<CourseReader course={courseWithVideo()} apiBaseUrl="http://api.test" />);
    fireEvent.click(await readerModeToggle().findByRole("radio", { name: /watch/i }));

    // Assert — the plain player resolves in Watch; there is no chapter rail (no Cinema surface).
    expect(await screen.findByRole("button", { name: /play lesson video/i })).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /video chapters/i })).not.toBeInTheDocument();
  });

  it("offers no Watch offline (no apiBaseUrl), even with a lesson video", async () => {
    // Arrange — an offline reader never reaches the video service, so Watch can't light up.
    vi.stubGlobal("fetch", videoFetch());

    // Act
    render(<CourseReader course={courseWithVideo()} />);
    await screen.findByRole("radio", { name: /learn/i });

    // Assert
    expect(screen.queryByRole("radio", { name: /watch/i })).not.toBeInTheDocument();
  });
});
