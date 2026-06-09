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
      { capability: "llm", mode: "fallback", provider: "Bonsai 8B (1-bit, local)" },
      { capability: "embeddings", mode: "live", provider: "Voyage" },
      { capability: "search", mode: "fallback", provider: "DuckDuckGo" },
      { capability: "video", mode: "live", provider: "YouTube" },
    ];

    render(<DraftModeBanner capabilities={capabilities} />);

    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent("Draft mode");
    expect(banner).toHaveTextContent("Bonsai 8B (1-bit, local)");
    expect(banner).toHaveTextContent("DuckDuckGo");
    // The live capabilities are not listed as fallbacks.
    expect(banner).not.toHaveTextContent("Voyage");
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
        capabilities={[{ capability: "llm", mode: "fallback", provider: "Bonsai 8B (1-bit, local)" }]}
        onOpenSettings={onOpenSettings}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add your keys in settings/i }));

    expect(onOpenSettings).toHaveBeenCalledOnce();
  });
});
