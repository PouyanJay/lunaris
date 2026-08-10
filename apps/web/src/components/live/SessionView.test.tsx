import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "./SessionView";

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
