import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeResource } from "../../test/fixtures";
import { LessonResources } from "./LessonResources";

describe("LessonResources", () => {
  it("renders each resource as a safe out-bound link with its kind, source, and trust", () => {
    // Arrange / Act
    render(
      <LessonResources
        resources={[
          makeResource({
            kind: "article",
            title: "Reading authorial stance",
            url: "https://example.edu/stance",
            source: "example.edu",
            trustTier: "reputable",
            duration: null,
          }),
        ]}
      />,
    );

    // Assert — a named region, a new-tab link with rel=noopener, the source domain + trust word.
    expect(screen.getByRole("region", { name: "Resources" })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Reading authorial stance" });
    expect(link).toHaveAttribute("href", "https://example.edu/stance");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
    expect(screen.getByText("article")).toBeInTheDocument();
    expect(screen.getByText("example.edu")).toBeInTheDocument();
    // Trust tier is shown in the word, not colour alone (WCAG: never colour as the sole signal).
    expect(screen.getByText("reputable")).toBeInTheDocument();
  });

  it("shows a video's runtime and omits it for non-video resources", () => {
    // Arrange / Act — a video (with duration) and an article (without).
    const { rerender } = render(
      <LessonResources resources={[makeResource({ duration: "6:12" })]} />,
    );
    expect(screen.getByText("6:12")).toBeInTheDocument();

    rerender(<LessonResources resources={[makeResource({ kind: "docs", duration: null })]} />);
    expect(screen.queryByText("6:12")).not.toBeInTheDocument();
  });
});
