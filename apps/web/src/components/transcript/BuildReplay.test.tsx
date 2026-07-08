import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainProvider } from "../explain/ExplainContext";
import { makeAgentEvent, makeProgressEvent, makeRunEvent } from "../../test/fixtures";
import { BuildReplay } from "./BuildReplay";

function stubFetch(value: { ok: boolean; status?: number; json?: () => Promise<unknown> }) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, ...value }));
}

function renderReplay(runId: string | undefined) {
  return render(
    <ExplainProvider apiBaseUrl="http://test" available={false}>
      <BuildReplay apiBaseUrl="http://test" runId={runId} topic="How HTTPS works" />
    </ExplainProvider>,
  );
}

describe("BuildReplay", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("replays the persisted log into the build timeline", async () => {
    stubFetch({
      ok: true,
      json: async () => [
        makeRunEvent(0, makeProgressEvent("run_started", 0)),
        makeRunEvent(1, makeAgentEvent("reasoning", 0, { text: "Planning the build…" })),
        makeRunEvent(2, makeProgressEvent("concepts_extracted", 1, { label: "21 concepts" })),
        makeRunEvent(3, makeProgressEvent("run_completed", 2)),
      ],
    });

    renderReplay("run-1");

    // The static timeline renders every pipeline phase from the persisted log.
    await waitFor(() => expect(screen.getByText("Concepts")).toBeInTheDocument());
    const phases = ["Start", "Concepts", "Graph", "Curriculum", "Lessons", "Verify", "Publish"];
    for (const label of phases) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("renders the control room with the transcript one toggle away, never claiming live", async () => {
    // Replay parity (P8): the same lens as the live build — but a still log has no live dot,
    // and the completed run reads every phase done.
    stubFetch({
      ok: true,
      json: async () => [
        makeRunEvent(0, makeProgressEvent("run_started", 0)),
        makeRunEvent(1, makeProgressEvent("claims_verified", 1)),
        makeRunEvent(2, makeProgressEvent("run_completed", 2)),
      ],
    });

    renderReplay("run-1");

    await waitFor(() =>
      expect(screen.getByRole("region", { name: /building how https works/i })).toBeInTheDocument(),
    );
    expect(screen.queryByText("live")).not.toBeInTheDocument();
    const pipeline = screen.getByRole("region", { name: /pipeline/i });
    expect(pipeline.querySelector('[data-status="active"]')).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: "Transcript" }));
    expect(screen.getByRole("radio", { name: "Transcript" })).toBeChecked();
  });

  it("shows a loading skeleton while the log is in flight", () => {
    // A never-resolving fetch keeps the hook in its loading state.
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    renderReplay("run-1");

    expect(screen.getByRole("status", { name: /loading build record/i })).toBeInTheDocument();
  });

  it("shows a 'no build record' state when the run left no log", async () => {
    stubFetch({ ok: true, json: async () => [] });

    renderReplay("run-1");

    await waitFor(() => expect(screen.getByText(/no build record/i)).toBeInTheDocument());
  });

  it("shows the empty state without fetching when there is no runId", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    renderReplay(undefined);

    await waitFor(() => expect(screen.getByText(/no build record/i)).toBeInTheDocument());
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("surfaces a recoverable error, then retries the fetch on Try again", async () => {
    // First load fails (503); the retry succeeds and renders the timeline.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          makeRunEvent(0, makeProgressEvent("run_started", 0)),
          makeRunEvent(1, makeProgressEvent("concepts_extracted", 1, { label: "21 concepts" })),
        ],
      });
    vi.stubGlobal("fetch", fetchMock);

    renderReplay("run-1");

    const retry = await screen.findByRole("button", { name: /try again/i });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fireEvent.click(retry);

    await waitFor(() => expect(screen.getByText("Concepts")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
