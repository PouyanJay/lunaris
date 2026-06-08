import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CredentialsPanel } from "./CredentialsPanel";

const READY = [
  { provider: "anthropic", isSet: true, last4: "9abc" },
  { provider: "voyage", isSet: false, last4: null },
  { provider: "search", isSet: false, last4: null },
  { provider: "youtube", isSet: false, last4: null },
];

/** Routes the credentials API by method + path. `onMutate` shapes PUT/DELETE/POST responses. */
function stubFetch(
  onMutate?: (
    method: string,
    url: string,
    body: unknown,
  ) => { ok?: boolean; status?: number; json: unknown },
) {
  return vi.fn(async (url: string | URL, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const href = url.toString();
    if (method === "GET") return { ok: true, json: async () => READY };
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    const result = onMutate?.(method, href, body) ?? { json: {} };
    return { ok: result.ok ?? true, status: result.status ?? 200, json: async () => result.json };
  });
}

describe("CredentialsPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("lists each BYOK provider with masked status, never a value", async () => {
    vi.stubGlobal("fetch", stubFetch());
    render(<CredentialsPanel apiBaseUrl="http://test" />);

    expect(await screen.findByText("Anthropic API key")).toBeInTheDocument();
    expect(screen.getByLabelText("Voyage embeddings key")).toBeInTheDocument();
    expect(screen.getByLabelText("Search API key (Tavily)")).toBeInTheDocument();
    expect(screen.getByLabelText("YouTube API key")).toBeInTheDocument();
    // anthropic is set → shows its last4 (masked), never the value; input is a password field.
    expect(screen.getByText(/set ····9abc/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Anthropic API key")).toHaveAttribute("type", "password");
  });

  it("saves a key and reflects the new masked status", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch((method) =>
        method === "PUT"
          ? { json: { provider: "voyage", isSet: true, last4: "PA12" } }
          : { json: {} },
      ),
    );
    render(<CredentialsPanel apiBaseUrl="http://test" />);

    const input = await screen.findByLabelText("Voyage embeddings key");
    fireEvent.change(input, { target: { value: "pa-secret-PA12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Voyage embeddings key" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/set ····PA12/i)).toBeInTheDocument());
    // Write-only: the raw value never renders back into the DOM.
    expect(screen.queryByText("pa-secret-PA12")).not.toBeInTheDocument();
  });

  it("reports an invalid key from the test probe without storing it", async () => {
    const fetchMock = stubFetch((method) =>
      method === "POST"
        ? { json: { ok: false, detail: "Anthropic rejected this API key." } }
        : { json: {} },
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<CredentialsPanel apiBaseUrl="http://test" />);

    const input = await screen.findByLabelText("Anthropic API key");
    fireEvent.change(input, { target: { value: "bad-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Test Anthropic API key" }));

    expect(await screen.findByText("Anthropic rejected this API key.")).toBeInTheDocument();
    // A probe must never persist: no PUT/DELETE was issued, only the POST test call.
    const methods = fetchMock.mock.calls.map(([, init]) => init?.method ?? "GET");
    expect(methods).not.toContain("PUT");
    expect(methods).not.toContain("DELETE");
  });

  it("removes a set key only after an inline confirm", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch((method) =>
        method === "DELETE"
          ? { json: { provider: "anthropic", isSet: false, last4: null } }
          : { json: {} },
      ),
    );
    render(<CredentialsPanel apiBaseUrl="http://test" />);

    // First click only asks to confirm (no destructive call yet).
    fireEvent.click(await screen.findByRole("button", { name: "Remove Anthropic API key" }));
    expect(screen.getByText("Remove this key?")).toBeInTheDocument();

    // Confirming removes it and the status flips to not set.
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove Anthropic API key" }));
    expect(await screen.findByText("Removed")).toBeInTheDocument();
    await waitFor(() => {
      const anthropicHead = screen.getByText("Anthropic API key").closest("div");
      expect(anthropicHead?.textContent).toMatch(/not set/i);
    });
  });

  it("shows a recoverable error when the keys can't be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ detail: "BYOK off" }) })),
    );
    render(<CredentialsPanel apiBaseUrl="http://test" />);

    expect(await screen.findByRole("alert")).toHaveTextContent("BYOK off");
  });
});
