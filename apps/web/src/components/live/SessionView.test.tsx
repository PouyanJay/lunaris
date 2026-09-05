import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WARMING_POLL_MS } from "../../hooks/useLiveSession";
import { SessionView } from "./SessionView";

// The generative panel is the kit's whole module graph; what this file needs from it is only its
// contract with the host: it is mounted with a runtime configured, and it reports each turn it
// takes. A stand-in that renders one button proves both without booting the kit.
vi.mock("./CopilotSession", async () => {
  const { useEffect } = await import("react");
  return {
    CopilotSession: ({
      onTurnTaken,
      standingTurn,
      nextReview,
    }: {
      onTurnTaken?: () => void;
      standingTurn: string | null;
      nextReview?: { day: string; concepts: string[] } | null;
    }) => {
      // Counts mounts, so a test can tell "the panel was rebuilt" from "the panel re-rendered".
      useEffect(() => {
        panelMounts += 1;
      }, []);
      return (
        <button type="button" onClick={() => onTurnTaken?.()}>
          turn taken: {standingTurn}
          {nextReview ? ` (come back ${nextReview.day})` : ""}
        </button>
      );
    },
  };
});
let panelMounts = 0;

/** A session as the API returns it: one turn, already teaching, with something staged to answer. */
const OPENED = {
  sessionId: "s1",
  graphId: "g1",
  status: "active" as const,
  startedAt: "2026-08-09T21:00:00Z",
  turns: [
    {
      seq: 1,
      move: { kind: "introduce" as const, nodeId: "gradient", reason: "Nothing precedes it." },
      tutor: "Picture the loss as a hillside. Which way is downhill?",
      runId: "r1",
      criterion: { kind: "explain" as const, statement: "Explain the gradient in your own words." },
      answer: null,
      grade: null,
      surface: {
        kind: "explain_back" as const,
        nodeId: "gradient",
        concept: "Gradient",
        prompt: "In your own words: what is Gradient, and what would you use it for?",
      },
    },
  ],
};

const ANSWERED = {
  ...OPENED,
  turns: [
    {
      ...OPENED.turns[0]!,
      answer: "It points downhill.",
      grade: { kind: "partial" as const, reason: "Direction yes, steepness missing." },
    },
    {
      seq: 2,
      move: { kind: "remediate" as const, nodeId: "gradient", reason: "It has not landed." },
      tutor: "Let's come at it from the steepness side.",
      runId: "r2",
      criterion: { kind: "explain" as const, statement: "Say how steep it is there." },
      answer: null,
      grade: null,
      surface: {
        kind: "quiz_card" as const,
        nodeId: "gradient",
        concept: "Gradient",
        question: "Which of these is actually true about Gradient?",
        options: ["The slope of the loss.", "How big the loss is."],
      },
    },
  ],
};

const CLOSED = {
  ...OPENED,
  status: "closed" as const,
  turns: [
    { ...OPENED.turns[0]!, answer: "It points downhill.", grade: null },
    {
      seq: 2,
      move: { kind: "close" as const, nodeId: null, reason: "The session's 30 minutes are up." },
      tutor: "That's where we'll stop for today. The session's 30 minutes are up.",
      runId: "r2",
      criterion: null,
      answer: null,
      grade: null,
      surface: {
        kind: "mastery_meter" as const,
        entries: [{ nodeId: "gradient", concept: "Gradient", recall: 0.51, evidenceCount: 2 }],
      },
    },
  ],
};

/** Answers every call with the same body — the factory re-runs per invocation, so "once" would be
 *  a lie the next multi-fetch test would trip over. */
function jsonAlways(body: unknown, status = 200) {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SessionView — the plainest surface a session can have", () => {
  it("shows the session is opening before there is anything to read", async () => {
    // A spinner where a transcript will be is a blank flash; the placeholder has the shape of the
    // thing it stands in for, so nothing jumps when the first turn lands.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    expect(await screen.findByRole("status")).toHaveTextContent(/opening/i);
  });

  it("renders the tutor's turn and what the learner is being asked to do", async () => {
    vi.stubGlobal("fetch", jsonAlways(OPENED, 201));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    expect(await screen.findByText(/picture the loss as a hillside/i)).toBeInTheDocument();
    // The staged criterion is the whole contract of the turn: it is what the answer is marked
    // against, so a surface that hid it would be asking for something it never showed.
    expect(screen.getByText("Explain the gradient in your own words.")).toBeInTheDocument();
  });

  it("shows why the director chose this move, so a session can be audited while it runs", async () => {
    vi.stubGlobal("fetch", jsonAlways(OPENED, 201));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    const transcript = await screen.findByRole("list", { name: /transcript/i });
    expect(within(transcript).getByText(/nothing precedes it/i)).toBeInTheDocument();
    expect(within(transcript).getByText("INTRODUCE")).toBeInTheDocument();
    // A turn arriving is the whole event of a session; somebody using a screen reader should hear
    // it rather than having to go looking for it.
    expect(transcript).toHaveAttribute("aria-live", "polite");
  });

  it("sends an answer and shows the verdict on it", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(OPENED), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(ANSWERED), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);
    const box = await screen.findByRole("textbox", { name: /your answer/i });

    fireEvent.change(box, { target: { value: "It points downhill." } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // The verdict first: it exists only once the server has answered, so waiting on it is waiting
    // for the settled state. Waiting on the answer text instead would match the optimistic echo,
    // which is replaced by the real turn a tick later — a green assertion against a detached node.
    expect(await screen.findByText("PARTIAL")).toBeInTheDocument();
    expect(screen.getByText("It points downhill.")).toBeInTheDocument();
    expect(screen.getByText(/direction yes, steepness missing/i)).toBeInTheDocument();
    // The answer names the turn it answers (T6): without it a double-send is graded against the
    // question that replaced the one it was written for.
    const [, answerCall] = fetchMock.mock.calls;
    expect(JSON.parse(String(answerCall?.[1]?.body))).toMatchObject({
      answer: "It points downhill.",
      answeringSeq: 1,
    });
  });

  it("will not send an empty answer", async () => {
    vi.stubGlobal("fetch", jsonAlways(OPENED, 201));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);
    await screen.findByRole("textbox", { name: /your answer/i });

    // Enabled — a form that pre-disables its own submit hides the reason it is not ready.
    const send = screen.getByRole("button", { name: /send/i });
    expect(send).toBeEnabled();
    fireEvent.click(send);

    expect(await screen.findByText(/write something first/i)).toBeInTheDocument();
    // And the caret goes back where the writing happens: an error nobody is focused on is an
    // error a keyboard user has to go looking for.
    expect(screen.getByRole("textbox", { name: /your answer/i })).toHaveFocus();
  });

  it("keeps the learner informed while their answer is being marked", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(OPENED), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockImplementationOnce(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);
    fireEvent.change(await screen.findByRole("textbox", { name: /your answer/i }), {
      target: { value: "It points downhill." },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // A tutor takes seconds to answer, so the wait is a state, not a gap — and the box is locked
    // so the same answer cannot be sent twice while the first is still being marked. Their own
    // words appear straight away; the verdict does not, because that is the server's to give.
    expect(await screen.findByText(/marking/i)).toBeInTheDocument();
    expect(screen.getByText("It points downhill.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeDisabled();
  });

  it.each([
    ["met", "MET"],
    ["partial", "PARTIAL"],
    ["not_met", "NOT MET"],
  ])("renders the %s verdict in words, not colour alone", async (kind, label) => {
    const graded = {
      ...OPENED,
      turns: [{ ...OPENED.turns[0]!, answer: "Something.", grade: { kind, reason: "Because." } }],
    };
    vi.stubGlobal("fetch", jsonAlways(graded, 201));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    expect(await screen.findByText(label)).toBeInTheDocument();
  });

  it("says the session has ended instead of offering a box that cannot be used", async () => {
    vi.stubGlobal("fetch", jsonAlways(CLOSED, 201));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    expect(await screen.findByText(/that's where we'll stop/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /your answer/i })).not.toBeInTheDocument();
    expect(screen.getByText("CLOSED")).toBeInTheDocument();
  });

  it("tells the learner when to come back, and for what, once the session has closed", async () => {
    // P2c T7: the close scheduled Gradient for review; the ending under the meter says the day
    // (the same day the meter row shows), so nobody has to read a date off a table.
    const scheduled = {
      ...CLOSED,
      turns: [
        CLOSED.turns[0]!,
        {
          ...CLOSED.turns[1]!,
          surface: {
            kind: "mastery_meter" as const,
            entries: [
              {
                nodeId: "gradient",
                concept: "Gradient",
                recall: 0.51,
                evidenceCount: 2,
                dueAt: "2026-08-20T12:00:00Z",
              },
            ],
          },
        },
      ],
    };
    vi.stubGlobal("fetch", jsonAlways(scheduled, 201));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    const ending = await screen.findByRole("status", { name: /session ended/i });
    expect(ending).toHaveTextContent(/come back on Thursday 20 August for Gradient/i);
  });

  it("labels the director's moves in words a learner can read", async () => {
    // The trace's move kinds are the API's vocabulary; a learner reads "GETTING TO KNOW YOU"
    // over an interview question, not "PLACE". Uppercase mono still: it is data, the label of a
    // row, and its style is the transcript's own.
    const placing = {
      ...OPENED,
      status: "placing" as const,
      topic: "How neural networks learn",
      turns: [
        {
          seq: 1,
          move: { kind: "place" as const, nodeId: null, reason: "The map is still being built." },
          tutor: "Before we start: what have you already met of this?",
          runId: "r1",
          criterion: null,
          answer: null,
          grade: null,
          surface: null,
          layout: null,
        },
      ],
    };
    vi.stubGlobal("fetch", jsonAlways(placing, 201));

    render(<SessionView apiBaseUrl="" topic="How neural networks learn" />);

    const transcript = await screen.findByRole("list", { name: /transcript/i });
    expect(within(transcript).getByText("GETTING TO KNOW YOU")).toBeInTheDocument();
    expect(within(transcript).queryByText("PLACE")).not.toBeInTheDocument();
  });

  it("interviews in the same box a lesson is answered in, while the session is placing", async () => {
    // P2c: an interview turn is a question with nothing staged. It is answered where every turn
    // is answered, and the surface says which state the session is in rather than "live".
    const placing = {
      ...OPENED,
      status: "placing" as const,
      topic: "How neural networks learn",
      turns: [
        {
          seq: 1,
          move: { kind: "place" as const, nodeId: null, reason: "The map is still being built." },
          tutor: "Before we start: what have you already met of this?",
          runId: "r1",
          criterion: null,
          answer: null,
          grade: null,
          surface: null,
          layout: null,
        },
      ],
    };
    vi.stubGlobal("fetch", jsonAlways(placing, 201));

    render(<SessionView apiBaseUrl="" topic="How neural networks learn" />);

    expect(await screen.findByText(/what have you already met of this/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeInTheDocument();
    expect(screen.getByText("PLACING")).toBeInTheDocument();
  });

  it("waits visibly, with nothing to answer, while the session is warming", async () => {
    // P2c T2: the interview ran out before the map landed. No composer (an answer would have
    // nothing to be an answer to), a status region that says what is happening, and the hook
    // polling behind it (the second call is the advance).
    const warming = {
      ...OPENED,
      status: "warming" as const,
      topic: "How neural networks learn",
      turns: [
        {
          seq: 1,
          move: { kind: "place" as const, nodeId: null, reason: "The map is still being built." },
          tutor: "Before we start: what have you already met of this?",
          runId: "r1",
          criterion: null,
          answer: "Not much.",
          grade: null,
          surface: null,
          layout: null,
        },
        {
          seq: 2,
          move: { kind: "place" as const, nodeId: null, reason: "The interview is over." },
          tutor:
            "Thanks, that's what I needed. The map is nearly ready; I'll start the moment it is.",
          runId: "r2",
          criterion: null,
          answer: null,
          grade: null,
          surface: null,
          layout: null,
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(warming), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValue(new Response(null, { status: 202 }));
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionView apiBaseUrl="" topic="How neural networks learn" />);

    expect(await screen.findByText(/nearly ready/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/almost ready|first lesson/i);
    expect(screen.getByText("WARMING")).toBeInTheDocument();
  });

  it("surfaces the server's own words when a session cannot be opened, and offers a way back", async () => {
    vi.stubGlobal(
      "fetch",
      jsonAlways({ detail: "Live's tutor could not reach its model. Try again shortly." }, 503),
    );

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach its model/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("recovers when a retry succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Nope." }), { status: 503 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(OPENED), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    expect(await screen.findByText(/picture the loss as a hillside/i)).toBeInTheDocument();
  });

  it("tells the learner to reload when their answer was already recorded", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(OPENED), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: "That question has already been answered. Reload to catch up.",
          }),
          { status: 409, headers: { "content-type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);
    fireEvent.change(await screen.findByRole("textbox", { name: /your answer/i }), {
      target: { value: "It points downhill." },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // The transcript they already have is still theirs to read — a failed send must not take the
    // session away from them.
    expect(await screen.findByRole("alert")).toHaveTextContent(/already been answered/i);
    expect(screen.getByText(/picture the loss as a hillside/i)).toBeInTheDocument();
  });

  it("submits on ⌘↵ from the answer box", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(OPENED), {
          status: 201,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(ANSWERED), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);
    const box = await screen.findByRole("textbox", { name: /your answer/i });
    fireEvent.change(box, { target: { value: "It points downhill." } });

    // Enter alone must stay a newline: the answer is prose, and a stray Return mid-thought that
    // submitted it would be the surface answering for them.
    fireEvent.keyDown(box, { key: "Enter" });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });
});

describe("the Tier 1 card (T4)", () => {
  it("puts the director's card in front of the learner, not a bare answer box", async () => {
    // The turn's own surface, chosen server-side. Rendering only the generic box would throw away
    // the whole tier: the card is what makes an explain-back different from a quiz.
    vi.stubGlobal("fetch", jsonAlways(OPENED, 201));
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);

    expect(await screen.findByText(/In your own words: what is Gradient/i)).toBeInTheDocument();
  });

  it("answers through the card, and the answer reaches the API for that turn", async () => {
    // The task's claim, from this side of the wire: what the learner typed into the *card* is what
    // gets sent, named against the turn the card belonged to.
    const fetchMock = jsonAlways(OPENED, 201);
    vi.stubGlobal("fetch", fetchMock);
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);
    await screen.findByText(/In your own words: what is Gradient/i);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "It is the slope of the loss." },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      const sent = (fetchMock.mock.calls as unknown as [string, RequestInit][]).find(([url]) =>
        String(url).includes("/turns"),
      );
      expect(sent).toBeDefined();
      expect(JSON.parse(String(sent?.[1]?.body))).toMatchObject({
        answer: "It is the slope of the loss.",
        answeringSeq: 1,
      });
    });
  });

  it("composes the standing turn around its card (T5)", async () => {
    // Tier 2 in the surface every environment actually runs. The card stays answerable inside the
    // composition — a layout that displaced the answer path would trade the tier for the loop.
    const composed = {
      ...OPENED,
      turns: [
        {
          ...OPENED.turns[0]!,
          layout: {
            catalogId: "lunaris.live.layout/v1",
            blocks: [
              { component: "Stack", id: "root", children: ["example", "surface", "hint"] },
              {
                component: "WorkedExample",
                id: "example",
                title: "Rolling downhill",
                steps: ["Read the slope.", "Step against it."],
                expanded: true,
              },
              { component: "Surface", id: "surface" },
              { component: "Hint", id: "hint", hint: "The sign is the direction." },
            ],
          },
        },
      ],
    };
    vi.stubGlobal("fetch", jsonAlways(composed, 201));
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);

    expect(await screen.findByText("Rolling downhill")).toBeInTheDocument();
    expect(screen.getByText("Show a hint")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("does not print the standing turn's words twice", async () => {
    // The transcript above already holds every word the tutor has said, so the layout's prose slot
    // is deliberately empty on this surface. Filling it would show the standing lesson twice, which
    // reads as the tutor repeating itself rather than as a composition.
    const composed = {
      ...OPENED,
      turns: [
        {
          ...OPENED.turns[0]!,
          layout: {
            catalogId: "lunaris.live.layout/v1",
            blocks: [
              { component: "Stack", id: "root", children: ["prose", "surface"] },
              { component: "Prose", id: "prose" },
              { component: "Surface", id: "surface" },
            ],
          },
        },
      ],
    };
    vi.stubGlobal("fetch", jsonAlways(composed, 201));
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);
    await screen.findByRole("textbox");

    expect(screen.getAllByText(OPENED.turns[0]!.tutor)).toHaveLength(1);
  });

  it("keeps a session stored before P2b answerable", async () => {
    // Every row P2a wrote has no surface. Falling back to the plain box is what stops the tier's
    // arrival making the whole of Live's own history unanswerable.
    const noSurface = { ...OPENED.turns[0]!, surface: null };
    vi.stubGlobal("fetch", jsonAlways({ ...OPENED, turns: [noSurface] }, 201));
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);

    expect(await screen.findByRole("textbox")).toBeInTheDocument();
  });

  it("stops taking answers once the session has closed", async () => {
    // The meter is a record, and the close already said so. An answer box under it would invite an
    // answer the server can only refuse.
    vi.stubGlobal("fetch", jsonAlways(CLOSED, 201));
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);
    await screen.findByText(/session has ended/i);

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAccessibleName(/gradient/i);
  });

  it("refuses to answer into a closed session even if a card says otherwise", async () => {
    // Defensive, deliberately. A closed session's last turn is the goodbye, whose card is always
    // the meter — so today the guard cannot fire. It exists because that is a *server-side*
    // invariant, and a surface that took an answer for a session the API will refuse would show
    // the learner a box whose only possible outcome is an error.
    const closedButAnswerable = {
      ...CLOSED,
      turns: [CLOSED.turns[0]!, { ...CLOSED.turns[1]!, surface: OPENED.turns[0]!.surface }],
    };
    vi.stubGlobal("fetch", jsonAlways(closedButAnswerable, 201));
    render(<SessionView apiBaseUrl="" graphId="g1" topic="Neural networks" />);
    await screen.findByText(/session has ended/i);

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("rebuilds the panel when teaching begins, so it opens on the first lesson", async () => {
    // P2c T7: the panel's thread opens on the turn it mounted with, and the first lesson arrives
    // through the host's poll (advance), not through a run of the panel's own — so a panel mounted
    // during the interview would keep showing the last question over a session that has moved
    // on. Across the placing → teaching boundary the panel is rebuilt; within a phase it is not.
    // Fake timers, as the hook's own tests drive the poll: the interval is advanced, not waited.
    vi.useFakeTimers();
    try {
      panelMounts = 0;
      const warming = {
        ...OPENED,
        status: "warming" as const,
        topic: "Neural networks",
        turns: [
          {
            seq: 1,
            move: { kind: "place" as const, nodeId: null, reason: "The interview is over." },
            tutor: "Thanks, the map is nearly ready.",
            runId: "r1",
            criterion: null,
            answer: "Not much.",
            grade: null,
            surface: null,
            layout: null,
          },
        ],
      };
      const taught = { ...OPENED, turns: [{ ...OPENED.turns[0]!, seq: 2 }] };
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(
          new Response(JSON.stringify(warming), {
            status: 201,
            headers: { "content-type": "application/json" },
          }),
        )
        .mockResolvedValue(
          new Response(JSON.stringify(taught), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      vi.stubGlobal("fetch", fetchMock);
      render(
        <SessionView apiBaseUrl="" topic="Neural networks" copilotUrl="http://runtime.test" />,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(screen.getByText(/turn taken: Thanks, the map is nearly ready/i)).toBeInTheDocument();
      expect(panelMounts).toBe(1);

      // The poll advances the session; the panel is rebuilt on the first lesson.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(WARMING_POLL_MS + 500);
      });
      expect(screen.getByText(/turn taken: Picture the loss as a hillside/i)).toBeInTheDocument();
      expect(panelMounts).toBe(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("hands the panel the day to come back, so its ending can say it too", async () => {
    // P2c T7: the panel's composer slot cannot see the meter the kit drew as a card; the host,
    // which re-reads the closed session, tells it.
    const scheduled = {
      ...CLOSED,
      turns: [
        CLOSED.turns[0]!,
        {
          ...CLOSED.turns[1]!,
          surface: {
            kind: "mastery_meter" as const,
            entries: [
              {
                nodeId: "gradient",
                concept: "Gradient",
                recall: 0.51,
                evidenceCount: 2,
                dueAt: "2026-08-20T12:00:00Z",
              },
            ],
          },
        },
      ],
    };
    vi.stubGlobal("fetch", jsonAlways(scheduled, 201));
    render(
      <SessionView
        apiBaseUrl=""
        graphId="g1"
        topic="Neural networks"
        copilotUrl="http://runtime.test"
      />,
    );

    expect(await screen.findByText(/come back Thursday 20 August/i)).toBeInTheDocument();
  });

  it("offers exactly one place to answer when the generative runtime is configured", async () => {
    // The hazard T2 left open and T4 closes: with both surfaces live, answering in one advanced the
    // session without the other knowing, and the two disagreed about what the learner had done.
    // The CopilotKit panel becomes the place to answer, and the transcript stays the record.
    vi.stubGlobal("fetch", jsonAlways(OPENED, 201));
    render(
      <SessionView
        apiBaseUrl=""
        graphId="g1"
        topic="Neural networks"
        copilotUrl="http://runtime.test"
      />,
    );
    await screen.findByLabelText(/session on neural networks/i);

    await waitFor(() => expect(screen.queryByRole("textbox")).not.toBeInTheDocument());
  });

  it("re-reads the session each time the panel takes a turn, so the record stays true", async () => {
    // With the panel answering, the transcript beside it is the record (T4), and until T10 it never
    // re-read: after the first panel turn it showed a session that no longer existed. The panel
    // reports each turn its state frames announce, and the transcript re-reads the row.
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: string | URL | Request, init?: RequestInit) => {
        const method = (init?.method ?? "GET").toUpperCase();
        const body = method === "POST" ? OPENED : ANSWERED;
        return Promise.resolve(
          new Response(JSON.stringify(body), {
            status: method === "POST" ? 201 : 200,
            headers: { "content-type": "application/json" },
          }),
        );
      }),
    );
    render(
      <SessionView
        apiBaseUrl=""
        graphId="g1"
        topic="Neural networks"
        copilotUrl="http://runtime.test"
      />,
    );
    await screen.findByLabelText(/session on neural networks/i);
    expect(screen.getByText(/1 turn\b/)).toBeInTheDocument();

    // The stand-in panel reports a turn the way the real one does (see the mock at the top).
    fireEvent.click(await screen.findByRole("button", { name: /turn taken/i }));

    await waitFor(() => expect(screen.getByText(/2 turns/)).toBeInTheDocument());
    const reads = vi
      .mocked(fetch)
      .mock.calls.filter(([, init]) => (init?.method ?? "GET").toUpperCase() === "GET");
    expect(reads.map(([input]) => String(input))).toContain("/api/live/sessions/s1");
  });
});

describe("a session the learner left", () => {
  /** The same opened session, in whatever state the server says it is in.
   *
   *  201, like a real open: answering with 200 puts the hook straight into its failure state, and
   *  every assertion below would then be about an error screen rather than about a session (found
   *  by writing them wrong first). */
  function opened(status: string) {
    return jsonAlways({ ...OPENED, status }, 201);
  }

  it("is not offered a composer, because it cannot be answered", async () => {
    // The defect this pins: three surfaces tested `status === "closed"` and none of them knew about
    // `abandoned`, the status added when leaving a session became possible. A learner reopening one
    // they had left was handed a box whose every submission the API refuses.
    vi.stubGlobal("fetch", opened("abandoned"));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    await screen.findByRole("heading", { name: "How neural networks learn" });
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByText(/this session has ended/i)).toBeInTheDocument();
  });

  it("says it has ended rather than showing itself as live", async () => {
    vi.stubGlobal("fetch", opened("abandoned"));

    render(<SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />);

    await screen.findByRole("heading", { name: "How neural networks learn" });
    // A left session reading as live is the surface disagreeing with the row behind it — and
    // borrowing "closed" for it would say the learner finished something they walked out of.
    expect(screen.getByText(/abandoned/i)).toBeInTheDocument();
    expect(screen.queryByText(/^live$/i)).not.toBeInTheDocument();
  });

  it.each(["placing", "warming", "active", "closed", "abandoned"])(
    "renders something a learner can read in the %s state",
    async (status) => {
      // The blank-canvas guard. Every status the wire can carry has to put *something* on screen:
      // an empty surface under a topbar is indistinguishable from a broken app, and it is the one
      // failure a learner cannot report usefully.
      vi.stubGlobal("fetch", opened(status));

      const { container } = render(
        <SessionView apiBaseUrl="" graphId="g1" topic="How neural networks learn" />,
      );

      await screen.findByRole("heading", { name: "How neural networks learn" });
      expect(container.textContent?.trim().length ?? 0).toBeGreaterThan(
        "How neural networks learn".length,
      );
    },
  );
});
