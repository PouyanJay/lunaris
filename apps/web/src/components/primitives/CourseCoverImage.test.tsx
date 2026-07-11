import { render, waitFor } from "@testing-library/react";
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

function readyView(): CoverJobView {
  return {
    job: { id: "job-1", courseId: "c1", status: "ready", stylePreset: "nocturne", error: null },
    imageUrl: "https://signed/cover.png",
    provenance: null,
  };
}

beforeEach(() => fetchJob.mockReset());
afterEach(() => vi.clearAllMocks());

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
    await waitFor(() => {
      const img = container.querySelector("img");
      expect(img?.getAttribute("src")).toBe("https://signed/cover.png");
    });
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
