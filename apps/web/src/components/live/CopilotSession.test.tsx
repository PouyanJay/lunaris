import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LIVE_AGENT, copilotRuntimeUrl, sessionHeaders } from "../../lib/copilotRuntime";
import { CopilotSession } from "./CopilotSession";

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

    expect(
      screen.getByText(/Which way would you step to lower the loss\?/),
    ).toBeInTheDocument();
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

    expect(screen.queryByText(/not configured/i)).not.toBeInTheDocument();
  });
});

