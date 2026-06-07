import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeBriefResponse } from "../../test/fixtures";
import { recommendedAnswers } from "../../lib/clarification";
import type { BriefLoadState } from "../../types/clarifier";
import { ConfigRail } from "./ConfigRail";

/** Render ConfigRail with sensible defaults; override any prop per test. */
function renderRail(overrides: Partial<React.ComponentProps<typeof ConfigRail>> = {}) {
  const props: React.ComponentProps<typeof ConfigRail> = {
    topic: "english",
    brief: { status: "blank" },
    onLoadBrief: vi.fn(),
    onAnswerChange: vi.fn(),
    depth: "standard",
    onDepthChange: vi.fn(),
    onOpenSettings: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<ConfigRail {...props} />) };
}

const ready = (): BriefLoadState => ({
  status: "ready",
  data: makeBriefResponse(),
  answers: recommendedAnswers(makeBriefResponse().clarifier),
});

describe("ConfigRail", () => {
  it("renders the three tiers: personalize (learner), advanced (build), operator", () => {
    renderRail();

    expect(screen.getByRole("heading", { name: /for you/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /advanced/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open settings/i })).toBeInTheDocument();
  });

  it("prompts for a topic before personalizing when none is entered", () => {
    renderRail({ topic: "" });

    expect(screen.getByText(/name a topic/i)).toBeInTheDocument();
    // No personalize trigger with nothing to personalize.
    expect(screen.queryByRole("button", { name: /personalize this topic/i })).not.toBeInTheDocument();
  });

  it("offers to personalize the entered topic, loading the brief on demand", () => {
    const onLoadBrief = vi.fn();
    renderRail({ topic: "english", brief: { status: "blank" }, onLoadBrief });

    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));

    expect(onLoadBrief).toHaveBeenCalledOnce();
  });

  it("shows a loading status while the brief is read", () => {
    renderRail({ brief: { status: "loading" } });

    expect(screen.getByRole("status")).toHaveTextContent(/reading your goal/i);
  });

  it("shows a retryable error when the brief fails", () => {
    const onLoadBrief = vi.fn();
    renderRail({ brief: { status: "error", message: "We couldn't read your goal." }, onLoadBrief });

    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't read your goal/i);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onLoadBrief).toHaveBeenCalledOnce();
  });

  it("renders the clarifier fields once the brief is ready and reports edits", () => {
    const onAnswerChange = vi.fn();
    renderRail({ brief: ready(), onAnswerChange });

    // The inferred goal summary + a clarifier choice (level), with the inference pre-picked.
    expect(screen.getByText(/reach CLB 10/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /intermediate/i })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /advanced/i }));
    expect(onAnswerChange).toHaveBeenCalledWith("level", "advanced");
  });

  it("renders the goal-type clarifier first, pre-picking the inferred outcome (R0)", () => {
    const onAnswerChange = vi.fn();
    renderRail({ brief: ready(), onAnswerChange });

    // goal_type is a learner-tier clarifier field: the inferred outcome is pre-selected…
    expect(screen.getByRole("radio", { name: /pass a credential/i })).toBeChecked();
    // …and changing it reports the new goal value up for the build.
    fireEvent.click(screen.getByRole("radio", { name: /build a skill/i }));
    expect(onAnswerChange).toHaveBeenCalledWith("goal", "skill");
  });

  it("keeps the rail present even when no topic is entered yet", () => {
    renderRail({ topic: "" });

    // A regression that drops the rail in the blank state would be caught here.
    expect(screen.getByRole("complementary", { name: /course setup/i })).toBeInTheDocument();
  });

  it("keeps the Advanced (build) section present once the brief is ready", () => {
    // Regression: the search-depth control must survive the brief loading — a learner who
    // personalizes their topic must not lose the Standard/Thorough choice.
    renderRail({ brief: ready() });

    const advanced = screen.getByRole("button", { name: /advanced/i });
    expect(advanced).toBeInTheDocument();
    fireEvent.click(advanced);
    expect(screen.getByRole("radio", { name: /standard/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /thorough/i })).toBeInTheDocument();
  });

  it("exposes the search depth in the Advanced section and reports a change", () => {
    const onDepthChange = vi.fn();
    renderRail({ depth: "standard", onDepthChange });

    // Build controls live behind the Advanced disclosure (collapsed by default).
    fireEvent.click(screen.getByRole("button", { name: /advanced/i }));
    expect(screen.getByRole("radio", { name: /standard/i })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /thorough/i }));
    expect(onDepthChange).toHaveBeenCalledWith("thorough");
  });

  it("points operators to Settings instead of duplicating admin controls", () => {
    const onOpenSettings = vi.fn();
    renderRail({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: /open settings/i }));
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });

  it("collapses on the wide-screen control and closes the narrow drawer", () => {
    const onCollapse = vi.fn();
    const onClose = vi.fn();
    renderRail({ onCollapse, onClose });

    fireEvent.click(screen.getByRole("button", { name: /collapse course setup/i }));
    expect(onCollapse).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: /close course setup/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
