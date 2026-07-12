import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CourseCoverImage } from "./CourseCoverImage";
import type { CoverArtifact } from "../../types/course";

vi.mock("../../lib/coverJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/coverJobs")>();
  return { ...actual, fetchCoverJob: vi.fn(), pollCoverJob: vi.fn() };
});
import { fetchCoverJob, type CoverJobView } from "../../lib/coverJobs";

const fetchJob = vi.mocked(fetchCoverJob);
const API = "http://api.test";

const DARK = "https://signed/cover.png";
const LIGHT = "https://signed/cover-light.png";
const DARK_THUMB = "https://signed/cover.png?width=1280";
const LIGHT_THUMB = "https://signed/cover-light.png?width=1280";

/** A READY view carrying each variant's master AND its storage-resized derivative — what the API
 *  now returns. The frames render the derivative; only the lightbox loads the master. */
function readyView(imageUrlLight: string | null = null): CoverJobView {
  return {
    job: { id: "job-1", courseId: "c1", status: "ready", stylePreset: "nocturne", error: null },
    imageUrl: DARK,
    imageUrlLight,
    thumbUrl: DARK_THUMB,
    thumbUrlLight: imageUrlLight === null ? null : LIGHT_THUMB,
    provenance: null,
  };
}

/** A cover minted before derivatives existed (or storage that cannot resize): masters only. */
function masterOnlyView(imageUrlLight: string | null = null): CoverJobView {
  return { ...readyView(imageUrlLight), thumbUrl: null, thumbUrlLight: null };
}

function srcOf(container: HTMLElement): string | null | undefined {
  return container.querySelector("img")?.getAttribute("src");
}

/** The rendered cover image, or a failure — so an error can be fired at it without a null check. */
function imageIn(container: HTMLElement): HTMLImageElement {
  const img = container.querySelector("img");
  if (img === null) throw new Error("no cover image rendered");
  return img;
}

const READY_COVER: CoverArtifact = { status: "ready", jobId: "job-1", provenance: null };

function setTheme(theme: "light" | "dark"): void {
  document.documentElement.setAttribute("data-theme", theme);
}

beforeEach(() => fetchJob.mockReset());
afterEach(() => {
  // Unmount before clearing the theme attribute so useThemeValue's observer can't fire outside act.
  cleanup();
  vi.clearAllMocks();
  document.documentElement.removeAttribute("data-theme");
});

describe("CourseCoverImage precedence", () => {
  it("renders the Typographic fallback when there is no cover", () => {
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="How HTTPS works" cover={null} apiBaseUrl={API} />,
    );
    expect(container.textContent).toContain("HTTPS"); // the Typographic word
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders the AI image once a READY cover's signed URL resolves", async () => {
    fetchJob.mockResolvedValue(readyView());
    const cover: CoverArtifact = { status: "ready", jobId: "job-1", provenance: null };
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="How HTTPS works" cover={cover} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));
  });

  it("renders the Typographic fallback for a FAILED cover (never a broken image)", async () => {
    const cover: CoverArtifact = { status: "failed", jobId: "job-1", provenance: null };
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="Networking basics" cover={cover} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(container.textContent).toContain("Networking"));
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("CourseCoverImage theme-aware selection (inverted / contrast)", () => {
  it("shows the DARK image in the app's LIGHT theme", async () => {
    setTheme("light");
    fetchJob.mockResolvedValue(readyView("https://signed/cover-light.png"));
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));
  });

  it("shows the LIGHT image in the app's DARK theme", async () => {
    setTheme("dark");
    fetchJob.mockResolvedValue(readyView("https://signed/cover-light.png"));
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(LIGHT_THUMB));
  });

  it("falls back to the DARK image in DARK theme when there is no light twin (old cover)", async () => {
    setTheme("dark");
    fetchJob.mockResolvedValue(readyView(null)); // a dark-only / pre-dual-theme cover
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));
  });

  it("degrades to the Typographic fallback when every image URL fails to load", async () => {
    setTheme("light");
    fetchJob.mockResolvedValue(readyView(LIGHT));
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="Broken" cover={READY_COVER} apiBaseUrl={API} />,
    );

    // Rung 1 (the derivative) 404s → the ladder tries the master rather than giving up.
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));
    fireEvent.error(imageIn(container));
    await waitFor(() => expect(srcOf(container)).toBe(DARK));

    // Rung 2 (the master) 404s too — the signed URL expired or the object was purged. Only NOW does
    // it give up, and it gives up to the Typographic cover, never to a broken image.
    fireEvent.error(imageIn(container));
    await waitFor(() => {
      expect(container.querySelector("img")).toBeNull();
      expect(container.textContent).toContain("Broken"); // the Typographic word
    });
  });

  it("swaps the image live when the theme is toggled", async () => {
    setTheme("light");
    fetchJob.mockResolvedValue(readyView(LIGHT));
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));

    act(() => setTheme("dark"));
    await waitFor(() => expect(srcOf(container)).toBe(LIGHT_THUMB));
  });
});

describe("CourseCoverImage load ladder (derivative → master → Typographic)", () => {
  it("loads the storage-resized derivative, NOT the 2048px master", async () => {
    // The whole point: a card frame is ~260px wide. Handing it the master and letting the browser
    // shrink it is what made card covers look soft — and shipped ~3.5MB per card.
    fetchJob.mockResolvedValue(readyView());
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );

    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));
    expect(srcOf(container)).not.toBe(DARK);
  });

  it("loads the master when a cover has no derivative (an older cover)", async () => {
    // Covers minted before derivatives existed must keep rendering — at the master, not at nothing.
    fetchJob.mockResolvedValue(masterOnlyView());
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );

    await waitFor(() => expect(srcOf(container)).toBe(DARK));
  });

  it("reaches the Typographic fallback when a cover with NO derivative fails to load", async () => {
    // Regression: with no derivative, the thumb selector falls back to the master, so both rungs are
    // the SAME url. Un-deduped, the ladder would "advance" to an identical src — React would reuse
    // the <img> (same key), the browser would never retry, no second error would fire, and the frame
    // would sit on a broken image forever instead of ever reaching the Typographic cover.
    fetchJob.mockResolvedValue(masterOnlyView());
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="Broken" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK));

    fireEvent.error(imageIn(container)); // the one and only URL 404s

    await waitFor(() => {
      expect(container.querySelector("img")).toBeNull();
      expect(container.textContent).toContain("Broken"); // the Typographic word
    });
  });

  it("falls back to the master when the derivative cannot be served", async () => {
    // Storage without image transformations answers the derivative URL with an error. The cover must
    // still appear — degraded in sharpness, not missing.
    fetchJob.mockResolvedValue(readyView());
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));

    fireEvent.error(imageIn(container));

    await waitFor(() => expect(srcOf(container)).toBe(DARK));
  });

  it("re-enters at the derivative when the theme swaps to the other variant", async () => {
    // A failure on one variant must not strand the OTHER variant on its master: toggling the theme
    // picks a different artwork, so the ladder starts over at the top for it.
    setTheme("light");
    fetchJob.mockResolvedValue(readyView(LIGHT));
    const { container } = render(
      <CourseCoverImage courseId="c1" topic="t" cover={READY_COVER} apiBaseUrl={API} />,
    );
    await waitFor(() => expect(srcOf(container)).toBe(DARK_THUMB));
    fireEvent.error(imageIn(container)); // the dark derivative fails → the dark master
    await waitFor(() => expect(srcOf(container)).toBe(DARK));

    act(() => setTheme("dark"));

    await waitFor(() => expect(srcOf(container)).toBe(LIGHT_THUMB));
  });
});
