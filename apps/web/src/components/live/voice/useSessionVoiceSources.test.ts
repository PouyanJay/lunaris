import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import type { LiveSession } from "../../../lib/liveSession";
import type { SimExchange } from "../../../lib/simContract";
import { useSessionVoiceSources } from "./useSessionVoiceSources";
const session: LiveSession = {
  sessionId: "s",
  graphId: "g",
  status: "active",
  startedAt: "2026-09-13T00:00:00Z",
  turns: [
    {
      seq: 1,
      runId: "r1",
      tutor: "Try a fraction",
      move: { kind: "introduce", nodeId: "n", reason: "start" },
      answer: null,
      grade: null,
      criterion: null,
      surface: null,
      layout: null,
    },
  ],
};
const reaction = (instanceId: string, sequence: number) =>
  ({ event: { instanceId, sequence }, reaction: { text: "Try that change" } }) as SimExchange;
it("keeps answer identity independent of validated simulator speech", () => {
  const { result, rerender } = renderHook(({ session }) => useSessionVoiceSources(session), {
    initialProps: { session },
  });
  expect(result.current.answerSource).toEqual({ turnSeq: 1, runId: "r1" });
  act(() => result.current.onExchange(reaction("r1", 1)));
  expect(result.current.speechSource).toEqual({ turnSeq: 1, runId: "r1", exchangeSequence: 1 });
  expect(result.current.answerSource).toEqual({ turnSeq: 1, runId: "r1" });
  const oldCallback = result.current.onExchange;
  rerender({ session: { ...session, turns: [{ ...session.turns[0]!, seq: 2, runId: "r2" }] } });
  act(() => oldCallback(reaction("r1", 2)));
  expect(result.current.speechSource).toEqual({ turnSeq: 2, runId: "r2" });
});
it("allows goodbye speech but no closed-session recording", () => {
  const { result } = renderHook(() => useSessionVoiceSources({ ...session, status: "closed" }));
  expect(result.current.answerSource).toBeNull();
  expect(result.current.speechSource).toEqual({ turnSeq: 1, runId: "r1" });
});
