import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Resource } from "../../types/course";
import { ChapterResourceCard } from "./ChapterResourceCard";

const resource: Resource = {
  kind: "article",
  title: "The TLS handshake explained",
  url: "https://baeldung.com/tls-handshake",
  source: "baeldung.com",
  why: "Walks the handshake step by step.",
  trustTier: "reputable",
  credibility: 0.9,
  fetchedAt: "2026-07-21T00:00:00Z",
  duration: null,
  author: null,
};

describe("ChapterResourceCard", () => {
  it("marks the row with a kind glyph and links out to the source", () => {
    render(<ChapterResourceCard scored={{ resource, rel: 35 }} />);

    const link = screen.getByRole("link", { name: /the tls handshake explained/i });
    expect(link).toHaveAttribute("href", "https://baeldung.com/tls-handshake");
    expect(link).toHaveAttribute("target", "_blank");

    // An article reads as READ; the glyph is decorative (aria-hidden), so it isn't in the link name.
    expect(screen.getByText("READ")).toBeInTheDocument();
    expect(screen.getByText(/baeldung\.com/)).toBeInTheDocument();
    expect(screen.getByText(/REL 35%/)).toBeInTheDocument();
  });

  it("uses the kind-specific glyph (video → VIDEO)", () => {
    render(<ChapterResourceCard scored={{ resource: { ...resource, kind: "video" }, rel: 50 }} />);
    expect(screen.getByText("VIDEO")).toBeInTheDocument();
  });
});
