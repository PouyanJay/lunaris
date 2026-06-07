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
            credibility: 0.82,
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
    expect(screen.getByText("82%")).toBeInTheDocument();
  });

  it("plays a YouTube link in-reader even when its kind is mislabeled 'article'", () => {
    // The curator can mislabel a youtube.com link as an article; the reader must still recognise the
    // URL as a video — a play affordance, not a READ card — and surface "video" as the kind word.
    render(
      <LessonResources
        resources={[
          makeResource({
            kind: "article",
            title: "Editing for register and tone",
            url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            source: "youtube.com",
            duration: null,
          }),
        ]}
      />,
    );

    expect(
      screen.getByRole("button", { name: /play video: editing for register and tone/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("video")).toBeInTheDocument();
    expect(screen.queryByText("article")).not.toBeInTheDocument();
  });

  it("recognises a youtu.be short link as a video even when mislabeled 'docs'", () => {
    render(
      <LessonResources
        resources={[
          makeResource({
            kind: "docs",
            title: "Register and tone, short",
            url: "https://youtu.be/dQw4w9WgXcQ",
            source: "youtu.be",
            duration: null,
          }),
        ]}
      />,
    );

    expect(
      screen.getByRole("button", { name: /play video: register and tone, short/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("video")).toBeInTheDocument();
    expect(screen.queryByText("docs")).not.toBeInTheDocument();
  });

  it("leaves a genuine non-YouTube article as a READ card with its kind word", () => {
    render(
      <LessonResources
        resources={[
          makeResource({
            kind: "article",
            title: "Reading stance",
            url: "https://example.edu/stance",
            source: "example.edu",
            duration: null,
          }),
        ]}
      />,
    );

    // No play button — it is a real article, shown as its authored kind.
    expect(screen.queryByRole("button", { name: /play video/i })).not.toBeInTheDocument();
    expect(screen.getByText("article")).toBeInTheDocument();
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
