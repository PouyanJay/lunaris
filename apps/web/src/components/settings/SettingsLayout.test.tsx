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
    if (url.includes("/api/capabilities")) return Promise.resolve({ ok: true, json: async () => [] });
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
    if (url.includes("/api/credentials")) return Promise.resolve({ ok: true, json: async () => [] });
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
      expect(within(nav).getByRole("link", { name: new RegExp(`^${section}$`, "i") })).toHaveAttribute(
        "href",
        `/settings/${section}`,
      );
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

    // The Voice section owns the ElevenLabs credential + the narration control.
    await waitFor(() =>
      expect(screen.getByText(/elevenlabs api key/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/narrate videos/i)).toBeInTheDocument();
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
});
