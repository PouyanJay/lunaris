import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  ConceptMapSpec,
  CriterionCardSpec,
  ExplainBackSpec,
  MasteryMeterSpec,
  QuizCardSpec,
} from "../../lib/surfaceSpec";
import { SurfaceCard } from "./SurfaceCard";

/** The Tier 1 cards (Phase 2b, T4).
 *
 *  These are the components plan §8 calls "controlled": the director chose them and filled every
 *  prop, and what they render is therefore *not* a rendering decision — a card that reordered its
 *  options, filtered them, or paraphrased a criterion would undo a determinism the server pays for.
 *  So most of what is asserted here is fidelity: the map's words, in the server's order.
 *
 *  The other half is that answering happens **in the card**. That is the success criterion the
 *  whole tier exists for, and it is why three of the five carry an answer path and two deliberately
 *  do not.
 */

const CRITERION: CriterionCardSpec = {
  kind: "criterion_card",
  nodeId: "gradient",
  concept: "Gradient",
  statement: "Say which way a weight should move to lower the loss.",
  asks: "predict",
};

const QUIZ: QuizCardSpec = {
  kind: "quiz_card",
  nodeId: "gradient",
  concept: "Gradient",
  question: "Which of these is actually true about Gradient?",
  options: [
    "A gradient tells you how big the loss is.",
    "The slope of the loss with respect to each weight.",
    "A gradient points uphill, towards the answer.",
  ],
};

const EXPLAIN: ExplainBackSpec = {
  kind: "explain_back",
  nodeId: "gradient",
  concept: "Gradient",
  prompt: "Without looking back: what is Gradient, in your own words, and what is it for?",
};

const METER: MasteryMeterSpec = {
  kind: "mastery_meter",
  entries: [
    { nodeId: "gradient", concept: "Gradient", recall: 0.82, evidenceCount: 3 },
    { nodeId: "loss", concept: "Loss", recall: 0.31, evidenceCount: 1 },
  ],
};

const MAP: ConceptMapSpec = {
  kind: "concept_map",
  focusNodeId: "dynamics",
  concept: "Training dynamics",
  // Deliberately NOT alphabetical. The map teaches Loss before Gradient here, so a renderer that
  // sorted the chain would produce a different list — with ["Gradient", "Loss"] the two behaviours
  // are identical and the ordering test below proves nothing. That is the same fixture mistake T3
  // found in the mastery meter, and this is the fourth time this journey has made it.
  prerequisites: ["Loss", "Gradient"],
};

function renderCard(spec: Parameters<typeof SurfaceCard>[0]["spec"], overrides = {}) {
  const onAnswer = vi.fn();
  render(<SurfaceCard spec={spec} busy={false} answerable onAnswer={onAnswer} {...overrides} />);
  return { onAnswer };
}

describe("the criterion card", () => {
  it("shows the do-statement the learner will be marked on, word for word", () => {
    // Paraphrasing it would mark them against something they were never shown, which is the
    // fastest way to make a grader's verdict look arbitrary.
    renderCard(CRITERION);

    expect(screen.getByText(CRITERION.statement)).toBeInTheDocument();
  });

  it("sends what the learner wrote", () => {
    const { onAnswer } = renderCard(CRITERION);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "Downhill, against the gradient." },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onAnswer).toHaveBeenCalledWith("Downhill, against the gradient.");
  });
});

describe("the quiz card", () => {
  it("offers every option the server sent, in the order it sent them", () => {
    // Both halves matter. Dropping one would change what is being asked; reordering would undo the
    // server's own shuffle, which exists so the true option is not always in the same place.
    renderCard(QUIZ);

    const options = screen.getAllByRole("radio");
    expect(options.map((option) => option.getAttribute("value"))).toEqual(QUIZ.options);
  });

  it("sends the text of the chosen option, not its position", () => {
    // The choice is graded server-side against the same criterion as any prose answer (U1), so
    // what travels has to be an answer — an index would be a second assessment protocol.
    const { onAnswer } = renderCard(QUIZ);

    fireEvent.click(screen.getByRole("radio", { name: QUIZ.options[1]! }));
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onAnswer).toHaveBeenCalledWith(QUIZ.options[1]!);
  });

  it("says what is missing rather than disabling itself when nothing is chosen", () => {
    // A greyed-out button hides the reason it is not ready. The house rule is to let the submit
    // happen and explain — and the message has to reach a screen reader, not just the sighted eye.
    const { onAnswer } = renderCard(QUIZ);

    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onAnswer).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/pick one/i);
  });

  it("puts every option in one native group, which is what arrow keys follow", () => {
    // jsdom does not implement radio-group keyboard semantics, so no test here can press an arrow
    // key and watch selection move. What *is* checkable is the thing a real browser uses to decide
    // the group: a shared `name`. Broken, keyboard navigation silently stops working while every
    // other test in this file still passes.
    renderCard(QUIZ);

    const names = new Set(screen.getAllByRole("radio").map((radio) => radio.getAttribute("name")));
    expect(names.size).toBe(1);
    expect([...names][0]).toBeTruthy();
  });

  it("groups the options under the question for anyone not reading it visually", () => {
    // A loose pile of radios is unanswerable with a screen reader: the group's name is what says
    // which question they belong to.
    renderCard(QUIZ);

    expect(screen.getByRole("radiogroup", { name: QUIZ.question })).toBeInTheDocument();
  });
});

describe("the explain-back card", () => {
  it("asks for it in their own words and sends what they write", () => {
    const { onAnswer } = renderCard(EXPLAIN);

    expect(screen.getByText(EXPLAIN.prompt)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "It is the slope of the loss." },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(onAnswer).toHaveBeenCalledWith("It is the slope of the loss.");
  });
});

describe("the mastery meter", () => {
  it("shows a measured bar per concept, named so it can be read aloud", () => {
    renderCard(METER);

    const bars = screen.getAllByRole("progressbar");
    expect(bars).toHaveLength(2);
    expect(bars[0]).toHaveAttribute("aria-valuenow", "82");
    expect(bars[0]).toHaveAccessibleName(/gradient/i);
  });

  it("says what each belief rests on, not just how strong it is", () => {
    // The director gates on the belief; a human reading their own meter is owed the same
    // distinction it gets — one answer behind a number is not the same as five.
    //
    // Asserted per row, not per document. "Both numbers appear somewhere" stays true when the two
    // rows swap their counts, which is a meter telling the learner something false about which
    // concept they have actually demonstrated.
    renderCard(METER);

    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent(/gradient/i);
    expect(rows[0]).toHaveTextContent(/3 answers/i);
    expect(rows[1]).toHaveTextContent(/loss/i);
    expect(rows[1]).toHaveTextContent(/1 answer\b/i);
  });

  it("says nothing was marked rather than showing an empty frame", () => {
    // A session can close with no evidence at all — every answer ungraded, or the clock spent
    // before anything was staged. A heading over a blank list reads as a rendering failure.
    renderCard({ ...METER, entries: [] });

    expect(screen.getByText(/nothing was marked/i)).toBeVisible();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("offers no way to answer, because there is nothing being asked", () => {
    renderCard(METER);

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("the concept map card", () => {
  it("names the chain in the order the map teaches it", () => {
    renderCard(MAP);

    const chain = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(chain).toEqual(MAP.prerequisites);
  });

  it("says why nothing is being asked, rather than leaving a dead end", () => {
    // Every criterion needs a simulator, so no answer here could be marked. A card that simply
    // showed a diagram would leave the learner waiting for a question that is never coming.
    renderCard(MAP);

    // Visible, not merely present: an explanation the learner cannot see leaves the same dead end
    // as no explanation at all, and `toBeInTheDocument` passes on a hidden element.
    expect(screen.getByText(/can\u2019t be checked/i)).toBeVisible();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("stands on its own when the concept opens the map", () => {
    // The first concept has no prerequisites. An empty list with a heading above it reads as a
    // rendering failure; saying so reads as a fact about the map.
    renderCard({ ...MAP, prerequisites: [] });

    expect(screen.getByText(/nothing before it/i)).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});

describe("every answerable card", () => {
  it("locks while an answer is being marked", () => {
    // Not merely to look busy: a second send lands on a turn the first one has already moved past,
    // and the server refuses it as stale. Refusing it here keeps the learner out of that round trip.
    //
    // Reached by a **rerender**, and that is the point. Mounting straight into `busy` leaves nothing
    // chosen, so the "pick one first" guard blocks the send whether or not the busy guard exists —
    // the test passes with the thing it names deleted. The state it has to reach is *chosen, then
    // busy*, which only a rerender produces because the fieldset is disabled while busy.
    const onAnswer = vi.fn();
    const { rerender } = render(
      <SurfaceCard spec={QUIZ} busy={false} answerable onAnswer={onAnswer} />,
    );
    fireEvent.click(screen.getByRole("radio", { name: QUIZ.options[1]! }));

    rerender(<SurfaceCard spec={QUIZ} busy answerable onAnswer={onAnswer} />);
    fireEvent.click(screen.getByRole("button", { name: /sending/i }));

    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("refuses a second send from the keyboard while the first is still being marked", () => {
    // The disabled Send button stops a second *click*, and stops nothing else: a form still submits
    // on Enter, so a learner who presses it twice quickly sends the same answer against a turn the
    // first send has already moved past. The guard inside `submit` is what catches that, and only a
    // submit event can reach it — which is why clicking a disabled button cannot pin this.
    const onAnswer = vi.fn();
    const { rerender } = render(
      <SurfaceCard spec={QUIZ} busy={false} answerable onAnswer={onAnswer} />,
    );
    const chosen = screen.getByRole("radio", { name: QUIZ.options[1]! });
    fireEvent.click(chosen);
    const form = chosen.closest("form")!;

    rerender(<SurfaceCard spec={QUIZ} busy answerable onAnswer={onAnswer} />);
    fireEvent.submit(form);

    expect(onAnswer).not.toHaveBeenCalled();
  });

  it("becomes a record once the turn it belonged to has been answered", () => {
    // A card left answerable behind a turn that has moved on invites an answer that can only be
    // refused — and the learner has no way to see that from the card.
    const { onAnswer } = renderCard(CRITERION, { answerable: false });

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(CRITERION.statement)).toBeInTheDocument();
    expect(onAnswer).not.toHaveBeenCalled();
  });
});

describe("a card this build does not know", () => {
  it("renders nothing rather than guessing", () => {
    // The server can ship a sixth kind before this bundle does — separately deployed, as every
    // other cross-deployable contract here is. A wrong card is worse than no card, because these
    // feed the learner model.
    const { container } = render(
      <SurfaceCard
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        spec={{ kind: "simulator", nodeId: "x", concept: "X" } as any}
        busy={false}
        answerable
        onAnswer={vi.fn()}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("keyboard operation", () => {
  it("sends the quiz on Enter, from the radio the learner has landed on", () => {
    // A card answerable only with the mouse is slower by keyboard than by hand, which inverts what
    // a dense product surface is for. The house forms rule: wrap it in a form so Enter submits.
    const { onAnswer } = renderCard(QUIZ);
    const chosen = screen.getByRole("radio", { name: QUIZ.options[2]! });

    fireEvent.click(chosen);
    fireEvent.submit(chosen.closest("form")!);

    expect(onAnswer).toHaveBeenCalledWith(QUIZ.options[2]!);
  });
});
