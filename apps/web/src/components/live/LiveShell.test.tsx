import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import LiveShell from "./LiveShell";

const NODES = [
  {
    id: "a",
    name: "Derivative as slope",
    definition: "How steeply a quantity changes.",
    requires: [],
    provenance: "compiled",
    aliases: ["rate of change"],
    teachingSpec: {
      objective: "Read a slope off a curve.",
      misconceptions: ["A derivative is just a fraction."],
      depth: "intuition_first",
    },
    masteryCriteria: [
      { kind: "predict", statement: "Say which way the curve turns.", needsSim: false },
      { kind: "manipulate", statement: "Steepen the curve and explain.", needsSim: true },
    ],
  },
  {
    id: "b",
    name: "Gradient",
    definition: "The slope of the loss surface.",
    requires: ["a"],
    provenance: "compiled",
    aliases: [],
    teachingSpec: null,
    masteryCriteria: [],
  },
];

const GRAPH = {
  graphId: "g1",
  topic: "How neural networks learn",
  version: 1,
  nodes: NODES,
  topoOrder: ["a", "b"],
  isAcyclic: true,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A fetch that answers each Live route with what the API would: the graph read for a map the
 *  learner already has, and the session open. Records every request so a test can assert what
 *  was NOT asked for — a compile in front of the interview would be the whole thing this task
 *  removes coming back. */
function liveApi(overrides: { session?: Response; graph?: Response } = {}) {
  const calls: { url: string; body: unknown }[] = [];
  const impl = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
    // The open only (`POST …/sessions`), never a turn or a re-read: a stub answering every session
    // route with the opened session would hand a T2 test the wrong shape without saying so.
    if (url.endsWith("/api/live/sessions")) {
      return Promise.resolve(overrides.session ?? json(PLACING, 201));
    }
    if (url.includes("/api/live/graphs/")) {
      return Promise.resolve(overrides.graph ?? json(GRAPH));
    }
    return Promise.resolve(new Response("no route", { status: 404 }));
  });
  vi.stubGlobal("fetch", impl);
  return calls;
}

/** A session as the placement path returns it (P2c): opened on the topic, no map yet, the
 *  interviewer's first question in front of the learner and nothing staged. */
const PLACING = {
  sessionId: "s2",
  graphId: "g-pending",
  topic: "How neural networks learn",
  status: "placing",
  startedAt: "2026-08-19T09:00:00Z",
  turns: [
    {
      seq: 1,
      move: { kind: "place", nodeId: null, reason: "The map is still being built." },
      tutor: "Before we start on how neural networks learn: what have you already met of it?",
      runId: "r1",
      criterion: null,
      answer: null,
      grade: null,
      surface: null,
      layout: null,
    },
  ],
};

/** A session as the sessions endpoint returns it — a different shape entirely from the compile's
 *  stream, which is the point: the two calls have to be told apart. */
const SESSION = {
  sessionId: "s1",
  graphId: "g1",
  status: "active",
  startedAt: "2026-08-09T21:00:00Z",
  turns: [
    {
      seq: 1,
      move: { kind: "introduce", nodeId: "a", reason: "Nothing precedes it." },
      tutor: "Picture the loss as a hillside.",
      runId: "r1",
      criterion: { kind: "explain", statement: "Explain it back." },
      answer: null,
      grade: null,
    },
  ],
};

function renderLive(topic: string) {
  return render(
    <MemoryRouter initialEntries={[`/live?topic=${encodeURIComponent(topic)}`]}>
      <LiveShell apiBaseUrl="http://test" />
    </MemoryRouter>,
  );
}

/** A learner's own sessions: Live's first sub-route (T2). */
function onTheSessionsRoute() {
  return render(
    <MemoryRouter initialEntries={["/live/sessions"]}>
      <LiveShell apiBaseUrl="http://test" />
    </MemoryRouter>,
  );
}

/** The map of a graph the learner already has: the way in that P2a/P2b's opening keeps. */
function renderMap(graphId = "g1") {
  return render(
    <MemoryRouter initialEntries={[`/live?graph=${encodeURIComponent(graphId)}`]}>
      <LiveShell apiBaseUrl="http://test" />
    </MemoryRouter>,
  );
}

describe("LiveShell — a topic opens a session, not a compile", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("opens a session on the topic it was sent and shows the first question, with no compile in front", async () => {
    // Plan §6, U5: the moment a topic arrives the learner is being talked to. What was here before
    // — a progress screen for the compile, then a map, then a button — is gone; the compile still
    // happens, behind the session, where the learner cannot see it.
    const calls = liveApi();

    renderLive("How neural networks learn");

    expect(await screen.findByText(/what have you already met of it/i)).toBeInTheDocument();
    // The interview is answered where every turn is answered.
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    // Exactly one request went out, and it opened a session on the topic — not a compile.
    expect(calls.map((call) => call.url)).toEqual(["http://test/api/live/sessions"]);
    expect(calls[0]?.body).toEqual({ topic: "How neural networks learn" });
  });

  it("asks for a topic rather than opening nothing", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    render(
      <MemoryRouter initialEntries={["/live"]}>
        <LiveShell apiBaseUrl="http://test" />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("link", { name: /name a topic/i })).toBeInTheDocument();
    await waitFor(() => expect(fetchSpy).not.toHaveBeenCalled());
  });

  it("offers a way forward when the session cannot open", async () => {
    liveApi({
      session: json({ detail: "You have opened as many sessions as today allows." }, 429),
    });

    renderLive("Tides");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/as many sessions as today allows/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("LiveShell — the concept's teaching notes", () => {
  afterEach(() => vi.unstubAllGlobals());

  async function openFirstConcept() {
    liveApi();
    renderMap();
    const concept = await screen.findByRole("button", { name: "Derivative as slope" });
    fireEvent.click(concept);
    return screen.getByRole("complementary");
  }

  it("opens the notes for the concept the learner picks", async () => {
    const panel = await openFirstConcept();

    // What the node says about itself is what Phase 2 teaches from — so it is what the map shows.
    expect(within(panel).getByText("Read a slope off a curve.")).toBeInTheDocument();
    expect(within(panel).getByText(/a derivative is just a fraction/i)).toBeInTheDocument();
    expect(within(panel).getByText(/say which way the curve turns/i)).toBeInTheDocument();
  });

  it("marks the criteria that need a simulator, because Phase 3 has to find them", async () => {
    const panel = await openFirstConcept();

    const criterion = within(panel)
      .getByText(/steepen the curve/i)
      .closest("li");
    expect(criterion).not.toBeNull();
    expect(within(criterion as HTMLElement).getByText(/needs a simulator/i)).toBeInTheDocument();
  });

  it("names what the concept needs first, in the learner's language not in ids", async () => {
    liveApi();
    renderMap();
    fireEvent.click(await screen.findByRole("button", { name: "Gradient" }));

    const panel = screen.getByRole("complementary");
    expect(within(panel).getByText("Derivative as slope")).toBeInTheDocument();
  });

  it("says so when a concept's notes failed rather than showing an empty panel", async () => {
    // The compiler keeps a concept whose authoring call failed — losing the map over one failed
    // call would be worse. The surface has to be honest about which one that was.
    liveApi();
    renderMap();
    fireEvent.click(await screen.findByRole("button", { name: "Gradient" }));

    expect(
      within(screen.getByRole("complementary")).getByText(/no teaching notes/i),
    ).toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the concept it came from", async () => {
    liveApi();
    renderMap();
    const concept = await screen.findByRole("button", { name: "Derivative as slope" });
    fireEvent.click(concept);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(concept).toHaveFocus();
  });
});

describe("LiveShell — a map the learner already has", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the map it was sent to", async () => {
    liveApi();
    renderMap();
    expect(await screen.findByRole("button", { name: "Derivative as slope" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gradient" })).toBeInTheDocument();
  });

  it("says so, in the server's words, when the map is not there", async () => {
    liveApi({ graph: json({ detail: "Map not found" }, 404) });
    renderMap("gone");
    expect(await screen.findByRole("alert")).toHaveTextContent(/map not found/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("offers a session on the map, opened on the map's id, and can come back to it", async () => {
    // U1 adds a way in; it does not move the first. A session started from a map the learner
    // already has opens on the graph id — teaching from turn 1 — and the map is still there to
    // come back to.
    const calls = liveApi({ session: json(SESSION, 201) });
    renderMap();

    fireEvent.click(await screen.findByRole("button", { name: /start a session/i }));

    expect(await screen.findByText(/picture the loss as a hillside/i)).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: /session on how neural networks learn/i }),
    ).toBeInTheDocument();
    expect(calls.find((call) => call.url.endsWith("/api/live/sessions"))?.body).toEqual({
      graphId: "g1",
    });

    fireEvent.click(screen.getByRole("button", { name: /back to the map/i }));
    expect(await screen.findByRole("button", { name: /start a session/i })).toBeInTheDocument();
  });
});

describe("the sessions route", () => {
  it("lists the learner's sessions rather than opening one", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify([
              {
                sessionId: "s1",
                graphId: "g1",
                topic: "How neural networks learn",
                status: "active",
                turnCount: 6,
                startedAt: "2026-08-19T09:00:00Z",
                updatedAt: "2026-08-19T09:40:00Z",
              },
            ]),
            { status: 200, headers: { "content-type": "application/json" } },
          ),
        ),
      ),
    );

    onTheSessionsRoute();

    // The route is the assertion: a path under /live must reach Live's own screen and never fall
    // through to the idle state, which is what an unrouted sub-path would do.
    expect(await screen.findByRole("heading", { name: /your sessions/i })).toBeInTheDocument();
    expect(await screen.findByRole("listitem")).toHaveTextContent("How neural networks learn");
  });
});
