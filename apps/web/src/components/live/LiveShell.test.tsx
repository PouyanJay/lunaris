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

/** A fetch that streams `frames` as SSE, exactly as the compile endpoint does.
 *
 *  `keepOpen` leaves the connection hanging after the last frame — which is what a compile still
 *  running actually looks like. Closing it instead is a *finished* compile, and one that ended
 *  without a map is a failure, so a progress-only fixture has to hold the line open or the surface
 *  under test is the error state rather than the one being asserted. */
function streamingFetch(frames: string[], { keepOpen = false } = {}): typeof fetch {
  return (() => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        for (const frame of frames) controller.enqueue(encoder.encode(frame));
        if (!keepOpen) controller.close();
      },
    });
    return Promise.resolve(
      new Response(body, {
        headers: { "content-type": "text/event-stream", "x-run-id": "r1" },
      }),
    );
  }) as unknown as typeof fetch;
}

const READY = [`event: graph\ndata: ${JSON.stringify(GRAPH)}\n\n`];

function renderLive(topic: string) {
  return render(
    <MemoryRouter initialEntries={[`/live?topic=${encodeURIComponent(topic)}`]}>
      <LiveShell apiBaseUrl="http://test" />
    </MemoryRouter>,
  );
}

describe("LiveShell — the concept map", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("compiles the topic it was sent and renders the concepts", async () => {
    vi.stubGlobal("fetch", streamingFetch(READY));

    renderLive("How neural networks learn");

    expect(await screen.findByRole("button", { name: "Derivative as slope" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gradient" })).toBeInTheDocument();
  });

  it("asks for a topic rather than compiling nothing", async () => {
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

  it("offers a way forward when the compile fails", async () => {
    vi.stubGlobal(
      "fetch",
      streamingFetch([
        'event: error\ndata: {"message":"Couldn\'t map this topic. Try again, or rephrase it.","runId":"r1"}\n\n',
      ]),
    );

    renderLive("Tides");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/rephrase it/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("LiveShell — watching the compile", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("says what it is doing before there is anything to count", async () => {
    // Decomposition is one long call with no countable unit. A bar stuck at zero for a minute reads
    // as a stall, so this stretch is narrated rather than measured.
    vi.stubGlobal(
      "fetch",
      streamingFetch(
        [
          'event: progress\ndata: {"phase":"decomposing","done":0,"total":0}\n\n',
          // …and then nothing, so the surface stays in this phase.
        ],
        { keepOpen: true },
      ),
    );

    renderLive("Tides");

    const status = await screen.findByRole("status");
    await waitFor(() => expect(status).toHaveTextContent(/working out which ideas/i));
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("counts the concepts off as they are written", async () => {
    // The whole point of streaming the compile: a real measure of a three-minute wait.
    vi.stubGlobal(
      "fetch",
      streamingFetch(
        [
          'event: progress\ndata: {"phase":"decomposing","done":0,"total":0}\n\n',
          'event: progress\ndata: {"phase":"authoring","done":3,"total":12}\n\n',
        ],
        { keepOpen: true },
      ),
    );

    renderLive("Tides");

    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(await screen.findByText(/3\s*\/\s*12/)).toBeInTheDocument();
  });
});

describe("LiveShell — a compile whose stream drops", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("re-reads the map on retry instead of paying for the compile a second time", async () => {
    // A three-minute stream is a long time for a proxy to keep a connection open. The compile
    // itself survives the drop server-side, so retrying has to try the map it was already told the
    // id of before it spends another three minutes building the same thing.
    const encoder = new TextEncoder();
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL) => {
        calls.push(String(url));
        if (String(url).includes("/stream")) {
          // Progress, then the connection dies without a terminal frame.
          return Promise.resolve(
            new Response(
              new ReadableStream({
                start(controller) {
                  controller.enqueue(
                    encoder.encode(
                      'event: progress\ndata: {"phase":"authoring","done":2,"total":9}\n\n',
                    ),
                  );
                  controller.close();
                },
              }),
              {
                headers: {
                  "content-type": "text/event-stream",
                  "x-run-id": "r1",
                  "x-graph-id": "g1",
                },
              },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify(GRAPH)));
      }),
    );

    renderLive("How neural networks learn");
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    // The map arrives from a plain read of the graph the dropped compile had already been given.
    expect(await screen.findByRole("button", { name: "Gradient" })).toBeInTheDocument();
    expect(calls.filter((url) => url.includes("/stream"))).toHaveLength(1);
    expect(calls.at(-1)).toContain("/api/live/graphs/g1");
  });

  it("compiles again when the dropped compile never landed", async () => {
    // The re-read is an optimisation, not a guarantee: the compile may have failed on the server
    // too. A 404 must fall back to compiling rather than stranding the learner on an error.
    const encoder = new TextEncoder();
    let streams = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string | URL) => {
        if (String(url).includes("/stream")) {
          streams += 1;
          const frames = streams === 1 ? [] : [`event: graph\ndata: ${JSON.stringify(GRAPH)}\n\n`];
          return Promise.resolve(
            new Response(
              new ReadableStream({
                start(controller) {
                  for (const frame of frames) controller.enqueue(encoder.encode(frame));
                  controller.close();
                },
              }),
              {
                headers: {
                  "content-type": "text/event-stream",
                  "x-run-id": "r1",
                  "x-graph-id": "g1",
                },
              },
            ),
          );
        }
        return Promise.resolve(new Response("Graph not found", { status: 404 }));
      }),
    );

    renderLive("How neural networks learn");
    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    expect(await screen.findByRole("button", { name: "Gradient" })).toBeInTheDocument();
    expect(streams).toBe(2);
  });
});

describe("LiveShell — the concept's teaching notes", () => {
  afterEach(() => vi.unstubAllGlobals());

  async function openFirstConcept() {
    vi.stubGlobal("fetch", streamingFetch(READY));
    renderLive("How neural networks learn");
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
    vi.stubGlobal("fetch", streamingFetch(READY));
    renderLive("How neural networks learn");
    fireEvent.click(await screen.findByRole("button", { name: "Gradient" }));

    const panel = screen.getByRole("complementary");
    expect(within(panel).getByText("Derivative as slope")).toBeInTheDocument();
  });

  it("says so when a concept's notes failed rather than showing an empty panel", async () => {
    // The compiler keeps a concept whose authoring call failed — losing the map over one failed
    // call would be worse. The surface has to be honest about which one that was.
    vi.stubGlobal("fetch", streamingFetch(READY));
    renderLive("How neural networks learn");
    fireEvent.click(await screen.findByRole("button", { name: "Gradient" }));

    expect(
      within(screen.getByRole("complementary")).getByText(/no teaching notes/i),
    ).toBeInTheDocument();
  });

  it("closes on Escape and returns focus to the concept it came from", async () => {
    vi.stubGlobal("fetch", streamingFetch(READY));
    renderLive("How neural networks learn");
    const concept = await screen.findByRole("button", { name: "Derivative as slope" });
    fireEvent.click(concept);

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(concept).toHaveFocus();
  });
});
