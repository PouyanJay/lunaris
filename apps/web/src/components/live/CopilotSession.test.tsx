import { useRenderToolCall } from "@copilotkit/react-core";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  LAYOUT_TOOL,
  LIVE_AGENT,
  SURFACE_TOOL,
  copilotRuntimeUrl,
  sessionHeaders,
} from "../../lib/copilotRuntime";
import { LAYOUT_CATALOG } from "../../lib/layoutSpec";
import { CopilotSession } from "./CopilotSession";

// The hook is stubbed rather than driven: what needs proving is *what this component registers*,
// which is a pure fact about the call — running CopilotKit's message machinery to observe it would
// test the kit rather than us.
vi.mock("@copilotkit/react-core", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@copilotkit/react-core")>()),
  useRenderToolCall: vi.fn(),
}));

describe("the generative session surface", () => {
  // CopilotKit fetches `${runtimeUrl}/info` the moment the provider mounts. Left unstubbed that is
  // real network I/O from a unit test — which the project's TDD standard forbids outright — and it
  // resolves *after* the test that triggered it has finished, so the resulting `act()` warning gets
  // attributed to whichever test happens to be running next. That is a cross-test leak, not just
  // log noise.
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ agents: {} }), { status: 200 })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** A `fetch` that answers the way the real runtime does: an info the kit can read, listing the
   *  agent it will ask for. The default stub above leaves the kit *unconnected*, which is fine for
   *  tests that only look at what mounts — but a test that waits long enough for the kit to finish
   *  syncing must let it find the agent, or the kit throws "Agent 'live' not found" from an effect
   *  no test awaits: an unhandled error vitest pins on whichever test ran last (the same cross-test
   *  leak T1 fixed once already), and the whole run exits non-zero with every assertion green. */
  function answerAsTheRuntime() {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              version: "1.67.1",
              agents: { live: { name: "live", description: "" } },
              mode: "sse",
            }),
            { status: 200 },
          ),
      ),
    );
  }

  /** A `fetch` that answers every route the kit uses, the way the real runtime does: `/info`
   *  listing the agent, an empty event stream for `/agent/live/connect`, and a run that starts and
   *  finishes at once for `/agent/live/run`. Enough for the kit to believe it is connected and to
   *  put a real run on the wire, which is what the T9 tests below inspect. */
  function answerEveryRoute(
    runFrames: (body: { threadId: string; runId: string }) => object[] = () => [],
  ) {
    const sse = (frames: object[]) =>
      new Response(frames.map((frame) => `data: ${JSON.stringify(frame)}\n\n`).join(""), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url =
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
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
          const body = JSON.parse(String(init?.body)) as { threadId: string; runId: string };
          return sse([
            { type: "RUN_STARTED", threadId: body.threadId, runId: body.runId },
            ...runFrames(body),
            { type: "RUN_FINISHED", threadId: body.threadId, runId: body.runId },
          ]);
        }
        return sse([]);
      }),
    );
  }

  /** The bodies of every run the kit put on the wire. */
  function runsSent(): { forwardedProps?: Record<string, unknown> }[] {
    return vi
      .mocked(fetch)
      .mock.calls.filter(([input]) => String(input).endsWith("/agent/live/run"))
      .map(
        ([, init]) =>
          JSON.parse(String(init?.body)) as { forwardedProps?: Record<string, unknown> },
      );
  }

  it("addresses the runtime's own mount path", () => {
    // The Node runtime answers under /api/copilotkit. Pointed at the bare host, every run 404s.
    expect(copilotRuntimeUrl("http://runtime.test")).toBe("http://runtime.test/api/copilotkit");
  });

  it("tolerates a trailing slash on the configured host", () => {
    // Operators set this in an Azure environment variable by hand, and "http://host/" is what a
    // browser's address bar hands them.
    expect(copilotRuntimeUrl("http://runtime.test/")).toBe("http://runtime.test/api/copilotkit");
  });

  it("asks for the agent the runtime exposes", () => {
    // apps/copilot: LIVE_AGENT = "live". Asserted as a literal on both sides, because the two are
    // separately deployed and nothing at build time sees them drift apart.
    expect(LIVE_AGENT).toBe("live");
  });

  it("registers the tool name the API actually calls", () => {
    // apps/api: SURFACE_TOOL = "lunaris.surface". Asserted as a literal on both sides, because the
    // two are separately deployed and nothing at build time sees them drift apart. A mismatch is a
    // Tier 1 card that never renders while every server-side assertion still passes.
    expect(SURFACE_TOOL).toBe("lunaris.surface");
  });

  it("names the session on every run", () => {
    // The runtime resolves which session to open from this header — it is not decoration, it is
    // the only thing that says whose lesson this is.
    expect(sessionHeaders("sess-5")).toEqual({ "x-lunaris-session-id": "sess-5" });
  });

  it("speaks the route shape the runtime serves: REST routes under the base path", async () => {
    // T7's output verification found the panel had never reached the runtime: the kit's default
    // transport POSTs `{"method": …}` bodies to the bare base path (its "single endpoint" mode),
    // while `apps/copilot` mounts the multi-route shape (`GET …/info`, `POST …/agent/live/run`) —
    // and every request 404'd. Six tasks of curl-driven e2e never noticed because curl spoke the
    // runtime's shape directly. Pinned on what the kit actually *emits* under our configuration,
    // not on the prop that configures it.
    answerAsTheRuntime();
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Anything at all."
        standingSeq={1}
      />,
    );

    const requested = () =>
      vi.mocked(fetch).mock.calls.map(([input, init]) => ({
        method: (init?.method ?? "GET").toUpperCase(),
        url: typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
      }));
    await waitFor(() =>
      expect(requested()).toContainEqual({
        method: "GET",
        url: "http://runtime.test/api/copilotkit/info",
      }),
    );
    expect(requested()).not.toContainEqual(
      expect.objectContaining({ method: "POST", url: "http://runtime.test/api/copilotkit" }),
    );
  });

  it("phones nowhere but the runtime, and mounts no inspector", async () => {
    // Left to its defaults the kit decides by hostname: on localhost it mounts its own inspector
    // (a floating web component in the kit's skin, over our panel) and that inspector fetches
    // announcements from the vendor's CDN. jsdom's hostname is localhost, so this is the exact
    // environment in which the defaults misbehave. Off explicitly: dev and prod behave the same,
    // and a self-hosted deployment carrying learner sessions makes no third-party requests.
    //
    // The kit only reaches for its inspector once it believes it is connected, and it believes
    // that only from a runtime info it can read. On the default stub the defaults this test guards
    // against never fire, so a test on top of it could not fail.
    answerAsTheRuntime();
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Anything at all."
        standingSeq={1}
      />,
    );

    const urls = () =>
      vi
        .mocked(fetch)
        .mock.calls.map(([input]) =>
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        );
    // Once connected the kit connects the agent; the inspector (and its CDN fetch) fires on the
    // same connection event, ahead of it — so by the time the connect is on the wire, a mounted
    // inspector has already shown its hand.
    await waitFor(() =>
      expect(urls()).toContain("http://runtime.test/api/copilotkit/agent/live/connect"),
    );
    expect(new Set(urls().map((url) => new URL(url).host))).toEqual(new Set(["runtime.test"]));
    expect(document.querySelector("cpk-web-inspector")).toBeNull();
  });

  it("names the turn it is answering on every run it sends (T9)", async () => {
    // AD10 left the answered turn derived server-side over AG-UI, and AD22 parked the consequence:
    // a late answer to a card the thread still shows is graded against whatever question is up
    // now. The API now reads `forwardedProps.answeringSeq` and refuses a moved-on turn with REST's
    // 409, but only if the browser names it. Pinned on the run body the kit actually *emits*, not
    // on the prop that is meant to produce it (T7's lesson: the kit's transport is what the API
    // sees, and a prop the kit ignores would leave every other test green).
    answerEveryRoute();
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
        standingSeq={3}
      />,
    );
    // The composer unlocks once the kit has found the agent; a send before that is dropped.
    const box = await screen.findByRole("textbox", { name: /your answer/i });
    await waitFor(() => expect(box).toBeEnabled());

    fireEvent.change(box, { target: { value: "Downhill." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });

    await waitFor(() => expect(runsSent()).toHaveLength(1));
    expect(runsSent()[0]?.forwardedProps?.answeringSeq).toBe(3);
  });

  it("names nothing when it has no turn to name", async () => {
    // A session with nothing standing (closed, or unreadable) is not answering anything, and a
    // guessed seq would be refused as stale, or accepted, against a turn this browser never saw.
    // The API derives the standing turn when nothing is named, which is every pre-T9 client.
    answerEveryRoute();
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn={null}
        standingSeq={null}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /your answer/i });
    await waitFor(() => expect(box).toBeEnabled());

    fireEvent.change(box, { target: { value: "Downhill." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });

    await waitFor(() => expect(runsSent()).toHaveLength(1));
    expect(runsSent()[0]?.forwardedProps).not.toHaveProperty("answeringSeq");
  });

  it("names the turn the last state frame said is up, not the one it mounted with", async () => {
    // The whole point. The REST read that seeded `standingSeq` never re-reads, so after the first
    // turn it names a question that is no longer up, and the API would refuse every later send
    // as stale (409). The run's own `STATE_SNAPSHOT` carries the turn now in front of the learner
    // (`SessionSnapshot.turn`), and it has to win from then on.
    answerEveryRoute(() => [{ type: "STATE_SNAPSHOT", snapshot: { turn: 4, status: "active" } }]);
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
        standingSeq={3}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /your answer/i });
    await waitFor(() => expect(box).toBeEnabled());

    fireEvent.change(box, { target: { value: "Downhill." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await waitFor(() => expect(runsSent()).toHaveLength(1));
    // The composer locks for the run and unlocks when it settles; the second send waits for that.
    await waitFor(() => expect(box).toBeEnabled());
    fireEvent.change(box, { target: { value: "Still downhill." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await waitFor(() => expect(runsSent()).toHaveLength(2));

    expect(runsSent().map((run) => run.forwardedProps?.answeringSeq)).toEqual([3, 4]);
  });

  it("forgets the named turn when it is re-used for another session", async () => {
    // The turn it learned from one session's state frames must not name the next session's
    // answers: a re-used panel falls back to what the new session's REST read says is standing.
    answerEveryRoute(() => [{ type: "STATE_SNAPSHOT", snapshot: { turn: 4, status: "active" } }]);
    const view = render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
        standingSeq={3}
      />,
    );
    const box = await screen.findByRole("textbox", { name: /your answer/i });
    await waitFor(() => expect(box).toBeEnabled());
    fireEvent.change(box, { target: { value: "Downhill." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    await waitFor(() => expect(runsSent()).toHaveLength(1));
    await waitFor(() => expect(box).toBeEnabled());

    view.rerender(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-2"
        topic="Neural networks"
        standingTurn="A different question."
        standingSeq={7}
      />,
    );
    const nextBox = await screen.findByRole("textbox", { name: /your answer/i });
    await waitFor(() => expect(nextBox).toBeEnabled());
    fireEvent.change(nextBox, { target: { value: "Uphill." } });
    fireEvent.keyDown(nextBox, { key: "Enter", metaKey: true });
    await waitFor(() => expect(runsSent()).toHaveLength(2));

    expect(runsSent()[1]?.forwardedProps?.answeringSeq).toBe(7);
  });

  it("tells the learner when the generative surface is not configured", () => {
    // A blank panel would read as a broken session. Live still works without the runtime — P2a's
    // transcript uses REST — so this has to say which half is missing.
    render(
      <CopilotSession
        runtimeUrl={undefined}
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
        standingSeq={1}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/not configured/i);
  });

  it("opens on the question the learner is actually being marked on", () => {
    // T2 makes a message sent here take a real turn, graded against the criterion the *standing*
    // turn staged. A chat that opened empty would therefore invite an answer to a question the
    // learner had never been shown — and the grader's verdict would look arbitrary to them.
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step to lower the loss?"
        standingSeq={1}
      />,
    );

    expect(screen.getByText(/Which way would you step to lower the loss\?/)).toBeInTheDocument();
  });

  it("opens on nothing at all when the session has nothing standing", () => {
    // A closed session, or one whose turn could not be read. Seeding the chat with an empty string
    // would render a blank tutor row, which reads as a tutor that said nothing.
    //
    // Asserted on the *absence of any tutor message*, not on the composer: the composer is
    // rendered by `<CopilotChat/>` unconditionally, so a test looking at it stays green even when a
    // label is passed — which is the exact defect it exists to catch, and which review caught it
    // committing.
    const { container } = render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn={null}
        standingSeq={1}
      />,
    );

    expect(container.querySelector('[data-speaker="tutor"]')).toBeNull();
    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeInTheDocument();
  });

  it("renders the standing turn as the tutor's own words, in our slot and not the kit's", () => {
    // The other half of the pair: a seeded turn has to arrive as a tutor message, not as text
    // loose on the page. Driven through the *real* `<CopilotChat/>` so that what is proven is
    // that the kit hands its assistant message to our `TutorMessage` slot (T7, AD1) — the kit's
    // own bubble class must be gone, or the re-skin registered a slot the kit is not using.
    const { container } = render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
        standingSeq={1}
      />,
    );

    expect(container.querySelector('[data-speaker="tutor"]')).toHaveTextContent(
      "Which way would you step?",
    );
    expect(container.querySelector(".copilotKitAssistantMessage")).toBeNull();
  });

  it("mounts the chat surface when it is configured, with our composer and not the kit's", () => {
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Anything at all."
        standingSeq={1}
      />,
    );

    // Asserted on the composer, not on our `<section aria-label>` wrapper. The wrapper is rendered
    // unconditionally by this component, so a test looking at it passes even with `<CopilotChat />`
    // deleted outright — which is the single thing T1 exists to prove. Mutation testing caught
    // exactly that. From T7 the composer is our own answer form, handed to the kit as its `Input`
    // slot; the kit's textarea (`copilot-chat-textarea`) must be gone, or the slot is registered
    // but unused.
    expect(screen.getByRole("textbox", { name: /your answer/i })).toBeInTheDocument();
    expect(screen.queryByTestId("copilot-chat-textarea")).not.toBeInTheDocument();
  });

  it("is absent from the session surface until a runtime is configured", async () => {
    // The whole rollout rests on this: `VITE_COPILOT_URL` is unset everywhere today, so adding the
    // generative surface must change nothing a learner sees. If this ever inverts, P2a's working
    // transcript has been replaced by a chat that cannot yet take a turn.
    const { SessionView } = await import("./SessionView");
    render(<SessionView apiBaseUrl="http://api.test" graphId="g1" topic="Neural networks" />);

    // Awaited rather than asserted immediately: `SessionView` opens a session on mount, and that
    // fetch settles after this test's body would otherwise have ended — landing an `act()` warning
    // on whichever test happened to be running next. That is a cross-test leak, which this file
    // has already been bitten by once (T1's unstubbed `/info` fetch).
    await waitFor(() => expect(screen.queryByText(/not configured/i)).not.toBeInTheDocument());
  });
});

describe("the Tier 1 card inside the generative panel", () => {
  const QUIZ = {
    kind: "quiz_card" as const,
    nodeId: "gradient",
    concept: "Gradient",
    question: "Which of these is actually true about Gradient?",
    options: ["The slope of the loss.", "How big the loss is."],
  };

  /** The tool config `SurfaceTool` registered, captured without a live runtime.
   *
   *  `useRenderToolCall` is a plain hook, so mounting the panel is enough to record what it was
   *  asked to render — no message store, no socket, no agent. That matters because this seam has
   *  had no test at all, and AD14 names its worst failure exactly: a card that silently never
   *  renders, with every server-side assertion still passing. */
  function registeredTool(name: string) {
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Anything at all."
        standingSeq={1}
      />,
    );
    // Looked up by name rather than by position. The panel registers two renderers from T5 (the
    // card and its layout), and an index would quietly start asserting about the wrong one the
    // first time a third is added or the two are reordered.
    const config = vi
      .mocked(useRenderToolCall)
      .mock.calls.map((call) => call[0])
      .find((registered) => registered.name === name);
    expect(config, `nothing registered a renderer for ${name}`).toBeDefined();
    return config!;
  }

  it("registers under the name the API actually calls", () => {
    expect(registeredTool(SURFACE_TOOL).name).toBe(SURFACE_TOOL);
  });

  it("draws the card the tool call carries", () => {
    const tool = registeredTool(SURFACE_TOOL);

    render(tool.render({ args: QUIZ } as never) as ReactElement);

    expect(screen.getByRole("radiogroup", { name: QUIZ.question })).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(2);
  });

  it("draws it as a record, with no way to answer in this panel", () => {
    // Deliberate, and the reason is in the component's own docstring: CopilotKit re-renders every
    // tool call in the thread, so an answerable card would outlive its turn — and the AG-UI path
    // derives the answered turn server-side, so a late answer would be graded against whatever
    // question is up now rather than refused. T9 is where that becomes nameable on this transport.
    //
    // Scoped to the card, because the panel around it has a composer of its own with a Send button.
    // A document-wide query finds *that* one and reports the opposite of what it is asked.
    const tool = registeredTool(SURFACE_TOOL);

    const card = render(tool.render({ args: QUIZ } as never) as ReactElement);

    expect(within(card.container).queryByRole("button")).not.toBeInTheDocument();
    expect(within(card.container).getByRole("radio", { name: QUIZ.options[0]! })).toBeDisabled();
  });

  it("registers a second renderer for the turn's Tier 2 layout", () => {
    // Its own registration, mirroring the two tool calls the API sends. A build that drew the card
    // and not the layout still assesses the learner correctly — which is exactly why the failure is
    // quiet, and why it needs its own assertion rather than riding on the card's.
    expect(registeredTool(LAYOUT_TOOL).name).toBe(LAYOUT_TOOL);
    expect(LAYOUT_TOOL).toBe("lunaris.layout");
  });

  it("draws the composition the layout tool call carries", () => {
    const tool = registeredTool(LAYOUT_TOOL);

    const drawn = render(
      tool.render({
        args: {
          catalogId: LAYOUT_CATALOG,
          blocks: [
            { component: "Stack", id: "root", children: ["hint"] },
            { component: "Hint", id: "hint", hint: "The sign is the direction." },
          ],
        },
      } as never) as ReactElement,
    );

    expect(within(drawn.container).getByText("The sign is the direction.")).toBeInTheDocument();
  });
});
