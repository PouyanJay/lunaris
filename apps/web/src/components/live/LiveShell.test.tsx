import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import LiveShell from "./LiveShell";

const GRAPH = {
  graphId: "g1",
  topic: "How neural networks learn",
  version: 1,
  nodes: [
    { id: "a", name: "Derivative as slope", definition: "How steeply…", requires: [] },
    { id: "b", name: "Gradient", definition: "The slope of the loss…", requires: ["a"] },
  ],
  topoOrder: ["a", "b"],
  isAcyclic: true,
};

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
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => GRAPH })),
    );

    renderLive("How neural networks learn");

    expect(await screen.findByText("Derivative as slope")).toBeInTheDocument();
    expect(screen.getByText("Gradient")).toBeInTheDocument();
  });

  it("says it is working while the map compiles", async () => {
    // A compile takes minutes, so the waiting state is the state a learner sees most of all.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );

    renderLive("Tides");

    expect(await screen.findByRole("status")).toHaveTextContent(/working out/i);
  });

  it("offers a way forward when the compile fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500, text: async () => "boom" })),
    );

    renderLive("Tides");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't build the map/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
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
});
