import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConfigSetting } from "../../lib/config";
import type { SecretStatus } from "../../lib/settings";
import { CoverConfigPanel } from "./CoverConfigPanel";

function coverSettings(overrides: Record<string, string> = {}): ConfigSetting[] {
  const base: ConfigSetting[] = [
    {
      name: "coverGenerationEnabled",
      value: "true",
      default: "true",
      kind: "toggle",
      restartRequired: false,
    },
    {
      name: "coverStylePreset",
      value: "nocturne",
      default: "nocturne",
      kind: "preset",
      restartRequired: false,
    },
  ];
  return base.map((s) => {
    const override = overrides[s.name];
    return override !== undefined ? { ...s, value: override } : s;
  });
}

/** Stubs GET /api/config (the cover settings), PUT /api/config/{name} (echo), and GET
 *  /api/credentials (the BYOK OpenAI key status — the gate for the whole section). */
function stubFetch(settings: ConfigSetting[], opts: { openAiSet?: boolean } = {}) {
  return vi.fn(async (url: string | URL, init?: RequestInit) => {
    const href = url.toString();
    if (href.includes("/api/credentials")) {
      return {
        ok: true,
        json: async () => [{ provider: "openai", isSet: opts.openAiSet ?? false, last4: null }],
      };
    }
    if (init?.method === "PUT") {
      const name = href.split("/api/config/")[1] ?? "";
      const value = (JSON.parse(String(init.body)) as { value: string }).value;
      return { ok: true, json: async () => ({ ...settings.find((s) => s.name === name), value }) };
    }
    return { ok: true, json: async () => ({ settings }) };
  });
}

async function expandCovers() {
  fireEvent.click(await screen.findByRole("button", { name: /cover images/i }));
}

function secret(name: string, isSet: boolean): SecretStatus {
  return { name, isSet, last4: isSet ? "wxyz" : null };
}

describe("CoverConfigPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("locks the toggle with a needs-a-key notice when the tenant has no OpenAI key (BYOK)", async () => {
    vi.stubGlobal("fetch", stubFetch(coverSettings(), { openAiSet: false }));
    render(<CoverConfigPanel apiBaseUrl="http://test" byokEnabled secrets={[]} />);
    await expandCovers();

    const toggle = await screen.findByRole("switch", { name: "Generate cover images" });
    expect(toggle).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent(/need an OpenAI API key/i);
  });

  it("unlocks the toggle once an OpenAI key is stored (BYOK) — the key gates the whole section", async () => {
    // The regression this guards: `openai` was missing from the web Keys UI, so no tenant could ever
    // store the key and this toggle stayed permanently disabled — the cover feature was unreachable.
    vi.stubGlobal("fetch", stubFetch(coverSettings(), { openAiSet: true }));
    render(<CoverConfigPanel apiBaseUrl="http://test" byokEnabled secrets={[]} />);
    await expandCovers();

    const toggle = await screen.findByRole("switch", { name: "Generate cover images" });
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).toHaveAttribute("aria-checked", "true");
    // With the master on, the art-direction preset becomes tunable.
    expect(screen.getByLabelText("Art-direction style")).toBeInTheDocument();
  });

  it("reads the key from the file-store secrets when BYOK is off", async () => {
    vi.stubGlobal("fetch", stubFetch(coverSettings()));
    render(
      <CoverConfigPanel
        apiBaseUrl="http://test"
        byokEnabled={false}
        secrets={[secret("openai", true)]}
      />,
    );
    await expandCovers();

    const toggle = await screen.findByRole("switch", { name: "Generate cover images" });
    expect(toggle).toBeEnabled();
  });

  it("saves the new value when the toggle is flipped off", async () => {
    const fetchMock = stubFetch(coverSettings(), { openAiSet: true });
    vi.stubGlobal("fetch", fetchMock);
    render(<CoverConfigPanel apiBaseUrl="http://test" byokEnabled secrets={[]} />);
    await expandCovers();

    const toggle = await screen.findByRole("switch", { name: "Generate cover images" });
    await waitFor(() => expect(toggle).toBeEnabled());
    fireEvent.click(toggle);

    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PUT");
      expect(put).toBeDefined();
      expect(String(put?.[0])).toContain("/api/config/coverGenerationEnabled");
      expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ value: "false" });
    });
  });
});
