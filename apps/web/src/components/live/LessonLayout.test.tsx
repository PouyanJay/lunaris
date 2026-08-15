import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  LAYOUT_CATALOG,
  type LayoutBlockSpec,
  type LayoutComponentName,
  type LayoutSpec,
} from "../../lib/layoutSpec";
import { LessonLayout } from "./LessonLayout";

/** Tier 2 on screen (Phase 2b, T5).
 *
 *  Plan §8 makes this the tier where the lesson is composed per learner. The server does the
 *  composing, so almost everything asserted here is **fidelity**: the blocks it sent, in the order
 *  it sent them, in the state it chose. A renderer that sorted, deduplicated, opened a closed
 *  example or supplied a hint the composition withheld would make the whole two-learner claim
 *  unprovable from the wire — the same failure an improvising Tier 1 renderer would cause, one tier
 *  down and quieter.
 *
 *  The other half is the fallbacks. Every session P2a stored has no layout, a turn whose material
 *  could not be written has none, and this SPA can meet a catalog a newer API knows first. All
 *  three must read as a plainer lesson rather than a broken one.
 */

const EXAMPLE_STEPS = ["Start at a point.", "Read the slope.", "Step against it."];
const PROMPTS = ["Which way does the weight move?", "What happens at a flat spot?"];

function layoutOf(...blocks: LayoutBlockSpec[]): LayoutSpec {
  return {
    catalogId: LAYOUT_CATALOG,
    blocks: [
      { component: "Stack", id: "root", children: blocks.map((block) => block.id) },
      ...blocks,
    ],
  };
}

const PROSE = <p data-testid="prose">The tutor said this.</p>;
const CARD = <div data-testid="card">The question.</div>;

function draw(layout: LayoutSpec | null) {
  return render(<LessonLayout layout={layout} prose={PROSE} card={CARD} />);
}

/** What was drawn, top to bottom, named by the shortest thing that identifies each block.
 *
 *  Read off the DOM rather than off the spec, because the claim is about what the learner ends up
 *  looking at — a renderer that held the right list and painted it in another order would satisfy
 *  any assertion made against its input.
 */
function drawnOrder(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("[data-testid], details, section")).map(
    // A slot is named by its test id; every other block opens with its own eyebrow label, which is
    // the first span or paragraph inside it.
    (node) =>
      node.getAttribute("data-testid") ?? node.querySelector("span, p")?.textContent?.trim() ?? "",
  );
}

const SCAFFOLDED = layoutOf(
  { component: "Prose", id: "prose" },
  {
    component: "WorkedExample",
    id: "example",
    title: "Rolling downhill",
    steps: EXAMPLE_STEPS,
    expanded: true,
  },
  { component: "Practice", id: "practice", prompts: PROMPTS },
  { component: "Surface", id: "surface" },
  { component: "Hint", id: "hint", hint: "The sign is the direction." },
);

describe("the composed lesson", () => {
  it("puts the tutor's words and the card in the slots the layout named", () => {
    // Slots, not copies: both live on the turn, and a layout carrying its own text could disagree
    // with the transcript the learner is actually marked against.
    draw(SCAFFOLDED);

    expect(screen.getByTestId("prose")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });

  it("draws the blocks in the order the server composed them", () => {
    // Order *is* the composition. A question placed above the worked example that sets it up is a
    // different lesson built from identical parts, so this asserts the sequence rather than the set.
    const { container } = draw(SCAFFOLDED);

    expect(drawnOrder(container)).toEqual([
      "prose",
      "Worked example",
      "Before you answer",
      "card",
      "Stuck?",
    ]);
  });

  it("follows the server's order even when it is not the order the composer usually emits", () => {
    // The test above cannot tell "renders `children` in order" from "renders a canonical component
    // order", because `compose_layout` always emits the same sequence — so every natural fixture
    // has the two agreeing. This one deliberately disagrees with it.
    //
    // Not hypothetical: the composer is free to reorder at any time (a future move kind, a
    // placement interview), and a renderer that had quietly hardcoded the running order would keep
    // drawing the old lesson while the server believed it had changed one.
    const { container } = draw(
      layoutOf(
        { component: "Hint", id: "hint", hint: "The sign is the direction." },
        {
          component: "WorkedExample",
          id: "example",
          title: "Rolling downhill",
          steps: EXAMPLE_STEPS,
          expanded: false,
        },
        { component: "Surface", id: "surface" },
        { component: "Prose", id: "prose" },
      ),
    );

    expect(drawnOrder(container)).toEqual(["Stuck?", "Worked example", "card", "prose"]);
  });

  it("opens the worked example when the composition opened it", () => {
    draw(SCAFFOLDED);

    const example = screen.getByText("Rolling downhill").closest("details");
    expect(example).toHaveAttribute("open");
  });

  it("leaves the worked example closed when the composition closed it", () => {
    // The band a learner reaches once they have shown something. A renderer that opened it anyway
    // would erase the difference between the two learners the tier exists to tell apart.
    draw(
      layoutOf({
        component: "WorkedExample",
        id: "example",
        title: "Rolling downhill",
        steps: EXAMPLE_STEPS,
        expanded: false,
      }),
    );

    expect(screen.getByText("Rolling downhill").closest("details")).not.toHaveAttribute("open");
  });

  it("keeps every step of the worked example, in order and unedited", () => {
    draw(SCAFFOLDED);

    const example = screen.getByText("Rolling downhill").closest("details");
    expect(example).not.toBeNull();
    // Scoped to the example itself: the practice prompts are a list too, and asserting against the
    // whole document would let the two swap their contents without anything noticing.
    const steps = within(example as HTMLElement);
    expect(steps.getAllByRole("listitem").map((item) => item.textContent)).toEqual(
      EXAMPLE_STEPS.map((step, index) => `${index + 1}${step}`),
    );
  });

  it("keeps the hint closed, because reaching for it is the learner's move", () => {
    // A hint that opened itself is the answer moved up the page. Nothing in the composition can
    // ask for it open, which is why this is a property of the renderer rather than of the spec.
    draw(SCAFFOLDED);

    expect(screen.getByText("Show a hint").closest("details")).not.toHaveAttribute("open");
    expect(screen.getByText("The sign is the direction.")).toBeInTheDocument();
  });

  it("shows exactly the practice prompts it was given, in order", () => {
    // The *number* is the server's decision — the scaffold is sized to what the learner has shown —
    // so a renderer that truncated or padded the list would silently undo the sizing.
    draw(SCAFFOLDED);

    const practice = within(screen.getByRole("region", { name: "Before you answer" }));
    expect(practice.getAllByRole("listitem").map((item) => item.textContent)).toEqual(PROMPTS);
  });
});

describe("the allow-list this build knows", () => {
  it("draws every component the server's catalog contains, and names them as literals", () => {
    // The other half of a contract pinned on both sides — `test_the_allow_list_is_exactly_these_six
    // _names` asserts the same six strings from Python. A shared import would only prove agreement
    // at commit time; the API and this SPA are separately deployed, so what matters is that the
    // build actually running knows the names the build actually composing uses.
    //
    // Drift is the quiet failure this whole tier has: a component the server composes and this
    // build has never heard of renders as nothing, and every server-side assertion still passes.
    const catalog: LayoutComponentName[] = [
      "Stack",
      "Prose",
      "Surface",
      "WorkedExample",
      "Hint",
      "Practice",
    ];

    draw(
      layoutOf(
        { component: "Prose", id: "prose" },
        {
          component: "WorkedExample",
          id: "example",
          title: "Rolling downhill",
          steps: EXAMPLE_STEPS,
          expanded: false,
        },
        { component: "Practice", id: "practice", prompts: PROMPTS },
        { component: "Surface", id: "surface" },
        { component: "Hint", id: "hint", hint: "The sign is the direction." },
      ),
    );

    expect(catalog).toHaveLength(6);
    expect(LAYOUT_CATALOG).toBe("lunaris.live.layout/v1");
    // Every non-slot component drew something of its own, and both slots drew what they were given.
    expect(screen.getByTestId("prose")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toBeInTheDocument();
    expect(screen.getByText("Rolling downhill")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Before you answer" })).toBeInTheDocument();
    expect(screen.getByText("Show a hint")).toBeInTheDocument();
  });
});

describe("what it does when there is no composition to draw", () => {
  it("falls back to the words and the card when the turn has no layout", () => {
    // Every session P2a stored is this case, and so is a turn whose material could not be written.
    draw(null);

    expect(screen.getByTestId("prose")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });

  it("falls back whole rather than drawing part of a catalog it does not know", () => {
    // The API and this SPA deploy separately, so the server can learn a v2 catalog first. Drawing
    // only the blocks this build recognises would show a lesson with holes where the new ones were.
    draw({ ...SCAFFOLDED, catalogId: "lunaris.live.layout/v99" });

    expect(screen.getByTestId("prose")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toBeInTheDocument();
    expect(screen.queryByText("Rolling downhill")).not.toBeInTheDocument();
  });

  it("falls back when the layout has no root to start from", () => {
    draw({ catalogId: LAYOUT_CATALOG, blocks: [{ component: "Prose", id: "prose" }] });

    expect(screen.getByTestId("prose")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });

  it("draws the rest of the lesson when one block does not resolve", () => {
    // The server refuses such a layout, so reaching here means a truncated or tampered payload.
    // The words and the card still have to arrive: a lesson missing its trimmings is readable.
    draw({
      catalogId: LAYOUT_CATALOG,
      blocks: [
        { component: "Stack", id: "root", children: ["prose", "ghost", "surface"] },
        { component: "Prose", id: "prose" },
        { component: "Surface", id: "surface" },
      ],
    });

    expect(screen.getByTestId("prose")).toBeInTheDocument();
    expect(screen.getByTestId("card")).toBeInTheDocument();
  });

  it("does not recurse forever on a layout that names itself as its own child", () => {
    // These ids come off a wire. A renderer that trusted them would have made the browser's
    // stability a property of somebody else's validator.
    draw({
      catalogId: LAYOUT_CATALOG,
      blocks: [
        { component: "Stack", id: "root", children: ["inner"] },
        { component: "Stack", id: "inner", children: ["root", "prose"] },
        { component: "Prose", id: "prose" },
      ],
    });

    expect(screen.getByTestId("prose")).toBeInTheDocument();
  });
});
