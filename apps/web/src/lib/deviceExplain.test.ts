import { describe, expect, it, vi } from "vitest";

import {
  DEVICE_MODEL_ID,
  DeviceExplainEngine,
  type BackendLoader,
  type DeviceProgress,
} from "./deviceExplain";

function fakeLoader(complete = vi.fn(async (_prompt: string) => "On-device words.")) {
  const loads: string[] = [];
  const loader: BackendLoader = async (modelId, onProgress) => {
    loads.push(modelId);
    onProgress({ progress: 0.5, text: "Fetching params (1/2)" });
    onProgress({ progress: 1, text: "Finish loading" });
    return { complete };
  };
  return { loader, loads, complete };
}

describe("DeviceExplainEngine", () => {
  it("loads the pinned model once and reuses it across explains", async () => {
    // Arrange
    const { loader, loads } = fakeLoader();
    const engine = new DeviceExplainEngine(loader);

    // Act — two explains; the multi-GB download must happen exactly once.
    await engine.explain("first block", undefined);
    await engine.explain("second block", undefined);

    // Assert
    expect(loads).toEqual([DEVICE_MODEL_ID]);
  });

  it("forwards download progress while the model loads", async () => {
    // Arrange
    const { loader } = fakeLoader();
    const engine = new DeviceExplainEngine(loader);
    const seen: DeviceProgress[] = [];

    // Act
    await engine.explain("block", undefined, (p) => seen.push(p));

    // Assert — the UI can render a real progress arc, not an indeterminate spinner.
    expect(seen.map((p) => p.progress)).toEqual([0.5, 1]);
  });

  it("prompts with the block's content and context and returns the completion", async () => {
    // Arrange
    const complete = vi.fn(async (_prompt: string) => "It relaxes one edge.");
    const { loader } = fakeLoader(complete);
    const engine = new DeviceExplainEngine(loader);

    // Act
    const explanation = await engine.explain("def relax(edge): ...", "python");

    // Assert — the model saw the content + context; the caller gets the plain answer.
    expect(explanation).toBe("It relaxes one edge.");
    const [prompt] = complete.mock.calls[0] ?? [""];
    expect(prompt).toContain("def relax(edge): ...");
    expect(prompt).toContain("python");
  });

  it("loads only once even when two explains race during the download", async () => {
    // Arrange — a loader that resolves on demand, so both calls start while it's in flight.
    let release: (backend: { complete: () => Promise<string> }) => void;
    const gate = new Promise<{ complete: () => Promise<string> }>((resolve) => {
      release = resolve;
    });
    const loads: string[] = [];
    const loader: BackendLoader = async (modelId) => {
      loads.push(modelId);
      return gate;
    };
    const engine = new DeviceExplainEngine(loader);

    // Act
    const first = engine.explain("a", undefined);
    const second = engine.explain("b", undefined);
    release!({ complete: async () => "done" });
    await Promise.all([first, second]);

    // Assert
    expect(loads).toHaveLength(1);
  });

  it("surfaces a load failure and allows a retry to reload", async () => {
    // Arrange — the first load dies (network drop mid-download); the second succeeds.
    let attempt = 0;
    const loader: BackendLoader = async () => {
      attempt += 1;
      if (attempt === 1) throw new Error("download interrupted");
      return { complete: async () => "recovered" };
    };
    const engine = new DeviceExplainEngine(loader);

    // Act / Assert — the failure propagates; the retry starts a fresh load.
    await expect(engine.explain("block", undefined)).rejects.toThrow("download interrupted");
    await expect(engine.explain("block", undefined)).resolves.toBe("recovered");
  });
});
