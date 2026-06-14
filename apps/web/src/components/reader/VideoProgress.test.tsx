import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VideoProgress } from "./VideoProgress";

describe("VideoProgress", () => {
  it("exposes a labelled determinate progressbar with the stage caption", () => {
    render(<VideoProgress status="rendering" label="Generating the course trailer" />);

    const bar = screen.getByRole("progressbar", { name: /generating the course trailer/i });
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeGreaterThan(0);
    // The plain-language stage caption is shown to sighted users too.
    expect(screen.getByText(/rendering the scenes/i)).toBeInTheDocument();
  });

  it("only ever moves the bar forward across the full stage chain", () => {
    const { rerender } = render(<VideoProgress status="queued" label="x" />);
    const at = (status: Parameters<typeof VideoProgress>[0]["status"]) => {
      rerender(<VideoProgress status={status} label="x" />);
      return Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"));
    };

    // Every in-flight stage rises monotonically (no two equal, no regression), ending below the
    // terminal 100 — so the bar never stalls or jumps backward whatever order stages arrive in.
    const percents = (
      ["queued", "planning", "coding", "voicing", "rendering", "qa", "assembling"] as const
    ).map(at);
    percents.reduce((prev, cur) => {
      expect(cur).toBeGreaterThan(prev);
      return cur;
    });
    expect(Math.max(...percents)).toBeLessThan(100);
    expect(at("ready")).toBe(100);
  });
});
