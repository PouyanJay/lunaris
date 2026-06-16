import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DegradedScene } from "../../types/course";
import { DegradedBadge } from "./DegradedBadge";

const scene = (sceneId: string, issues: string[]): DegradedScene => ({ sceneId, issues });

describe("DegradedBadge", () => {
  it("renders nothing when no scenes are degraded", () => {
    const { container } = render(<DegradedBadge scenes={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows a singular count and the issue on hover for one degraded scene", () => {
    render(<DegradedBadge scenes={[scene("S1_hook", ["title overflows the frame"])]} />);

    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("1 scene degraded");
    expect(badge).toHaveAttribute("title", "title overflows the frame");
  });

  it("pluralizes the count and lists every issue in the title", () => {
    render(
      <DegradedBadge
        scenes={[
          scene("S1_hook", ["title overflows the frame"]),
          scene("S2_mechanism", ["states a figure no cited source verifies: 80"]),
        ]}
      />,
    );

    const badge = screen.getByRole("status");
    expect(badge).toHaveTextContent("2 scenes degraded");
    const title = badge.getAttribute("title") ?? "";
    expect(title).toContain("title overflows the frame");
    expect(title).toContain("states a figure no cited source verifies: 80");
  });

  it("de-duplicates an issue repeated across scenes in the title", () => {
    render(
      <DegradedBadge
        scenes={[
          scene("S1_hook", ["narration not fully in sync (beat b2)"]),
          scene("S2_mechanism", ["narration not fully in sync (beat b2)"]),
        ]}
      />,
    );

    expect(screen.getByRole("status").getAttribute("title")).toBe(
      "narration not fully in sync (beat b2)",
    );
  });
});
