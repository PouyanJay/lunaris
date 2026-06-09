import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CapabilityStatus } from "../lib/capabilities";
import { DraftModeBanner } from "./DraftModeBanner";

const LIVE: CapabilityStatus[] = [
  { capability: "llm", mode: "live", provider: "Anthropic Claude" },
  { capability: "embeddings", mode: "live", provider: "Voyage" },
  { capability: "search", mode: "live", provider: "Tavily" },
  { capability: "video", mode: "live", provider: "YouTube" },
];

describe("DraftModeBanner", () => {
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
    expect(banner).toHaveTextContent("Qwen2.5-3B (local)");
    expect(banner).toHaveTextContent("DuckDuckGo");
    // The live capabilities are not listed as fallbacks.
    expect(banner).not.toHaveTextContent("Voyage");
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
