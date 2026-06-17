import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VideosGeneratingPanel } from "./VideosGeneratingPanel";

describe("VideosGeneratingPanel", () => {
  it("shows N of M ready on a determinate progress bar", () => {
    render(
      <VideosGeneratingPanel
        progress={{ total: 8, ready: 3, failed: 0, settled: false }}
        onOpenCourse={() => {}}
      />,
    );

    const bar = screen.getByRole("progressbar", { name: /generating videos/i });
    expect(bar.getAttribute("aria-valuenow")).toBe("3");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("8");
    expect(screen.getByText(/3\s*\/\s*8/)).toBeInTheDocument();
  });

  it("notes failed videos honestly with a recovery hint", () => {
    render(
      <VideosGeneratingPanel
        progress={{ total: 8, ready: 5, failed: 1, settled: false }}
        onOpenCourse={() => {}}
      />,
    );

    expect(screen.getByText(/1 couldn.t generate/i)).toBeInTheDocument();
  });

  it("lets the user open the course without waiting", () => {
    const onOpen = vi.fn();
    render(
      <VideosGeneratingPanel
        progress={{ total: 8, ready: 3, failed: 0, settled: false }}
        onOpenCourse={onOpen}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /open course/i }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("shows a loading affordance before the first reading lands", () => {
    render(<VideosGeneratingPanel progress={null} onOpenCourse={() => {}} />);

    // No progressbar yet, but the panel announces it is working and still offers the escape.
    expect(screen.getByText(/finishing up your videos/i)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByRole("button", { name: /open course/i })).toBeInTheDocument();
  });
});
