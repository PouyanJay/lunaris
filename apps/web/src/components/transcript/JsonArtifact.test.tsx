import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainProvider } from "../explain/ExplainContext";
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

  describe("auto-Explain", () => {
    afterEach(() => vi.unstubAllGlobals());

    const SUBSTANTIAL = '{"a":1,"b":2,"c":3}'; // 3 keys → worth explaining

    function renderWithExplain(node: ReactNode, available = true) {
      return render(
        <ExplainProvider apiBaseUrl="http://test" available={available}>
          {node}
        </ExplainProvider>,
      );
    }

    function mockExplain(text = "It maps the order.") {
      const fetchMock = vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => ({ explanation: text }) });
      vi.stubGlobal("fetch", fetchMock);
      return fetchMock;
    }

    it("auto-explains a substantial blob — no click — and shows the result once", async () => {
      const fetchMock = mockExplain();
      renderWithExplain(<JsonArtifact source={SUBSTANTIAL} closed />);

      expect(await screen.findByText("It maps the order.")).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        "http://test/api/explain",
        expect.objectContaining({ method: "POST" }),
      );
    });

    it("auto-explains a long blob even with few keys (the source-length branch)", async () => {
      const long = '{"note":"' + "x".repeat(110) + '"}'; // 1 key, but > 100 chars
      const fetchMock = mockExplain();
      renderWithExplain(<JsonArtifact source={long} closed />);

      expect(await screen.findByText("It maps the order.")).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("surfaces a recoverable message when the explanation fails", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
      renderWithExplain(<JsonArtifact source={SUBSTANTIAL} closed />);

      expect(await screen.findByText(/couldn't explain/i)).toBeInTheDocument();
    });

    it("does not explain when the service is unavailable", () => {
      const fetchMock = mockExplain();
      renderWithExplain(<JsonArtifact source={SUBSTANTIAL} closed />, false);

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("does not explain a diagram (it explains itself)", () => {
      const fetchMock = mockExplain();
      renderWithExplain(<JsonArtifact source={FLOW_SPEC} closed />);

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("does not explain a trivial blob", () => {
      const fetchMock = mockExplain();
      renderWithExplain(<JsonArtifact source='{"a":1}' closed />);

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("does not explain a blob that is still streaming (even a substantial one)", () => {
      // Long enough to be "substantial", but unterminated → the closed guard alone must stop it.
      const streaming = '{"detail":"' + "x".repeat(110);
      const fetchMock = mockExplain();
      renderWithExplain(<JsonArtifact source={streaming} closed={false} />);

      expect(fetchMock).not.toHaveBeenCalled();
    });
  });
});
