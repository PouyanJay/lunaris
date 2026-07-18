import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { CourseCard } from "./CourseCard";
import { makeCourseSummary } from "../../test/fixtures";

// Spy the per-card signed-URL exchange: the whole point of pre-signed thumbs is that the library
// grid NEVER calls it (no "covers pop in one by one" waterfall).
vi.mock("../../lib/coverJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/coverJobs")>();
  return { ...actual, fetchCoverJob: vi.fn(), pollCoverJob: vi.fn() };
});
import { fetchCoverJob, pollCoverJob } from "../../lib/coverJobs";

const fetchJob = vi.mocked(fetchCoverJob);
const pollJob = vi.mocked(pollCoverJob);

const DARK_THUMB = "https://signed/cover.png?width=1280";
const LIGHT_THUMB = "https://signed/cover-light.png?width=1280";

function renderCard(course = makeCourseSummary()) {
  return render(
    <MemoryRouter>
      <CourseCard course={course} />
    </MemoryRouter>,
  );
}

function coverSrc(container: HTMLElement): string | null | undefined {
  return container.querySelector("img")?.getAttribute("src");
}

function setTheme(theme: "light" | "dark"): void {
  document.documentElement.setAttribute("data-theme", theme);
}

beforeEach(() => {
  fetchJob.mockReset();
  pollJob.mockReset();
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  document.documentElement.removeAttribute("data-theme");
});

describe("CourseCard cover from the pre-signed summary thumb", () => {
  it("renders a READY cover straight from the summary thumbUrl, with no per-card fetch", () => {
    const { container } = renderCard(makeCourseSummary({ thumbUrl: DARK_THUMB }));

    // The grid arrives cover-ready: the card shows the pre-signed thumb...
    expect(coverSrc(container)).toBe(DARK_THUMB);
    // ...and never mints its own signed URL (the waterfall this feature removes).
    expect(fetchJob).not.toHaveBeenCalled();
    expect(pollJob).not.toHaveBeenCalled();
  });

  it("shows the light-theme twin in the app's dark theme (inverted mapping)", () => {
    setTheme("dark");
    const { container } = renderCard(
      makeCourseSummary({ thumbUrl: DARK_THUMB, thumbUrlLight: LIGHT_THUMB }),
    );

    // The app's DARK theme shows the LIGHT cover so it pops against the dark chrome.
    expect(coverSrc(container)).toBe(LIGHT_THUMB);
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it("falls back to the dark thumb in dark theme when there is no light twin", () => {
    setTheme("dark");
    const { container } = renderCard(makeCourseSummary({ thumbUrl: DARK_THUMB, thumbUrlLight: null }));

    expect(coverSrc(container)).toBe(DARK_THUMB);
  });

  it("renders the Typographic fallback (no image, no fetch) when there is no cover at all", () => {
    const { container } = renderCard(makeCourseSummary({ topic: "How HTTPS works", cover: null }));

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("HTTPS"); // the Typographic word set
    expect(fetchJob).not.toHaveBeenCalled();
  });
});

describe("CourseCard cover reveal + priority", () => {
  function image(container: HTMLElement): HTMLImageElement {
    const img = container.querySelector("img");
    if (img === null) throw new Error("no cover image rendered");
    return img;
  }

  it("crossfades the cover in only once it has loaded (no empty→image pop)", () => {
    const { container } = renderCard(makeCourseSummary({ thumbUrl: DARK_THUMB }));
    const img = image(container);

    // Before load the image is transparent (the constellation placeholder holds the frame)...
    expect(img.hasAttribute("data-loaded")).toBe(false);
    fireEvent.load(img);
    // ...and fades in once decoded.
    expect(img.hasAttribute("data-loaded")).toBe(true);
  });

  it("loads an above-the-fold cover eagerly at high fetch priority", () => {
    const { container } = renderCard(makeCourseSummary({ thumbUrl: DARK_THUMB }));
    // Default (below the fold) stays lazy.
    expect(image(container).getAttribute("loading")).toBe("lazy");
    cleanup();

    render(
      <MemoryRouter>
        <CourseCard course={makeCourseSummary({ thumbUrl: DARK_THUMB })} priority />
      </MemoryRouter>,
    );
    const img = document.querySelector("img") as HTMLImageElement;
    expect(img.getAttribute("loading")).toBe("eager");
    expect(img.getAttribute("fetchpriority")).toBe("high");
  });
});
