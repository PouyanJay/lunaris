import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsLayout } from "./SettingsLayout";
import { SETTINGS_SECTIONS, type SettingsSection } from "../../lib/routes";

const API = "http://api.test";

/** A fetch stub that answers the settings/capabilities/config reads the surface makes on mount. */
function stubSettingsFetch(view: Record<string, unknown> = {}) {
  const fetchMock = vi.fn((input: Parameters<typeof fetch>[0]) => {
    const url = input instanceof Request ? input.url : String(input);
    if (url.includes("/api/settings")) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          secrets: [],
          pipeline: "stub",
          byokEnabled: false,
          perUserConfigEnabled: false,
          ...view,
        }),
      });
    }
    if (url.includes("/api/capabilities"))
      return Promise.resolve({ ok: true, json: async () => [] });
    if (url.includes("/api/config"))
      return Promise.resolve({
        ok: true,
        json: async () => ({
          settings: [
            {
              name: "videoVoice",
              value: "false",
              default: "false",
              kind: "toggle",
              restartRequired: false,
            },
          ],
        }),
      });
    if (url.includes("/api/credentials"))
      return Promise.resolve({ ok: true, json: async () => [] });
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function renderSection(section: SettingsSection, onPreferenceChange = vi.fn()) {
  return render(
    <MemoryRouter>
      <SettingsLayout
        apiBaseUrl={API}
        section={section}
        preference="light"
        onPreferenceChange={onPreferenceChange}
      />
    </MemoryRouter>,
  );
}

describe("SettingsLayout", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders a sub-nav with all seven sections, deep-linked, marking the active one", async () => {
    stubSettingsFetch();
    renderSection("voice");
    // Let the settings/credentials fetch settle inside act before asserting + unmounting — the nav
    // itself is synchronous, but leaving the pending fetch to resolve after the test leaks a
    // setState into the next test (the source of the suite-wide flakiness the reviewers caught).
    await screen.findByText(/elevenlabs api key/i);

    const nav = screen.getByRole("navigation", { name: /settings sections/i });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual([
      "System",
      "Appearance",
      "LLM",
      "Video",
      "Voice",
      "Tools",
      "Sources",
    ]);
    // Every section is a real deep link (Back/Forward + shareable).
    for (const section of SETTINGS_SECTIONS) {
      expect(
        within(nav).getByRole("link", { name: new RegExp(`^${section}$`, "i") }),
      ).toHaveAttribute("href", `/settings/${section}`);
    }
    // The active section carries aria-current="page".
    expect(within(nav).getByRole("link", { name: /^voice$/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders the Appearance section's theme control and reports a preference change", async () => {
    stubSettingsFetch();
    const onPreferenceChange = vi.fn();
    renderSection("appearance", onPreferenceChange);

    // The 3-way theme control (radiogroup) with the current preference selected.
    await screen.findByText(/interface theme/i);
    const dark = screen.getByRole("radio", { name: /^dark$/i });
    fireEvent.click(dark);
    expect(onPreferenceChange).toHaveBeenCalledWith("dark");
  });

  it("places the ElevenLabs key in the Voice section (file-store mode)", async () => {
    stubSettingsFetch();
    renderSection("voice");

    // The Voice section owns the ElevenLabs credential + the narration control. The narrate toggle
    // comes from VoiceConfigPanel's OWN config fetch (a separate promise from the settings load), so
    // it must be awaited independently — findBy, not a bare getBy.
    await screen.findByText(/elevenlabs api key/i);
    await screen.findByText(/narrate videos/i);
    // …and does not surface the Anthropic key (that lives in the LLM section).
    expect(screen.queryByText(/anthropic api key/i)).not.toBeInTheDocument();
  });

  it("places the Anthropic + Voyage keys in the LLM section", async () => {
    stubSettingsFetch();
    renderSection("llm");

    await waitFor(() => expect(screen.getByText(/anthropic api key/i)).toBeInTheDocument());
    expect(screen.getByText(/voyage embeddings key/i)).toBeInTheDocument();
    expect(screen.queryByText(/elevenlabs api key/i)).not.toBeInTheDocument();
  });

  // Wiring smoke tests: SettingsLayout routes each section id to the right content. The panels'
  // own logic is covered by their component tests; these prove the section dispatch + scoping.
  it("routes the System section to pipeline mode + the infra keys", async () => {
    stubSettingsFetch({ pipeline: "agent" });
    renderSection("system");

    await waitFor(() => expect(screen.getByText(/pipeline mode/i)).toBeInTheDocument());
    expect(screen.getByText("agent")).toBeInTheDocument();
    // System owns the operator/infra keys (file-store mode), not the LLM provider key.
    expect(screen.getByText(/supabase url/i)).toBeInTheDocument();
    expect(screen.queryByText(/anthropic api key/i)).not.toBeInTheDocument();
  });

  it("routes the Tools section to the cover control + the service keys", async () => {
    stubSettingsFetch();
    renderSection("tools");

    await screen.findByText(/youtube api key/i);
    expect(screen.getByText(/search api key/i)).toBeInTheDocument();
    // Cover images (image generation) live under Tools.
    expect(screen.getByText(/cover images/i)).toBeInTheDocument();
  });

  it("routes the Video section to video generation and the Sources section to source authority", async () => {
    stubSettingsFetch();
    const { unmount } = renderSection("video");
    await screen.findByText(/video generation/i);
    unmount();

    renderSection("sources");
    await screen.findByText(/source authority/i);
  });

  it("renders per-user BYOK credential fields (with a Test action) in BYOK mode", async () => {
    // Under BYOK the LLM section shows the tenant's own keys as CredentialFields — which carry a
    // Test action the write-only file-store SecretField does not — and operator-only keys
    // (Supabase) are hidden even in the System section.
    stubSettingsFetch({ byokEnabled: true });
    const { unmount } = renderSection("llm");

    await screen.findByText(/anthropic api key/i);
    // The Test action (aria-label "Test <key>") is BYOK-only — its presence proves the BYOK field,
    // not the file-store SecretField (which has no probe). hidden:true because the credential
    // disclosure starts collapsed (role queries exclude hidden nodes by default).
    expect(
      screen.getByRole("button", { name: /^test anthropic/i, hidden: true }),
    ).toBeInTheDocument();
    unmount();

    // System infra keys are operator-owned, so BYOK mode surfaces none of them.
    renderSection("system");
    await screen.findByText(/pipeline mode/i);
    expect(screen.queryByText(/supabase url/i)).not.toBeInTheDocument();
  });
});
