import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveActivity } from "./LiveActivity";

describe("LiveActivity", () => {
  beforeEach(() => vi.useFakeTimers());
  // Restore real timers only — the component's own cleanup clears its intervals on unmount, so
  // flushing pending timers here would fire a post-unmount state update (an act warning).
  afterEach(() => vi.useRealTimers());

  it("shows a phase-appropriate verb beside the branded spinner", () => {
    render(<LiveActivity phaseKey="graph_built" />);

    expect(screen.getByTestId("lunar-spinner")).toBeInTheDocument();
    expect(screen.getByText("Mapping prerequisites…")).toBeInTheDocument();
  });

  it("cycles through the phase's verbs over time", () => {
    render(<LiveActivity phaseKey="graph_built" />);

    expect(screen.getByText("Mapping prerequisites…")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(2400));
    expect(screen.getByText("Ordering concepts…")).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(2400));
    expect(screen.getByText("Untangling dependencies…")).toBeInTheDocument();
  });

  it("uses the intro verbs for the pre-stage intro node", () => {
    render(<LiveActivity phaseKey="intro" />);

    expect(screen.getByText("Planning the build…")).toBeInTheDocument();
  });

  it("falls back to generic verbs for an unrecognised phase key", () => {
    render(<LiveActivity phaseKey="something_unmapped" />);

    expect(screen.getByText("Working…")).toBeInTheDocument();
  });

  it("shows a live elapsed clock (m:ss) when a start time is given", () => {
    // 75s ago → 1:15. Fake timers freeze Date.now(), so the diff is exact.
    render(<LiveActivity phaseKey="graph_built" startedAt={Date.now() - 75_000} />);

    expect(screen.getByText("1:15")).toBeInTheDocument();
  });

  it("omits the clock when no start time is provided", () => {
    render(<LiveActivity phaseKey="graph_built" />);

    // No "m:ss" clock anywhere — only the verb + spinner.
    expect(screen.queryByText(/^\d+:\d{2}$/)).not.toBeInTheDocument();
  });
});
