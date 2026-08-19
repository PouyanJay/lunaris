import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { runsSent, stubCopilotRuntime, turnWithCard } from "../../test/copilotRuntimeStub";
import { CopilotSession, isStandingCard } from "./CopilotSession";

/** The generative panel driven through the REAL kit in jsdom (P2b T10): the runtime is a
 *  route-aware `fetch` stub, everything else, `<CopilotKit>`, `<CopilotChat>`, `useRenderToolCall`,
 *  the agent's state, is the kit's own. Its sibling `CopilotSession.test.tsx` mocks
 *  `useRenderToolCall` to inspect registrations; this file needs the real one, because what it
 *  proves is that a card *rendered by the kit* can be answered in place and that the answer reaches
 *  the wire as the run the API expects. */

const QUIZ = {
  kind: "quiz_card",
  nodeId: "gradient",
  concept: "Gradient",
  question: "Which of these is actually true about Gradient?",
  options: ["The slope of the loss.", "How big the loss is."],
};

const NEXT_QUIZ = { ...QUIZ, nodeId: "loss", concept: "Loss", question: "And about Loss?" };

afterEach(() => {
  vi.unstubAllGlobals();
});

function mountPanel(extra: Partial<Parameters<typeof CopilotSession>[0]> = {}) {
  return render(
    <CopilotSession
      runtimeUrl="http://runtime.test"
      sessionId="sess-1"
      topic="Neural networks"
      standingTurn="Which way would you step?"
      standingSeq={1}
      {...extra}
    />,
  );
}

async function sendFromComposer(text: string) {
  const box = await screen.findByRole("textbox", { name: /your answer/i });
  await waitFor(() => expect(box).toBeEnabled());
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter", metaKey: true });
}

describe("the Tier 1 card inside the generative panel, answered in place", () => {
  it("makes the standing card answerable and sends the chosen option as the answer", async () => {
    // Success criterion 1, on this surface at last: the card mounts from the kit's own tool-call
    // rendering and the learner answers *in it*. The answer goes out as the next run's user
    // message, naming the turn the state frame said was standing (T9), which is what the API
    // grades against the criterion the card was staged for.
    stubCopilotRuntime((body, index) =>
      index === 0 ? turnWithCard(body, { callId: "call-1", card: QUIZ, turn: 2 }) : [],
    );
    mountPanel();
    await sendFromComposer("Downhill.");

    const group = await screen.findByRole("radiogroup", { name: QUIZ.question });
    const option = within(group).getByRole("radio", { name: QUIZ.options[1]! });
    await waitFor(() => expect(option).toBeEnabled());
    fireEvent.click(option);
    fireEvent.click(within(group.closest("form")!).getByRole("button", { name: /send/i }));

    await waitFor(() => expect(runsSent()).toHaveLength(2));
    const answered = runsSent()[1]!;
    expect(answered.messages.at(-1)?.content).toBe(QUIZ.options[1]);
    expect(answered.forwardedProps?.answeringSeq).toBe(2);
  });

  it("turns an earlier turn's card into a record once the next one is standing", async () => {
    // CopilotKit keeps every card in the thread on screen. Only the one the last state frame named
    // stays answerable; the rest are the record, and cannot send a late answer against the current
    // question (which the API would now refuse anyway).
    stubCopilotRuntime((body, index) =>
      index === 0
        ? turnWithCard(body, { callId: "call-1", card: QUIZ, turn: 2 })
        : turnWithCard(body, { callId: "call-2", card: NEXT_QUIZ, turn: 3, words: "Next." }),
    );
    mountPanel();
    await sendFromComposer("Downhill.");
    const first = await screen.findByRole("radiogroup", { name: QUIZ.question });
    await waitFor(() =>
      expect(within(first).getByRole("radio", { name: QUIZ.options[0]! })).toBeEnabled(),
    );

    await sendFromComposer("Still downhill.");
    const second = await screen.findByRole("radiogroup", { name: NEXT_QUIZ.question });

    await waitFor(() =>
      expect(within(second).getByRole("radio", { name: QUIZ.options[0]! })).toBeEnabled(),
    );
    expect(within(first).getByRole("radio", { name: QUIZ.options[0]! })).toBeDisabled();
    expect(within(first).queryByRole("button", { name: /send/i })).not.toBeInTheDocument();
  });

  it("offers no way to answer once the session has closed, and says so", async () => {
    // The last turn of a session is the mastery meter under a closed status. A composer still
    // offered there is a dead end (the API refuses with a 409); the panel says the session ended,
    // in the transcript surface's own words, and locks nothing silently.
    stubCopilotRuntime((body) =>
      turnWithCard(body, {
        callId: "call-1",
        card: { kind: "mastery_meter", entries: [] },
        turn: 2,
        status: "closed",
        words: "That is time.",
      }),
    );
    mountPanel();
    await sendFromComposer("Downhill.");

    await waitFor(() =>
      expect(screen.queryByRole("textbox", { name: /your answer/i })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("status", { name: /session/i })).toHaveTextContent(/has ended/i);
  });

  it("offers no answer on a closed session even when the standing card could take one", async () => {
    // The API closes a session on the mastery meter, which takes no answer anyway, so a panel that
    // forgot the session had closed would look right on every real session. This plants the state
    // the API does not produce: a closed session whose standing card is a quiz. One rule, held in
    // one place (the composer withholds `ready` once closed), and every card reads it from there.
    stubCopilotRuntime((body) =>
      turnWithCard(body, { callId: "call-1", card: QUIZ, turn: 2, status: "closed" }),
    );
    mountPanel();
    await sendFromComposer("Downhill.");

    const group = await screen.findByRole("radiogroup", { name: QUIZ.question });
    await waitFor(() =>
      expect(screen.queryByRole("textbox", { name: /your answer/i })).not.toBeInTheDocument(),
    );
    expect(within(group).getByRole("radio", { name: QUIZ.options[0]! })).toBeDisabled();
    expect(within(group.closest("form")!).queryByRole("button", { name: /send/i })).toBeNull();
  });

  it("tells its host each time a turn is taken, so the record can be re-read", async () => {
    // With a runtime configured the transcript below the panel is the record (T4), and it never
    // re-read: after the first turn it was stale. The panel reports each turn the state frames
    // announce; the host re-reads the session and the record stays true.
    const onTurnTaken = vi.fn();
    stubCopilotRuntime((body, index) =>
      turnWithCard(body, { callId: `call-${index}`, card: QUIZ, turn: index + 2 }),
    );
    mountPanel({ onTurnTaken });
    await sendFromComposer("Downhill.");
    await waitFor(() => expect(onTurnTaken).toHaveBeenCalledTimes(1));

    await sendFromComposer("Still downhill.");

    await waitFor(() => expect(onTurnTaken).toHaveBeenCalledTimes(2));
  });
});

describe("which card is the standing one", () => {
  it("is the card whose id the last state frame named, and only that one", () => {
    expect(isStandingCard("call-2", { surfaceCallId: "call-2" })).toBe(true);
    expect(isStandingCard("call-1", { surfaceCallId: "call-2" })).toBe(false);
  });

  it("is never a card with no id, whatever the state says", () => {
    // The kit's v1 hook does not declare `toolCallId` on its render props (it is on what the kit
    // actually passes), so a build that stopped passing it would leave every card without one. The
    // safe reading of that is "record", not "answerable": a wrong card is worse than a read-only
    // one when the answer it collects becomes evidence. Including the case where the state has
    // no id either, which is the only case where `undefined === undefined` would have said yes.
    expect(isStandingCard(null, { surfaceCallId: "call-1" })).toBe(false);
    expect(isStandingCard(null, {})).toBe(false);
  });
});
