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

  it("only ever moves the bar forward as the job advances through its stages", () => {
    const { rerender } = render(<VideoProgress status="planning" label="x" />);
    const at = (status: Parameters<typeof VideoProgress>[0]["status"]) => {
      rerender(<VideoProgress status={status} label="x" />);
      return Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"));
    };

    // planning → rendering → assembling rises monotonically, ending below the terminal 100.
    const planning = at("planning");
    const rendering = at("rendering");
    const assembling = at("assembling");
    expect(rendering).toBeGreaterThan(planning);
    expect(assembling).toBeGreaterThan(rendering);
    expect(assembling).toBeLessThan(100);
  });
});
