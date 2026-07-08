import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeBriefResponse } from "../../test/fixtures";
import type { BriefResponse, GoalType } from "../../types/clarifier";
import { IdleCourseSetup } from "./IdleCourseSetup";

function stubFetch(response: { ok: boolean; status?: number; json: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

function renderSetup(overrides: Partial<React.ComponentProps<typeof IdleCourseSetup>> = {}) {
  const props: React.ComponentProps<typeof IdleCourseSetup> = {
    apiBaseUrl: "http://test",
    onGenerate: vi.fn(),
    onOpenSettings: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<IdleCourseSetup {...props} />) };
}

afterEach(() => vi.unstubAllGlobals());

describe("IdleCourseSetup", () => {
  it("renders the topic form beside the persistent course-setup rail", () => {
    renderSetup();

    expect(screen.getByRole("heading", { name: /what do you want to learn/i })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: /course setup/i })).toBeInTheDocument();
  });

  it("builds in one click with no personalization and the default options", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    // Default depth (standard), recommended level (no override → undefined), trust switch off.
    expect(onGenerate).toHaveBeenCalledWith({
      topic: "binary search",
      clarification: undefined,
      discoveryDepth: "standard",
      officialOnly: false,
    });
  });

  it("threads the brief plus the options-bar Level override into the build", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
    await screen.findByText(/reach CLB 10/i); // the brief (with its inferred goal_type) is ready

    // The quick Level control (options bar) maps onto the clarifier's target level.
    const level = screen.getByRole("radiogroup", { name: "Level" });
    fireEvent.click(within(level).getByRole("radio", { name: "Advanced" }));
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith({
      topic: "english",
      // The options-bar level overrides the target level; the inferred goal_type (R0) still threads.
      clarification: expect.objectContaining({ targetLevel: "advanced", goalType: "credential" }),
      discoveryDepth: "standard",
      officialOnly: false,
    });
  });

  it("invalidates a loaded brief when the topic changes, so stale answers can't build", async () => {
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
    await screen.findByText(/reach CLB 10/i);

    // Editing the topic drops the brief that was read for the old topic.
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "spanish" } });

    expect(screen.queryByText(/reach CLB 10/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /personalize this topic/i })).toBeInTheDocument();
  });

  it("shows a retryable error when the brief read fails", async () => {
    stubFetch({ ok: false, status: 500, json: async () => ({}) });
    renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));

    // The alert carries the real cause, not just a generic "failed".
    expect(await screen.findByRole("alert")).toHaveTextContent(/http 500/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("keeps the depth control in the options bar available regardless of the brief", async () => {
    // Regression for the reported bug (the depth control must never vanish): it now lives in the
    // always-visible options bar, so loading the brief can't drop it.
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    renderSetup();

    const depth = screen.getByRole("radiogroup", { name: "Depth" });
    expect(within(depth).getByRole("radio", { name: "Standard" })).toBeInTheDocument();
    expect(within(depth).getByRole("radio", { name: "Thorough" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
    await screen.findByText(/reach CLB 10/i);

    // Still present after the brief renders.
    expect(within(depth).getByRole("radio", { name: "Thorough" })).toBeInTheDocument();
  });

  it("threads the chosen Thorough depth into the build", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    const depth = screen.getByRole("radiogroup", { name: "Depth" });
    fireEvent.click(within(depth).getByRole("radio", { name: "Thorough" }));
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith({
      topic: "binary search",
      clarification: undefined,
      discoveryDepth: "thorough",
      officialOnly: false,
    });
  });

  it("threads the Official-sources-only switch into the build", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("switch", { name: /official sources only/i }));
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith({
      topic: "binary search",
      clarification: undefined,
      discoveryDepth: "standard",
      officialOnly: true,
    });
  });

  it("opens Settings from the operator pointer", () => {
    const onOpenSettings = vi.fn();
    renderSetup({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: /open settings/i }));

    expect(onOpenSettings).toHaveBeenCalledOnce();
  });

  it("collapses the rail to an edge tab and expands it again", () => {
    renderSetup();

    fireEvent.click(screen.getByRole("button", { name: /collapse course setup/i }));
    const reveal = screen.getByRole("button", { name: /show course setup/i });
    expect(reveal).toBeInTheDocument();

    fireEvent.click(reveal);
    expect(screen.queryByRole("button", { name: /show course setup/i })).not.toBeInTheDocument();
  });

  it("aborts an in-flight brief read when unmounted", () => {
    let captured: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: unknown, init?: RequestInit) => {
        captured = init?.signal ?? undefined;
        return new Promise<never>(() => {}); // never settles — the read is in-flight
      }),
    );
    const { unmount } = renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
    expect(captured?.aborted).toBe(false);

    unmount();
    expect(captured?.aborted).toBe(true);
  });

  it("opens the setup drawer, closes it on Escape, and returns focus to the toggle", () => {
    renderSetup();
    const toggle = screen.getByRole("button", { name: /^course setup$/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: /close course setup overlay/i })).toBeInTheDocument();

    // Esc dismisses the drawer (WCAG 2.2) and restores focus to the control that opened it.
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveFocus();
  });

  it("closes the setup drawer when the scrim is clicked", () => {
    renderSetup();
    const toggle = screen.getByRole("button", { name: /^course setup$/i });

    fireEvent.click(toggle);
    fireEvent.click(screen.getByRole("button", { name: /close course setup overlay/i }));

    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      screen.queryByRole("button", { name: /close course setup overlay/i }),
    ).not.toBeInTheDocument();
  });
});

// The journey's final task: parametrize the threading over goal types (the Genericity Rule — the
// rail must be goal-type-blind, never wired to one outcome shape) and the depth override.
describe("IdleCourseSetup — variant coverage across goal types", () => {
  afterEach(() => vi.unstubAllGlobals());

  /** A brief whose goal-type clarifier recommends `goalType` (so the inference pre-picks it).
   *  Built immutably so it never mutates the fixture, even if `makeBriefResponse` later shares state. */
  function briefForGoal(goalType: GoalType): BriefResponse {
    const base = makeBriefResponse();
    return {
      brief: { ...base.brief, goalType },
      clarifier: {
        questions: base.clarifier.questions.map((question) =>
          question.id === "goal"
            ? {
                ...question,
                options: question.options.map((option) => ({
                  ...option,
                  recommended: option.value === goalType,
                })),
              }
            : question,
        ),
      },
    };
  }

  const GOAL_TYPES: GoalType[] = ["knowledge", "skill", "credential", "behavior"];

  it.each(GOAL_TYPES)(
    "threads the inferred goal_type '%s' and the Thorough depth override into the build",
    async (goalType) => {
      stubFetch({ ok: true, json: async () => briefForGoal(goalType) });
      const onGenerate = vi.fn();
      renderSetup({ onGenerate });

      fireEvent.change(screen.getByLabelText("Topic"), { target: { value: `topic-${goalType}` } });
      fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
      // The fixture always carries the "CLB 10" goal text; the variant covers the inferred GOAL
      // option (goal_type), not the goal prose — this just waits for the ready brief to render.
      await screen.findByText(/reach CLB 10/i);

      // Override the smart default depth (options bar), then build with the confirmed goal type.
      const depth = screen.getByRole("radiogroup", { name: "Depth" });
      fireEvent.click(within(depth).getByRole("radio", { name: "Thorough" }));
      fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

      expect(onGenerate).toHaveBeenCalledWith({
        topic: `topic-${goalType}`,
        clarification: expect.objectContaining({ goalType }),
        discoveryDepth: "thorough",
        officialOnly: false,
      });
    },
  );
});
