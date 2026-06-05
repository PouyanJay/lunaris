import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPanel } from "./SettingsPanel";

const SETTINGS = {
  pipeline: "stub",
  secrets: [
    { name: "anthropic", isSet: false, last4: null },
    { name: "voyage", isSet: true, last4: "7777" },
    { name: "supabaseUrl", isSet: false, last4: null },
    { name: "supabaseServiceRole", isSet: false, last4: null },
  ],
};

/** A fetch stub: GET returns the settings (or an empty trust config / empty runtime config); PUT
 *  returns the per-call status from `onPut`. The embedded TrustedSourcesPanel lists
 *  /api/source-authorities and the ConfigPanel lists /api/config on mount. */
function stubFetch(onPut: (body: unknown) => { ok: boolean; status?: number; json: unknown }) {
  return vi.fn(async (url: string | URL, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const result = onPut(JSON.parse(String(init.body)));
      return { ok: result.ok, status: result.status ?? 200, json: async () => result.json };
    }
    if (url.toString().includes("/api/source-authorities")) {
      return { ok: true, json: async () => [] };
    }
    if (url.toString().includes("/api/config")) {
      return { ok: true, json: async () => ({ settings: [] }) };
    }
    return { ok: true, json: async () => SETTINGS };
  });
}

describe("SettingsPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  // The "Keys & configuration" section starts collapsed; expand it to reach the secret fields.
  async function expandKeys() {
    fireEvent.click(await screen.findByRole("button", { name: /keys & configuration/i }));
  }

  it("shows each secret's status without revealing values, and masks input", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch(() => ({ ok: true, json: {} })),
    );
    render(<SettingsPanel apiBaseUrl="http://test" />);
    await expandKeys();

    expect(await screen.findByText("Anthropic API key")).toBeInTheDocument();
    // The newer feature keys render too (extend KNOWN_SECRETS + FIELDS).
    expect(screen.getByLabelText("Search API key (Tavily)")).toBeInTheDocument();
    expect(screen.getByLabelText("YouTube API key")).toBeInTheDocument();
    expect(screen.getByLabelText("LangSmith API key")).toBeInTheDocument();
    // voyage is set → status shows its last4, never a value.
    expect(screen.getByText(/set ····7777/i)).toBeInTheDocument();
    // The key input is a password field (masked).
    expect(screen.getByLabelText("Anthropic API key")).toHaveAttribute("type", "password");
    // The embedded Trusted-sources panel mounts alongside the keys (its GET is routed in the stub).
    expect(await screen.findByText("Source authority config")).toBeInTheDocument();
  });

  it("saves a key and reflects the new status", async () => {
    const fetchMock = stubFetch(() => ({
      ok: true,
      json: { name: "anthropic", isSet: true, last4: "WXYZ" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    render(<SettingsPanel apiBaseUrl="http://test" />);
    await expandKeys();

    fireEvent.change(await screen.findByLabelText("Anthropic API key"), {
      target: { value: "sk-ant-supersecret-WXYZ" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save anthropic api key/i }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.getByText(/set ····WXYZ/i)).toBeInTheDocument();
    // The PUT carried the value; nothing in the DOM renders it as text.
    expect(fetchMock).toHaveBeenCalled();
    expect(screen.queryByText("sk-ant-supersecret-WXYZ")).not.toBeInTheDocument();
  });

  it("surfaces a validation rejection from the backend", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch(() => ({
        ok: false,
        status: 400,
        json: { detail: "Anthropic rejected this API key." },
      })),
    );
    render(<SettingsPanel apiBaseUrl="http://test" />);
    await expandKeys();

    fireEvent.change(await screen.findByLabelText("Anthropic API key"), {
      target: { value: "sk-ant-bogus" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save anthropic api key/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/rejected/i));
  });
});
