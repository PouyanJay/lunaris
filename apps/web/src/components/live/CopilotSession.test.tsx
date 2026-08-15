import { useRenderToolCall } from "@copilotkit/react-core";
import { render, screen, waitFor, within } from "@testing-library/react";
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

  it("tells the learner when the generative surface is not configured", () => {
    // A blank panel would read as a broken session. Live still works without the runtime — P2a's
    // transcript uses REST — so this has to say which half is missing.
    render(
      <CopilotSession
        runtimeUrl={undefined}
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
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
      />,
    );

    expect(screen.getByText(/Which way would you step to lower the loss\?/)).toBeInTheDocument();
  });

  it("opens on nothing at all when the session has nothing standing", () => {
    // A closed session, or one whose turn could not be read. Seeding the chat with an empty string
    // would render a blank assistant bubble, which reads as a tutor that said nothing.
    //
    // Asserted on the *absence of any assistant bubble*, not on the composer: the composer is
    // rendered by `<CopilotChat/>` unconditionally, so a test looking at it stays green even when a
    // label is passed — which is the exact defect it exists to catch, and which review caught it
    // committing. The class is the kit's own, and that coupling is deliberate rather than
    // incidental: it is the same seam T7 re-skins, so a version bump that renames it should fail
    // here rather than silently stop checking anything.
    const { container } = render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn={null}
      />,
    );

    expect(container.querySelector(".copilotKitAssistantMessage")).toBeNull();
    expect(screen.getByTestId("copilot-chat-textarea")).toBeInTheDocument();
  });

  it("renders the standing turn as the tutor's own message", () => {
    // The other half of the pair, and the reason the class above is the right thing to look at: a
    // seeded turn has to arrive as an assistant bubble, not as text loose on the page.
    const { container } = render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Which way would you step?"
      />,
    );

    expect(container.querySelector(".copilotKitAssistantMessage")).not.toBeNull();
  });

  it("mounts the chat surface when it is configured", () => {
    render(
      <CopilotSession
        runtimeUrl="http://runtime.test"
        sessionId="sess-1"
        topic="Neural networks"
        standingTurn="Anything at all."
      />,
    );

    // Asserted on the kit's own composer, not on our `<section aria-label>` wrapper. The wrapper is
    // rendered unconditionally by this component, so a test looking at it passes even with
    // `<CopilotChat />` deleted outright — which is the single thing T1 exists to prove. Mutation
    // testing caught exactly that.
    expect(screen.getByTestId("copilot-chat-textarea")).toBeInTheDocument();
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
