import { describe, expect, it, vi } from "vitest";

import {
  DEVICE_MODEL_ID,
  DeviceEngine,
  type BackendLoader,
  type ChatMessage,
  type DeviceProgress,
} from "./deviceEngine";

function fakeLoader(chat = vi.fn(async (_messages: ChatMessage[]) => "On-device words.")) {
  const loads: string[] = [];
  const loader: BackendLoader = async (modelId, onProgress) => {
    loads.push(modelId);
    onProgress({ progress: 0.5, text: "Fetching params (1/2)" });
    onProgress({ progress: 1, text: "Finish loading" });
    return { chat };
  };
  return { loader, loads, chat };
}

describe("DeviceEngine", () => {
  it("loads the pinned model once and reuses it across calls", async () => {
    // Arrange
    const { loader, loads } = fakeLoader();
    const engine = new DeviceEngine(loader);

    // Act — an explain and a chat; the multi-GB download must happen exactly once.
    await engine.explain("first block", undefined);
    await engine.chat([{ role: "user", content: "a build completion" }]);

    // Assert
    expect(loads).toEqual([DEVICE_MODEL_ID]);
  });

  it("forwards download progress while the model loads", async () => {
    // Arrange
    const { loader } = fakeLoader();
    const engine = new DeviceEngine(loader);
    const seen: DeviceProgress[] = [];

    // Act
    await engine.explain("block", undefined, (p) => seen.push(p));

    // Assert — the UI can render a real progress arc, not an indeterminate spinner.
    expect(seen.map((p) => p.progress)).toEqual([0.5, 1]);
  });

  it("passes chat messages to the backend verbatim and trims the reply", async () => {
    // Arrange — the bridge worker hands the server's wire messages straight through.
    const chat = vi.fn(async (_messages: ChatMessage[]) => "  the answer \n");
    const { loader } = fakeLoader(chat);
    const engine = new DeviceEngine(loader);
    const messages = [
      { role: "system", content: "You are an author." },
      { role: "user", content: "Write a lesson." },
    ];

    // Act
    const reply = await engine.chat(messages);

    // Assert
    expect(reply).toBe("the answer");
    expect(chat).toHaveBeenCalledWith(messages);
  });

  it("preloads the model without running a completion", async () => {
    // Arrange — the device build flow downloads BEFORE the build starts.
    const { loader, loads, chat } = fakeLoader();
    const engine = new DeviceEngine(loader);
    const seen: number[] = [];

    // Act
    await engine.preload((p) => seen.push(p.progress));

    // Assert — downloaded with visible progress, but no completion ran; a later chat
    // reuses the already-booted backend.
    expect(loads).toEqual([DEVICE_MODEL_ID]);
    expect(seen).toEqual([0.5, 1]);
    expect(chat).not.toHaveBeenCalled();
    await engine.chat([{ role: "user", content: "now" }]);
    expect(loads).toHaveLength(1);
  });

  it("prompts with the block's content and context and returns the completion", async () => {
    // Arrange
    const chat = vi.fn(async (_messages: ChatMessage[]) => "It relaxes one edge.");
    const { loader } = fakeLoader(chat);
    const engine = new DeviceEngine(loader);

    // Act
    const explanation = await engine.explain("def relax(edge): ...", "python");

    // Assert — the model saw the content + context; the caller gets the plain answer.
    expect(explanation).toBe("It relaxes one edge.");
    const [messages] = chat.mock.calls[0] ?? [[]];
    expect(messages[0]?.content).toContain("def relax(edge): ...");
    expect(messages[0]?.content).toContain("python");
  });

  it("loads only once even when two calls race during the download", async () => {
    // Arrange — a loader that resolves on demand, so both calls start while it's in flight.
    let release: (backend: { chat: () => Promise<string> }) => void;
    const gate = new Promise<{ chat: () => Promise<string> }>((resolve) => {
      release = resolve;
    });
    const loads: string[] = [];
    const loader: BackendLoader = async (modelId) => {
      loads.push(modelId);
      return gate;
    };
    const engine = new DeviceEngine(loader);

    // Act — release the gate; both pending calls must resolve from the single in-flight load.
    const first = engine.explain("a", undefined);
    const second = engine.chat([{ role: "user", content: "b" }]);
    release!({ chat: async () => "done" });
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
      return { chat: async () => "recovered" };
    };
    const engine = new DeviceEngine(loader);

    // Act / Assert — the failure propagates; the retry starts a fresh load.
    await expect(engine.explain("block", undefined)).rejects.toThrow("download interrupted");
    await expect(engine.explain("block", undefined)).resolves.toBe("recovered");
  });
});
