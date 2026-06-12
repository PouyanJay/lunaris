import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { COMPUTE_SOURCE_KEY } from "../../lib/computeSource";
import { DeviceEngine, type BackendLoader } from "../../lib/deviceEngine";
import { ExplainProvider, useExplainApi, type ExplainOutcome } from "./ExplainContext";

function Probe() {
  const { explain } = useExplainApi();
  return (
    <button
      type="button"
      onClick={() =>
        void explain("the block", "ctx").then((outcome: ExplainOutcome) => {
          document.title = `${outcome.source}:${outcome.explanation}`;
        })
      }
    >
      go
    </button>
  );
}

function deviceEngine(answer: string) {
  const loader: BackendLoader = async () => ({ chat: async () => answer });
  return new DeviceEngine(loader);
}

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

describe("ExplainProvider compute routing", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
    document.title = "";
  });

  it("answers on-device when the keyless user chose this device", async () => {
    // Arrange — keyless LLM, device choice saved, WebGPU present, a fake engine injected.
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");
    const fetchMock = vi.fn();
    vi.stubGlobal("navigator", { gpu: {} });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ExplainProvider
        apiBaseUrl="http://test"
        available={true}
        llmKeyless={true}
        deviceEngine={deviceEngine("Local words.")}
      >
        <Probe />
      </ExplainProvider>,
    );

    // Act
    screen.getByRole("button", { name: "go" }).click();

    // Assert — the device answered with its provenance; the server was never called.
    await waitFor(() => expect(document.title).toBe("on-device:Local words."));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("answers via the server when the keyless user chose the server", async () => {
    // Arrange — keyless, but the (default) server choice.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ explanation: "Server words.", source: "server-fallback" })),
    );
    render(
      <ExplainProvider
        apiBaseUrl="http://test"
        available={true}
        llmKeyless={true}
        deviceEngine={deviceEngine("never used")}
      >
        <Probe />
      </ExplainProvider>,
    );

    // Act
    screen.getByRole("button", { name: "go" }).click();

    // Assert — the wire's provenance flows through.
    await waitFor(() => expect(document.title).toBe("server-fallback:Server words."));
  });

  it("ignores a device choice when the LLM is keyed (hosted always wins)", async () => {
    // Arrange — a keyed user who once chose "device" on this browser: hosted still answers.
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ explanation: "Claude words.", source: "hosted" })),
    );
    render(
      <ExplainProvider
        apiBaseUrl="http://test"
        available={true}
        llmKeyless={false}
        deviceEngine={deviceEngine("never used")}
      >
        <Probe />
      </ExplainProvider>,
    );

    // Act
    screen.getByRole("button", { name: "go" }).click();

    // Assert
    await waitFor(() => expect(document.title).toBe("hosted:Claude words."));
  });

  it("falls back to the server when device is chosen but WebGPU is absent", async () => {
    // Arrange — a stale "device" choice on a browser that can't run it (jsdom has no gpu).
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ explanation: "Server words.", source: "server-fallback" })),
    );
    render(
      <ExplainProvider
        apiBaseUrl="http://test"
        available={true}
        llmKeyless={true}
        deviceEngine={deviceEngine("never used")}
      >
        <Probe />
      </ExplainProvider>,
    );

    // Act
    screen.getByRole("button", { name: "go" }).click();

    // Assert — no dead end on unsupported hardware.
    await waitFor(() => expect(document.title).toBe("server-fallback:Server words."));
  });
});

describe("answering-tier badges (variant coverage)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it.each([
    ["hosted", "CLAUDE"],
    ["server-fallback", "LUNARIS SERVER"],
  ] as const)("labels a %s answer as %s", async (source, label) => {
    // Arrange — render the full hook → result path with the wire reporting `source`.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ explanation: "Words.", source })),
    );
    const { ExplainResult } = await import("./ExplainResult");
    const { useExplain } = await import("./useExplain");
    function Block() {
      const { state, explain } = useExplain();
      return (
        <div>
          <button type="button" onClick={() => void explain("x")}>
            go
          </button>
          <ExplainResult state={state} />
        </div>
      );
    }
    render(
      <ExplainProvider apiBaseUrl="http://test" available={true}>
        <Block />
      </ExplainProvider>,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: "go" }));

    // Assert
    await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
  });
});
