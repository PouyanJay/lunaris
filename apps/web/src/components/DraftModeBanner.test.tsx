import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CapabilityStatus } from "../lib/capabilities";
import { COMPUTE_SOURCE_KEY } from "../lib/computeSource";
import { DraftModeBanner } from "./DraftModeBanner";

const LIVE: CapabilityStatus[] = [
  { capability: "llm", mode: "live", provider: "Anthropic Claude" },
  { capability: "embeddings", mode: "live", provider: "Voyage" },
  { capability: "search", mode: "live", provider: "Tavily" },
  { capability: "video", mode: "live", provider: "YouTube" },
];

describe("DraftModeBanner", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("names each capability running on a keyless fallback", () => {
    const capabilities: CapabilityStatus[] = [
      { capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)" },
      { capability: "embeddings", mode: "live", provider: "Voyage" },
      { capability: "search", mode: "fallback", provider: "DuckDuckGo" },
      { capability: "video", mode: "live", provider: "YouTube" },
    ];

    render(<DraftModeBanner capabilities={capabilities} />);

    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Draft mode");
    // Each fallback is a labelled chip: the capability name over its provider.
    expect(screen.getByText("Language model")).toBeInTheDocument();
    expect(screen.getByText("Qwen2.5-3B")).toBeInTheDocument();
    expect(banner).toHaveTextContent("Qwen2.5-3B");
    expect(banner).toHaveTextContent("DuckDuckGo");
    // The redundant "(local)" suffix is dropped — the band already says these run locally.
    expect(banner).not.toHaveTextContent("(local)");
    // The live capabilities are not listed as fallbacks.
    expect(banner).not.toHaveTextContent("Voyage");
  });

  it("offers the explain compute dropdown when the language model runs keyless", () => {
    // Arrange — the LLM is on its fallback: this user's explains are keyless too.
    const capabilities: CapabilityStatus[] = [
      { capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)" },
    ];

    // Act
    render(<DraftModeBanner capabilities={capabilities} />);

    // Assert — the per-device choice rides the Draft banner.
    expect(screen.getByLabelText(/draft ai runs on/i)).toBeInTheDocument();
  });

  it("hides the explain compute dropdown when only non-LLM capabilities are fallback", () => {
    // Arrange — search is keyless but the LLM is live: explains are hosted, no choice to make.
    const capabilities: CapabilityStatus[] = [
      { capability: "llm", mode: "live", provider: "Anthropic Claude" },
      { capability: "search", mode: "fallback", provider: "DuckDuckGo" },
    ];

    // Act
    render(<DraftModeBanner capabilities={capabilities} />);

    // Assert
    expect(screen.queryByLabelText(/draft ai runs on/i)).not.toBeInTheDocument();
  });

  it("shows the compute kind (GPU/CPU) for the local model fallback only", () => {
    render(
      <DraftModeBanner
        capabilities={[
          { capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)", compute: "gpu" },
          // No compute field — a keyless web service, not local inference.
          { capability: "search", mode: "fallback", provider: "DuckDuckGo" },
        ]}
      />,
    );

    // The LLM fallback shows its compute as a single accessible chip; the web service (no compute)
    // gets none — so exactly one chip is present, reading "GPU".
    const chips = screen.getAllByLabelText(/running on/i);
    expect(chips).toHaveLength(1);
    expect(chips[0]).toHaveTextContent("GPU");
  });

  it("presents the on-device engine in the language-model cell while the device is chosen", () => {
    // Arrange — the server's capability report says CPU fallback, but THIS device's choice is
    // "This device": the cell must describe what will actually serve — the browser engine over
    // WebGPU — not the server it bypasses.
    vi.stubGlobal("navigator", { gpu: {} });
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");

    // Act
    render(
      <DraftModeBanner
        capabilities={[
          { capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)", compute: "cpu" },
        ]}
      />,
    );

    // Assert — the device engine's compute chip, not the server's.
    const chips = screen.getAllByLabelText(/running on/i);
    expect(chips).toHaveLength(1);
    expect(chips[0]).toHaveTextContent("WEBGPU");
    expect(screen.getByRole("status")).not.toHaveTextContent("CPU");
  });

  it("keeps the server fallback in the language-model cell while the server is chosen", () => {
    // Arrange — default choice (server): the capability report is the truth.
    vi.stubGlobal("navigator", { gpu: {} });

    // Act
    render(
      <DraftModeBanner
        capabilities={[
          { capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)", compute: "cpu" },
        ]}
      />,
    );

    // Assert
    expect(screen.getByLabelText(/running on cpu/i)).toBeInTheDocument();
  });

  it("renders nothing once every capability is live (the banner clears when keys are set)", () => {
    const { container } = render(<DraftModeBanner capabilities={LIVE} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("offers a route to Settings to add keys", () => {
    const onOpenSettings = vi.fn();
    render(
      <DraftModeBanner
        capabilities={[{ capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)" }]}
        onOpenSettings={onOpenSettings}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add your keys in settings/i }));

    expect(onOpenSettings).toHaveBeenCalledOnce();
  });
});
