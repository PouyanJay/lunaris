import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConfigSetting } from "../../lib/config";
import type { SecretStatus } from "../../lib/settings";
import { VideoConfigPanel } from "./VideoConfigPanel";

function videoSettings(overrides: Record<string, string> = {}): ConfigSetting[] {
  const base: ConfigSetting[] = [
    {
      name: "videoEnabled",
      value: "true",
      default: "true",
      kind: "toggle",
      restartRequired: false,
    },
    {
      name: "videoLessonsEnabled",
      value: "true",
      default: "true",
      kind: "toggle",
      restartRequired: false,
    },
    { name: "videoVoice", value: "true", default: "true", kind: "toggle", restartRequired: false },
    {
      name: "videoSummarySeconds",
      value: "75",
      default: "75",
      kind: "number",
      restartRequired: false,
    },
    {
      name: "videoOverviewSeconds",
      value: "180",
      default: "180",
      kind: "number",
      restartRequired: false,
    },
    {
      name: "videoLessonSeconds",
      value: "75",
      default: "75",
      kind: "number",
      restartRequired: false,
    },
  ];
  return base.map((s) => {
    const override = overrides[s.name];
    return override !== undefined ? { ...s, value: override } : s;
  });
}

/** Stubs GET /api/config (the video settings), PUT /api/config/{name} (echo), and GET
 *  /api/credentials (the BYOK ElevenLabs status). */
function stubFetch(settings: ConfigSetting[], opts: { elevenLabsSet?: boolean } = {}) {
  return vi.fn(async (url: string | URL, init?: RequestInit) => {
    const href = url.toString();
    if (href.includes("/api/credentials")) {
      return {
        ok: true,
        json: async () => [
          { provider: "elevenlabs", isSet: opts.elevenLabsSet ?? false, last4: null },
        ],
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

async function expandVideo() {
  fireEvent.click(await screen.findByRole("button", { name: /video generation/i }));
}

function secret(name: string, isSet: boolean): SecretStatus {
  return { name, isSet, last4: isSet ? "wxyz" : null };
}

describe("VideoConfigPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the master toggle and, when on, the voice toggle + three length controls", async () => {
    vi.stubGlobal("fetch", stubFetch(videoSettings()));
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", true)]}
      />,
    );
    await expandVideo();

    expect(await screen.findByRole("switch", { name: "Generate videos" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("switch", { name: "Generate lesson videos" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Narrate videos" })).toBeInTheDocument();
    expect(screen.getByLabelText("Course trailer length")).toBeInTheDocument();
    expect(screen.getByLabelText("Topic intro length")).toBeInTheDocument();
    expect(screen.getByLabelText("Lesson video length")).toBeInTheDocument();
  });

  it("saves the lesson-videos sub-toggle through PUT /api/config/videoLessonsEnabled", async () => {
    const fetchMock = stubFetch(videoSettings({ videoLessonsEnabled: "true" }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", true)]}
      />,
    );
    await expandVideo();

    // Turn the sub-toggle OFF — the build then makes only the course-level videos.
    fireEvent.click(await screen.findByRole("switch", { name: "Generate lesson videos" }));

    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    const put = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/config/videoLessonsEnabled"),
    );
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ value: "false" });
  });

  it("saves the master toggle through PUT /api/config/videoEnabled", async () => {
    const fetchMock = stubFetch(videoSettings({ videoEnabled: "false" }));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", true)]}
      />,
    );
    await expandVideo();

    fireEvent.click(await screen.findByRole("switch", { name: "Generate videos" }));

    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    const put = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/config/videoEnabled"),
    );
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ value: "true" });
  });

  it("hides the voice + length controls when the master toggle is off (deactivated)", async () => {
    vi.stubGlobal("fetch", stubFetch(videoSettings({ videoEnabled: "false" })));
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", true)]}
      />,
    );
    await expandVideo();

    expect(await screen.findByRole("switch", { name: "Generate videos" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    // The sub-settings disclosure is collapsed.
    expect(
      screen.queryByRole("switch", { name: "Generate lesson videos" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Narrate videos" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Lesson video length")).not.toBeInTheDocument();
  });

  it("locks the voice toggle off until an ElevenLabs key exists", async () => {
    vi.stubGlobal("fetch", stubFetch(videoSettings()));
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", false)]}
      />,
    );
    await expandVideo();

    const voice = await screen.findByRole("switch", { name: "Narrate videos" });
    // No key → off + disabled regardless of the stored intent ("true"), with a guiding hint.
    expect(voice).toBeDisabled();
    expect(voice).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/add an elevenlabs api key/i)).toBeInTheDocument();
  });

  it("enables the voice toggle once a BYOK ElevenLabs key is present", async () => {
    vi.stubGlobal("fetch", stubFetch(videoSettings(), { elevenLabsSet: true }));
    render(<VideoConfigPanel apiBaseUrl="http://test" keyless={false} byokEnabled secrets={[]} />);
    await expandVideo();

    const voice = await screen.findByRole("switch", { name: "Narrate videos" });
    await waitFor(() => expect(voice).not.toBeDisabled());
    expect(voice).toHaveAttribute("aria-checked", "true");
  });

  it("locks the voice toggle off in BYOK mode when the key is not yet set", async () => {
    // The BYOK branch of the key check: credentials report no elevenlabs key → locked, like the
    // non-BYOK secrets path, but reached through the async /api/credentials read.
    vi.stubGlobal("fetch", stubFetch(videoSettings(), { elevenLabsSet: false }));
    render(<VideoConfigPanel apiBaseUrl="http://test" keyless={false} byokEnabled secrets={[]} />);
    await expandVideo();

    const voice = await screen.findByRole("switch", { name: "Narrate videos" });
    await waitFor(() => expect(voice).toBeDisabled());
    expect(voice).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/add an elevenlabs api key/i)).toBeInTheDocument();
  });

  it("saves a length change through PUT /api/config", async () => {
    const fetchMock = stubFetch(videoSettings());
    vi.stubGlobal("fetch", fetchMock);
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", true)]}
      />,
    );
    await expandVideo();

    // The custom Select (a listbox, not a native <select>): open it, then pick the option (90s → 1:30).
    fireEvent.click(await screen.findByRole("button", { name: /lesson video length/i }));
    fireEvent.pointerDown(screen.getByRole("option", { name: "1:30" }));

    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    const put = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/config/videoLessonSeconds"),
    );
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ value: "90" });
  });

  it("surfaces a validation error when a save is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return { ok: false, status: 422, json: async () => ({ detail: "out of bounds" }) };
        }
        return { ok: true, json: async () => ({ settings: videoSettings() }) };
      }),
    );
    render(
      <VideoConfigPanel
        apiBaseUrl="http://test"
        keyless={false}
        byokEnabled={false}
        secrets={[secret("elevenlabs", true)]}
      />,
    );
    await expandVideo();

    // The custom Select (a listbox, not a native <select>): open it, then pick the option (90s → 1:30).
    fireEvent.click(await screen.findByRole("button", { name: /lesson video length/i }));
    fireEvent.pointerDown(screen.getByRole("option", { name: "1:30" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/out of bounds/i));
  });

  it("fully deactivates the section with a needs-a-key affordance for keyless accounts", async () => {
    vi.stubGlobal("fetch", stubFetch(videoSettings()));
    render(<VideoConfigPanel apiBaseUrl="http://test" keyless byokEnabled={false} secrets={[]} />);
    await expandVideo();

    expect(await screen.findByRole("switch", { name: "Generate videos" })).toBeDisabled();
    expect(screen.getByRole("note")).toHaveTextContent(/needs an anthropic api key/i);
    // None of the sub-settings are offered on the keyless tier.
    expect(
      screen.queryByRole("switch", { name: "Generate lesson videos" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Narrate videos" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Lesson video length")).not.toBeInTheDocument();
  });
});
