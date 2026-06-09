import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CapabilityBuildTag } from "../../types/course";
import { BuildProvenance } from "./BuildProvenance";

const KEYLESS: CapabilityBuildTag[] = [
  { capability: "llm", mode: "fallback", provider: "Qwen2.5-3B (local)" },
  { capability: "embeddings", mode: "fallback", provider: "BGE-large (local)" },
  { capability: "search", mode: "fallback", provider: "DuckDuckGo" },
  { capability: "video", mode: "fallback", provider: "Web search" },
];

describe("BuildProvenance", () => {
  it("names every keyless fallback that produced the course, with its provider", () => {
    render(<BuildProvenance buildCapabilities={KEYLESS} />);
    const band = screen.getByRole("region", { name: /build provenance/i });
    const list = within(band).getByRole("list", { name: /fallback providers used/i });
    expect(within(list).getByText("Language model")).toBeInTheDocument();
    expect(within(list).getByText("Qwen2.5-3B (local)")).toBeInTheDocument();
    expect(within(list).getByText("DuckDuckGo")).toBeInTheDocument();
  });

  it("flags the build as Draft so it is never shown as authoritative", () => {
    render(<BuildProvenance buildCapabilities={KEYLESS} />);
    expect(screen.getByText("DRAFT")).toBeInTheDocument();
  });

  it("lists only the fallback capabilities on a partially-keyed build", () => {
    const mixed: CapabilityBuildTag[] = [
      { capability: "llm", mode: "live", provider: "Anthropic Claude" },
      { capability: "search", mode: "fallback", provider: "DuckDuckGo" },
    ];
    render(<BuildProvenance buildCapabilities={mixed} />);
    const list = screen.getByRole("list", { name: /fallback providers used/i });
    expect(within(list).getByText("Web search")).toBeInTheDocument(); // search's label
    expect(within(list).getByText("DuckDuckGo")).toBeInTheDocument(); // search's fallback provider
    expect(within(list).queryByText("Anthropic Claude")).not.toBeInTheDocument();
  });

  it("renders nothing for a fully-live build (no fallback to disclose)", () => {
    const live: CapabilityBuildTag[] = [
      { capability: "llm", mode: "live", provider: "Anthropic Claude" },
      { capability: "search", mode: "live", provider: "Tavily" },
    ];
    const { container } = render(<BuildProvenance buildCapabilities={live} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when there are no build tags (pre-T5 course)", () => {
    const { container } = render(<BuildProvenance buildCapabilities={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
