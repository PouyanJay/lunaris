import { vi } from "vitest";

/** A `fetch` that answers every route CopilotKit's browser kit uses, the way Lunaris Live's real
 *  Node runtime does: `/info` listing the `live` agent, an empty event stream for
 *  `/agent/live/connect`, and for `/agent/live/run` a run that starts, carries whatever frames the
 *  test supplies, and finishes. Enough for the real `<CopilotKit>` / `<CopilotChat>` to believe it
 *  is connected and to put real runs on the wire in jsdom, which is what the panel tests inspect
 *  (T7's lesson: assert on what the kit emits and renders, never on the prop meant to produce it).
 *
 *  `runFrames` sees the run's own body, so a test can answer differently to the first and second
 *  send, or echo the message it was sent. */
export function stubCopilotRuntime(
  runFrames: (body: RunBody, runIndex: number) => object[] = () => [],
): void {
  let runs = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/info")) {
        return new Response(
          JSON.stringify({
            version: "1.67.1",
            agents: { live: { name: "live", description: "" } },
            mode: "sse",
          }),
          { status: 200 },
        );
      }
      if (url.endsWith("/agent/live/run")) {
        const body = JSON.parse(String(init?.body)) as RunBody;
        const index = runs++;
        return sse([
          { type: "RUN_STARTED", threadId: body.threadId, runId: body.runId },
          ...runFrames(body, index),
          { type: "RUN_FINISHED", threadId: body.threadId, runId: body.runId },
        ]);
      }
      return sse([]);
    }),
  );
}

/** The AG-UI `RunAgentInput` the kit posts, narrowed to what the panel tests read. */
export interface RunBody {
  threadId: string;
  runId: string;
  messages: { id: string; role: string; content?: unknown }[];
  forwardedProps?: Record<string, unknown>;
}

/** The bodies of every run the kit put on the wire, oldest first. */
export function runsSent(): RunBody[] {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([input]) => String(input).endsWith("/agent/live/run"))
    .map(([, init]) => JSON.parse(String(init?.body)) as RunBody);
}

/** A run's worth of frames for a tutor turn that carries a Tier 1 card: the words, the card as
 *  the `lunaris.surface` tool call under `callId`, and a state frame naming that call as the one
 *  standing. The exact shape `turn_events` produces on the API. */
export function turnWithCard(
  body: RunBody,
  {
    callId,
    card,
    turn,
    words = "Which of these is right?",
    status = "active",
  }: { callId: string; card: object; turn: number; words?: string; status?: string },
): object[] {
  const messageId = `tutor-${callId}`;
  return [
    { type: "TEXT_MESSAGE_START", messageId, role: "assistant" },
    { type: "TEXT_MESSAGE_CONTENT", messageId, delta: words },
    { type: "TEXT_MESSAGE_END", messageId },
    { type: "TOOL_CALL_START", toolCallId: callId, toolCallName: "lunaris.surface" },
    { type: "TOOL_CALL_ARGS", toolCallId: callId, delta: JSON.stringify(card) },
    { type: "TOOL_CALL_END", toolCallId: callId },
    {
      type: "STATE_SNAPSHOT",
      snapshot: {
        sessionId: "sess-1",
        status,
        turn,
        criterion: null,
        grade: null,
        surfaceCallId: callId,
      },
    },
  ].map((frame) => ({ ...frame, threadId: body.threadId }));
}

function sse(frames: object[]): Response {
  return new Response(frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join(""), {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}
