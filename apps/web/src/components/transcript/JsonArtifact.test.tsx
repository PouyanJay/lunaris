import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainProvider } from "./ExplainContext";
import { JsonArtifact } from "./JsonArtifact";

const FLOW_SPEC = JSON.stringify({
  type: "flow",
  title: null,
  nodes: [{ id: "a", label: "A" }],
  edges: [],
});

describe("JsonArtifact", () => {
  it("summarises a closed JSON object and stays collapsed until expanded", () => {
    render(<JsonArtifact source='{"a":1,"b":2,"c":3}' closed />);

    // The summary shows without dumping the body; the value is not visible yet.
    expect(screen.getByText("object · 3 keys")).toBeInTheDocument();
    expect(screen.queryByText(/"a"/)).not.toBeInTheDocument();

    // Expanding reveals the syntax-highlighted body.
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/"a"/)).toBeInTheDocument();
  });

  it("summarises a JSON array", () => {
    render(<JsonArtifact source="[1,2,3,4]" closed />);

    expect(screen.getByText("array · 4 items")).toBeInTheDocument();
  });

  it("renders a recognised flow spec as a branded diagram, not raw JSON", () => {
    const flow = JSON.stringify({
      type: "flow",
      title: "Request flow",
      nodes: [
        { id: "client", label: "Client" },
        { id: "server", label: "Server" },
      ],
      edges: [{ from: "client", to: "server", label: null }],
    });
    render(<JsonArtifact source={flow} closed />);

    // Labelled as a diagram, summarised, and drawn (the node labels render) — no raw JSON key dumped.
    expect(screen.getByText("diagram")).toBeInTheDocument();
    expect(screen.getByText("flow · 2 nodes · 1 edge")).toBeInTheDocument();
    expect(screen.getByText("Client")).toBeInTheDocument();
    expect(screen.queryByText(/"nodes"/)).not.toBeInTheDocument();
  });

  it("renders a still-streaming blob bounded and open, marked as streaming", () => {
    render(<JsonArtifact source='{"modules":[{"title":"Net' closed={false} />);

    expect(screen.getByText("streaming…")).toBeInTheDocument();
    // Open by default so it forms in view — but inside the bounded artifact, not raw in the page.
    expect(screen.getByText(/"modules"/)).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true");
  });

  it("falls back to a bounded raw view for invalid JSON", () => {
    render(<JsonArtifact source="not json at all, just prose-ish {oops" closed />);

    // Unparseable → a line-count summary + the raw text shown bounded (collapsed by default).
    expect(screen.getByText(/^\d+ line/)).toBeInTheDocument();
  });

  describe("Explain", () => {
    afterEach(() => vi.unstubAllGlobals());

    function renderWithExplain(node: ReactNode, available = true) {
      return render(
        <ExplainProvider apiBaseUrl="http://test" available={available}>
          {node}
        </ExplainProvider>,
      );
    }

    it("offers Explain when available and shows the returned explanation", async () => {
      const fetchMock = vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => ({ explanation: "It maps the order." }) });
      vi.stubGlobal("fetch", fetchMock);
      renderWithExplain(<JsonArtifact source='{"a":1}' closed />);

      fireEvent.click(screen.getByRole("button", { name: /^explain$/i }));

      expect(await screen.findByText("It maps the order.")).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledWith(
        "http://test/api/explain",
        expect.objectContaining({ method: "POST" }),
      );
      // The button is gone once explained — no second call.
      expect(screen.queryByRole("button", { name: /^explain$/i })).not.toBeInTheDocument();
    });

    it("surfaces a recoverable message when Explain fails", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
      renderWithExplain(<JsonArtifact source='{"a":1}' closed />);

      fireEvent.click(screen.getByRole("button", { name: /^explain$/i }));

      expect(await screen.findByText(/couldn't explain/i)).toBeInTheDocument();
    });

    it("hides Explain when the service is unavailable", () => {
      renderWithExplain(<JsonArtifact source='{"a":1}' closed />, false);

      expect(screen.queryByRole("button", { name: /explain/i })).not.toBeInTheDocument();
    });

    it("does not offer Explain on a diagram (it explains itself)", () => {
      renderWithExplain(<JsonArtifact source={FLOW_SPEC} closed />);

      expect(screen.queryByRole("button", { name: /explain/i })).not.toBeInTheDocument();
    });
  });
});
