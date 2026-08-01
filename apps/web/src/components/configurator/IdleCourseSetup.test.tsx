import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeBriefResponse } from "../../test/fixtures";
import type { BriefResponse, GoalType } from "../../types/clarifier";
import { IdleCourseSetup } from "./IdleCourseSetup";

/** Open the composer's Personalize panel. The brief used to sit permanently in the rail; it is a
 *  chip in the settings bar now, so the panel has to be opened before its contents exist. */
function openPersonalize() {
  // Idempotent: clicking the chip while the panel is already open would close it. The chip reads
  // "Personalize" until a brief is read, then "For you Tailored".
  const chip = screen.queryByRole("button", { name: /^personalize$|tailored/i });
  if (chip && chip.getAttribute("aria-expanded") !== "true") fireEvent.click(chip);
}

/** Open the panel AND read the brief. Separate from opening, because a test that wants to see the
 *  offer to personalize must not have it clicked out from under it. */
function readBrief() {
  openPersonalize();
  fireEvent.click(screen.getByRole("button", { name: /personalize this topic/i }));
}

/** Pick a value from one of the composer's setting menus. The controls became menus in the
 *  composer rebuild; the guarantees they are asserted against are unchanged. */
function pickSetting(setting: string, option: RegExp) {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(setting, "i") }));
  fireEvent.click(
    within(screen.getByRole("menu", { name: setting })).getByRole("menuitemradio", {
      name: option,
    }),
  );
}

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
  it("renders the topic form with every setting docked inside its box", () => {
    renderSetup();

    // The rail is gone: Depth, Level, Sources and Personalize all live in the composer now.
    expect(screen.getByLabelText("Topic")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /depth/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^personalize$/i })).toBeInTheDocument();
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
    readBrief();
    await screen.findByText(/reach CLB 10/i); // the brief (with its inferred goal_type) is ready

    // The quick Level control (options bar) maps onto the clarifier's target level.
    pickSetting("Level", /advanced/i);
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
    readBrief();
    await screen.findByText(/reach CLB 10/i);

    // Editing the topic drops the brief that was read for the old topic.
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "spanish" } });

    expect(screen.queryByText(/reach CLB 10/i)).not.toBeInTheDocument();
    // The offer to personalize is back, which is what "the brief was dropped" means to a user.
    openPersonalize();
    expect(screen.getByRole("button", { name: /personalize this topic/i })).toBeInTheDocument();
  });

  it("says on the chip whether the build is tailored, without opening the panel", async () => {
    // The bar has to carry the state. Otherwise the only way to know whether a brief is threading
    // is to open the panel and look, which defeats having a bar at all.
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    renderSetup();

    expect(screen.getByRole("button", { name: /^personalize$/i })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    readBrief();
    await screen.findByText(/reach CLB 10/i);

    expect(screen.getByRole("button", { name: /tailored/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^personalize$/i })).not.toBeInTheDocument();
  });

  it("does not offer to personalize before there is a topic to read", () => {
    // The brief is interpreted FROM the topic, so offering to read one with the field empty would
    // promise something the system cannot do.
    renderSetup();

    openPersonalize();

    expect(screen.getByText(/name a topic first/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /personalize this topic/i }),
    ).not.toBeInTheDocument();
  });

  it("threads a CHANGED clarifier answer into the build, not just the inferred one", async () => {
    // The inferred answers are covered by the variant suite. This covers the other half: actually
    // editing an answer and having the edit reach the build. Without it, gutting the change handler
    // is invisible, because every test would still pass on the pre-picked values.
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    readBrief();
    await screen.findByText(/reach CLB 10/i);

    // The fixture pre-picks "Pass a credential"; choose a different outcome.
    fireEvent.click(screen.getByRole("radio", { name: "Build a skill" }));
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith(
      expect.objectContaining({
        clarification: expect.objectContaining({ goalType: "skill" }),
      }),
    );
  });

  it("leaves Level out of the panel, because the Level chip owns it", async () => {
    // Two level pickers is a bug rather than a convenience: they would disagree.
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    readBrief();
    await screen.findByText(/reach CLB 10/i);

    const panel = screen.getByRole("dialog", { name: /for you/i });
    // The LEVEL clarifier question, by its actual prompt: it must not be rendered here.
    expect(within(panel).queryByText(/current level with this/i)).not.toBeInTheDocument();
    // The other questions from the same brief are present, so this is exclusion and not an
    // empty panel passing by accident.
    expect(within(panel).getByText(/already comfortable with/i)).toBeInTheDocument();
    // And it is still settable, from the one control that owns it.
    expect(screen.getByRole("button", { name: /level/i })).toBeInTheDocument();
  });

  it("shows a retryable error when the brief read fails", async () => {
    stubFetch({ ok: false, status: 500, json: async () => ({}) });
    renderSetup();

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    readBrief();

    // The alert carries the real cause, not just a generic "failed".
    expect(await screen.findByRole("alert")).toHaveTextContent(/http 500/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("keeps the depth control in the options bar available regardless of the brief", async () => {
    // Regression for the reported bug (the depth control must never vanish): it now lives in the
    // always-visible options bar, so loading the brief can't drop it.
    stubFetch({ ok: true, json: async () => makeBriefResponse() });
    renderSetup();

    fireEvent.click(screen.getByRole("button", { name: /depth/i }));
    const depth = screen.getByRole("menu", { name: "Depth" });
    expect(within(depth).getByRole("menuitemradio", { name: /standard/i })).toBeInTheDocument();
    expect(within(depth).getByRole("menuitemradio", { name: /thorough/i })).toBeInTheDocument();
    fireEvent.keyDown(depth, { key: "Escape" });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "english" } });
    readBrief();
    await screen.findByText(/reach CLB 10/i);

    // Still reachable after the brief renders.
    expect(screen.getByRole("button", { name: /depth/i })).toBeInTheDocument();
  });

  it("threads the chosen Thorough depth into the build", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /depth/i }));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Depth" })).getByRole("menuitemradio", {
        name: /thorough/i,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith({
      topic: "binary search",
      clarification: undefined,
      discoveryDepth: "thorough",
      officialOnly: false,
    });
  });

  it("opens Settings from the Sources menu's trusted-domains row", () => {
    // The row is a real destination, not an ornament. A menu entry that goes nowhere is exactly
    // what this bar was built to stop offering.
    const onOpenSettings = vi.fn();
    renderSetup({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: /sources/i }));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Sources" })).getByRole("button", {
        name: /trusted domains/i,
      }),
    );

    expect(onOpenSettings).toHaveBeenCalled();
  });

  it("threads the Official-sources-only switch into the build", () => {
    const onGenerate = vi.fn();
    renderSetup({ onGenerate });

    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "binary search" } });
    fireEvent.click(screen.getByRole("button", { name: /sources/i }));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Sources" })).getByRole("menuitemradio", {
        name: /official only/i,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /generate course/i }));

    expect(onGenerate).toHaveBeenCalledWith({
      topic: "binary search",
      clarification: undefined,
      discoveryDepth: "standard",
      officialOnly: true,
    });
  });

  it("still reaches Settings, now from the Sources menu", () => {
    // The rail's operator section is gone, but the capability it pointed at is not: the trusted
    // domain list is one row inside the Sources menu.
    const onOpenSettings = vi.fn();
    renderSetup({ onOpenSettings });

    fireEvent.click(screen.getByRole("button", { name: /sources/i }));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Sources" })).getByRole("button", {
        name: /trusted domains/i,
      }),
    );

    expect(onOpenSettings).toHaveBeenCalledOnce();
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
    readBrief();
    expect(captured?.aborted).toBe(false);

    unmount();
    expect(captured?.aborted).toBe(true);
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
      readBrief();
      // The fixture always carries the "CLB 10" goal text; the variant covers the inferred GOAL
      // option (goal_type), not the goal prose — this just waits for the ready brief to render.
      await screen.findByText(/reach CLB 10/i);

      // Override the smart default depth (options bar), then build with the confirmed goal type.
      pickSetting("Depth", /thorough/i);
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
