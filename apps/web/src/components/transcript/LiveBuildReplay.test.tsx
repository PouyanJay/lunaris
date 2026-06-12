import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainProvider } from "../explain/ExplainContext";
import { makeAgentEvent, makeProgressEvent, makeRunEvent } from "../../test/fixtures";
import { LiveBuildReplay } from "./LiveBuildReplay";

function stubFetch(value: { ok: boolean; status?: number; json?: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, ...value }));
}

function renderLive(runId: string) {
  return render(
    <ExplainProvider apiBaseUrl="http://test" available={false}>
      <LiveBuildReplay apiBaseUrl="http://test" runId={runId} topic="How HTTPS works" />
    </ExplainProvider>,
  );
}

describe("LiveBuildReplay", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reattaches a running build to its live timeline", async () => {
    stubFetch({
      ok: true,
      json: async () => [
        makeRunEvent(0, makeProgressEvent("run_started", 0)),
        makeRunEvent(1, makeAgentEvent("reasoning", 0, { text: "Mapping the prerequisites." })),
        makeRunEvent(2, makeProgressEvent("concepts_extracted", 1, { label: "21 concepts" })),
      ],
    });

    renderLive("run-1");

    // The live timeline renders the in-flight log into the same build-timeline region.
    expect(
      await screen.findByRole("region", { name: /building How HTTPS works/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Mapping the prerequisites.")).toBeInTheDocument();
    expect(screen.getByText("Concepts")).toBeInTheDocument();
  });

  it("shows the pending spine while the run has emitted nothing yet", async () => {
    stubFetch({ ok: true, json: async () => [] });

    renderLive("run-1");

    // An empty live log is "nothing yet", not "no record" — the timeline spine still renders.
    expect(
      await screen.findByRole("region", { name: /building How HTTPS works/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Concepts")).toBeInTheDocument();
  });

  it("shows a reattaching skeleton while the first poll is in flight", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderLive("run-1");

    expect(
      screen.getByRole("status", { name: /reattaching to the live build/i }),
    ).toBeInTheDocument();
  });

  it("surfaces a recoverable error, then retries on Try again", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [makeRunEvent(0, makeProgressEvent("concepts_extracted", 0))],
      });
    vi.stubGlobal("fetch", fetchMock);

    renderLive("run-1");

    const retry = await screen.findByRole("button", { name: /try again/i });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(retry);

    await waitFor(() =>
      expect(screen.getByRole("region", { name: /building How HTTPS works/i })).toBeInTheDocument(),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
