import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExplainProvider } from "../explain/ExplainContext";
import { CodeBlock } from "./CodeBlock";

/** A minimal hast `pre` node carrying one fenced python block, as react-markdown lowers it. */
const hastNode = {
  type: "element",
  tagName: "pre",
  children: [
    {
      type: "element",
      tagName: "code",
      properties: { className: ["language-python"] },
      children: [{ type: "text", value: "def relax(edge):\n    pass\n" }],
    },
  ],
};

function block() {
  return (
    <CodeBlock node={hastNode as never}>
      <code>def relax(edge): ...</code>
    </CodeBlock>
  );
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => body,
  } as Response;
}

describe("CodeBlock explain affordance", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers no Explain button outside an available explain capability", () => {
    // Arrange / Act — no provider (the context default is unavailable).
    render(block());

    // Assert — copy is there, explain is not.
    expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /explain/i })).not.toBeInTheDocument();
  });

  it("explains the block's source through the API and renders the explanation", async () => {
    // Arrange — an available capability backed by a fake server.
    const fetchMock = vi.fn(async () => jsonResponse({ explanation: "It relaxes one edge." }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ExplainProvider apiBaseUrl="http://test" available={true}>
        {block()}
      </ExplainProvider>,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /explain/i }));

    // Assert — the explanation appears, and the request carried the block's raw source.
    await waitFor(() => expect(screen.getByText("It relaxes one edge.")).toBeInTheDocument());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://test/api/explain");
    expect(JSON.parse(init.body as string).content).toContain("def relax(edge):");
  });

  it("shows a recoverable error state when the explanation fails", async () => {
    // Arrange — the server refuses (e.g. capped or unavailable).
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "nope" }, 503)),
    );
    render(
      <ExplainProvider apiBaseUrl="http://test" available={true}>
        {block()}
      </ExplainProvider>,
    );

    // Act
    fireEvent.click(screen.getByRole("button", { name: /explain/i }));

    // Assert — an announced error, and the button is still there to try again (no dead end).
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/couldn't generate an explanation/i),
    );
    expect(screen.getByRole("button", { name: /explain/i })).toBeEnabled();
  });
});
