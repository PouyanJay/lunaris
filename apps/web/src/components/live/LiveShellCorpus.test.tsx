import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
vi.mock("../../hooks/useAuth", () => ({
  useAuth: () => ({ user: { email: "owner@example.test", user_metadata: {} } }),
}));
vi.mock("./SessionView", () => ({
  SessionView: ({ graphId }: { graphId: string }) => <p>Teaching {graphId}</p>,
}));
import LiveShell from "./LiveShell";

const digest = "a".repeat(64);
const graph = {
  graphId: "course-graph",
  topic: "Patient data",
  version: 1,
  isAcyclic: true,
  topoOrder: ["privacy"],
  nodes: [
    {
      id: "privacy",
      name: "Privacy",
      definition: "Patient privacy",
      requires: [],
      provenance: "compiled",
      aliases: [],
      teachingSpec: { objective: "Explain privacy", misconceptions: [], depth: "applied" },
      masteryCriteria: [{ kind: "explain", statement: "Explain privacy", needsSim: false }],
      assets: [
        {
          assetId: "privacy-lesson",
          kind: "lesson",
          origin: "ingested",
          locator: "lesson:privacy",
          sourceDigest: digest,
          title: "Privacy",
          excerpt: "Patient privacy",
          sourceLabel: "Patient data",
          clip: null,
          verification: {
            runId: "prepare-1",
            verifierVersion: "mapping-verifier-v1",
            sourceDigest: digest,
          },
        },
      ],
    },
  ],
  corpus: {
    courseId: "course-1",
    title: "Patient data",
    digest,
    runId: "prepare-1",
    adapterVersion: "studio-v1",
    status: "verified",
  },
  groundingReport: {
    sourceDigest: digest,
    runId: "prepare-1",
    status: "passed",
    nodes: [
      { nodeId: "privacy", classification: "source", locators: ["lesson:privacy"], rationale: "" },
    ],
    uncoveredLocators: [],
    omittedLocators: [],
    issues: [],
  },
  mappingReport: {
    sourceDigest: digest,
    runId: "prepare-1",
    status: "passed",
    mapperVersion: "mapping-v1",
    verifierVersion: "mapping-verifier-v1",
    mappings: [
      {
        nodeId: "privacy",
        locator: "lesson:privacy",
        status: "approved",
        reason: "verified",
        evidence: ["Patient privacy"],
      },
    ],
    gaps: [],
    issues: [],
  },
};
function response(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}
function setup(prepared: unknown = graph) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/courses"))
      return response([
        { id: "course-1", topic: "Patient data", courseStatus: "published" },
        { id: "draft", topic: "Draft course", courseStatus: "draft" },
      ]);
    if (url.endsWith("/api/live/graphs") && init?.method === "POST") return response(prepared);
    if (url.includes("/api/live/graphs/")) return response(prepared);
    return new Response(null, { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
afterEach(() => vi.unstubAllGlobals());

it("prepares one published course, reviews the result, then starts only on explicit action", async () => {
  const fetch = setup();
  render(
    <MemoryRouter initialEntries={["/live?source=course"]}>
      <LiveShell apiBaseUrl="https://api.test" />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: /Source course/ }));
  expect(screen.queryByRole("option", { name: "Draft course" })).not.toBeInTheDocument();
  fireEvent.pointerDown(screen.getByRole("option", { name: "Patient data" }));
  fireEvent.click(screen.getByRole("button", { name: "Prepare course" }));
  expect(await screen.findByRole("heading", { name: "Patient data", level: 2 })).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("Ready for review");
  expect(screen.queryByText("Teaching course-graph")).not.toBeInTheDocument();
  expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Start a session" }));
  expect(await screen.findByText("Teaching course-graph")).toBeVisible();
});

it.each(["pending", "failed"])(
  "keeps %s preparation behind review and explicit retry",
  async (status) => {
    setup({ ...graph, corpus: { ...graph.corpus, status } });
    render(
      <MemoryRouter initialEntries={["/live?source=course&course=course-1"]}>
        <LiveShell apiBaseUrl="https://api.test" />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Prepare course" }));
    await screen.findByRole("heading", { name: "Patient data", level: 2 });
    expect(screen.queryByRole("button", { name: "Start a session" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare course" })).toBeEnabled();
  },
);

it("does not admit an existing unverified source graph", async () => {
  setup({ ...graph, mappingReport: null });
  render(
    <MemoryRouter initialEntries={["/live?graph=course-graph"]}>
      <LiveShell apiBaseUrl="https://api.test" />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("button", { name: "Start a session" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("Awaiting verification");
});

it("aborts and ignores an old preparation when the route chooses another source", async () => {
  const fetch = setup();
  let finish!: (response: Response) => void;
  const baseline = fetch.getMockImplementation()!;
  fetch.mockImplementation((input, init) =>
    init?.method === "POST"
      ? new Promise<Response>((resolve) => {
          finish = resolve;
        })
      : baseline(input, init),
  );
  function SwitchSource() {
    const navigate = useNavigate();
    return (
      <button onClick={() => navigate("/live?source=course&course=other")}>
        Choose another source
      </button>
    );
  }
  render(
    <MemoryRouter initialEntries={["/live?source=course&course=course-1"]}>
      <SwitchSource />
      <LiveShell apiBaseUrl="https://api.test" />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Prepare course" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
  );
  const signal = fetch.mock.calls.find(([, init]) => init?.method === "POST")![1]!.signal!;
  fireEvent.click(screen.getByRole("button", { name: "Choose another source" }));
  await act(async () => finish(response(graph)));
  expect(signal.aborted).toBe(true);
  expect(screen.queryByText("Ready for review")).not.toBeInTheDocument();
  expect(screen.queryByText("Teaching course-graph")).not.toBeInTheDocument();
});

it("reprepares the same source and presents a review diff without starting a session", async () => {
  const fetch = setup();
  render(
    <MemoryRouter initialEntries={["/live?graph=course-graph"]}>
      <LiveShell apiBaseUrl="https://api.test" />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("link", { name: "Prepare this course again" }));
  fireEvent.click(await screen.findByRole("button", { name: "Prepare course" }));
  expect(
    await screen.findByRole("region", { name: "Changes since the previous preparation" }),
  ).toHaveTextContent("No source, concept or supporting material changes");
  expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  expect(screen.queryByText("Teaching course-graph")).not.toBeInTheDocument();
});
