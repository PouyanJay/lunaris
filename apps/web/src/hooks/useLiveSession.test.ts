import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useLiveSession } from "./useLiveSession";

const OPENED = {
  sessionId: "s1",
  graphId: "g1",
  status: "active" as const,
  startedAt: "2026-08-09T21:00:00Z",
  turns: [
    {
      seq: 1,
      move: { kind: "introduce", nodeId: "a", reason: "Nothing precedes it." },
      tutor: "Picture the loss as a hillside.",
      runId: "r1",
      criterion: { kind: "explain", statement: "Explain it back." },
      answer: "Downhill.",
      grade: { kind: "met", reason: "Yes." },
    },
    {
      seq: 2,
      move: { kind: "introduce", nodeId: "b", reason: "A is demonstrated." },
      tutor: "Now the step size.",
      runId: "r2",
      criterion: { kind: "explain", statement: "Say what a step size does." },
      answer: null,
      grade: null,
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("useLiveSession — the loop's client side", () => {
  it("answers the turn in front of the learner, not the first one in the transcript", async () => {
    // A session is many turns long by the time most answers are sent. Naming the wrong one is the
    // failure `answeringSeq` exists to prevent, and a one-turn fixture cannot tell the two apart:
    // `turns[0]` and `turns[length - 1]` are the same element.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(OPENED, 201))
      .mockResolvedValueOnce(json(OPENED));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useLiveSession("", "g1"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.answer("A step size scales the move."));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body));
    expect(body).toMatchObject({ answeringSeq: 2 });
  });

  it("will not send a second answer while the first is still being marked", async () => {
    // The surface disables the box while an answer is in flight, but the guard has to hold on its
    // own: a double-submit that reached the server would be refused there (409) after paying for
    // the round trip, and the two writes racing is exactly what the store's compare-and-set had to
    // be built for.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json(OPENED, 201))
      .mockImplementationOnce(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useLiveSession("", "g1"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.answer("First."));
    act(() => result.current.answer("Second, sent too fast."));

    expect(fetchMock).toHaveBeenCalledTimes(2); // the open, and one answer
  });

  it("does not answer a session the director has closed", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(json({ ...OPENED, status: "closed" }, 201)),
    );

    const { result } = renderHook(() => useLiveSession("", "g1"));
    await waitFor(() => expect(result.current.state.status).toBe("ready"));

    act(() => result.current.answer("One more thing?"));

    expect(result.current.state.status).toBe("ready");
  });

  it("abandons an open the learner has walked away from", async () => {
    // The request is aborted on unmount: a session nobody is watching should not keep a connection
    // open, and on the retry path below the abort is what stops two opens from racing.
    const signals: AbortSignal[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.signal) signals.push(init.signal);
        return new Promise<Response>(() => {});
      }),
    );

    const { unmount } = renderHook(() => useLiveSession("", "g1"));
    await waitFor(() => expect(signals).toHaveLength(1));

    unmount();
    expect(signals[0]?.aborted).toBe(true);
  });

  it("does not let an abandoned open overwrite the one that replaced it", async () => {
    // A retry starts a second open and aborts the first — but an abort does not un-send a request
    // that is already on its way back. If the first response were applied when it landed, the
    // learner would be dropped into the session they had just given up on, several seconds after
    // being shown the one they retried into.
    const settle: ((response: Response) => void)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => settle.push(resolve))),
    );

    const { result } = renderHook(() => useLiveSession("", "g1"));
    await waitFor(() => expect(settle).toHaveLength(1));

    act(() => result.current.retry());
    await waitFor(() => expect(settle).toHaveLength(2));

    // The retry lands first, then the abandoned one arrives behind it.
    const second = { ...OPENED, sessionId: "s2" };
    await act(async () => {
      settle[1]?.(json(second, 201));
      settle[0]?.(json({ ...OPENED, sessionId: "s1" }, 201));
    });

    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    const state = result.current.state;
    expect(state.status === "ready" && state.session.sessionId).toBe("s2");
  });
});
