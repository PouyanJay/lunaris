import { render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it } from "vitest";

import { makeResource } from "../../test/fixtures";
import { WatchSurface } from "./WatchSurface";

const VIDEO = {
  videoUrl: "https://signed.example/final.mp4",
  posterUrl: null,
  captionsUrl: null,
  chapters: [{ id: "S1_intro", title: "Intro", startS: 0, endS: 10 }],
  transcript: [],
  label: "Binary Search — lesson video",
};

function renderSurface(overrides: Partial<ComponentProps<typeof WatchSurface>> = {}) {
  return render(<WatchSurface {...VIDEO} takeaways={[]} resources={[]} {...overrides} />);
}

describe("WatchSurface", () => {
  it("renders the chaptered player", () => {
    // Arrange / Act
    renderSurface();

    // Assert
    expect(screen.getByRole("navigation", { name: /video chapters/i })).toBeInTheDocument();
    expect(document.querySelector("video")).not.toBeNull();
  });

  it("docks the lesson's key takeaways when present", () => {
    // Arrange / Act
    renderSurface({ takeaways: ["Locate a target with binary search."] });

    // Assert — the takeaways grid (labelled columns) carries the line.
    expect(screen.getByText(/^Takeaway 1$/i)).toBeInTheDocument();
    expect(screen.getByText(/locate a target with binary search/i)).toBeInTheDocument();
  });

  it("omits the takeaways section when there are none", () => {
    // Arrange / Act
    renderSurface();

    // Assert
    expect(screen.queryByText(/^Takeaway 1$/i)).not.toBeInTheDocument();
  });

  it("docks the lesson's resources when present", () => {
    // Arrange / Act — a resource that matches no chapter falls back to the lesson-level dock.
    renderSurface({ resources: [makeResource({ title: "Binary search visualised" })] });

    // Assert
    expect(screen.getByRole("heading", { name: /resources/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /binary search visualised/i })).toBeInTheDocument();
  });

  it("omits the resources section when there are none", () => {
    // Arrange / Act
    renderSurface();

    // Assert
    expect(screen.queryByRole("heading", { name: /resources/i })).not.toBeInTheDocument();
  });

  it("docks a matching resource under its chapter in the rail, with a relevance score", () => {
    // Arrange — a chapter whose key terms the resource covers.
    renderSurface({
      chapters: [
        { id: "S2", title: "Self-similarity", startS: 0, endS: 10, keyTerms: ["koch curve"] },
      ],
      resources: [
        makeResource({
          title: "Koch curve explained",
          why: "the koch curve fractal",
          source: "youtube.com",
          duration: "5:22",
        }),
      ],
    });

    // Assert — the resource is docked inside the chapters rail with a REL score, not in a separate
    // lesson-level Resources block.
    const rail = screen.getByRole("navigation", { name: /video chapters/i });
    expect(within(rail).getByRole("link", { name: /koch curve explained/i })).toBeInTheDocument();
    expect(within(rail).getByText(/REL \d+%/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /resources/i })).not.toBeInTheDocument();
  });

  it("shows the docks unconditionally — there is no Watch/Both/Read sub-control", () => {
    // Arrange / Act — the player, its chapter rail, and the lesson docks are all present at once.
    renderSurface({
      takeaways: ["Locate a target with binary search."],
      resources: [makeResource({ title: "Binary search visualised" })],
    });

    // Assert — docks show, and no consumption radiogroup toggles them.
    expect(screen.getByText(/^Takeaway 1$/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /resources/i })).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Both" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Read" })).not.toBeInTheDocument();
  });
});
