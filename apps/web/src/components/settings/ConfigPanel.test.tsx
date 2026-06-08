import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfigPanel } from "./ConfigPanel";

const CONFIG = {
  settings: [
    {
      name: "langsmithTracing",
      value: "false",
      default: "false",
      kind: "toggle",
      restartRequired: true,
    },
    {
      name: "langsmithProject",
      value: "lunaris",
      default: "lunaris",
      kind: "text",
      restartRequired: true,
    },
    {
      name: "modelStrong",
      value: "claude-opus-4-8",
      default: "claude-opus-4-8",
      kind: "model",
      restartRequired: false,
    },
    {
      name: "modelWorker",
      value: "claude-haiku-4-5-20251001",
      default: "claude-haiku-4-5-20251001",
      kind: "model",
      restartRequired: false,
    },
  ],
};

/** GET returns the config; PUT echoes the updated setting via `onPut`. */
function stubFetch(onPut: (name: string, value: string) => unknown) {
  return vi.fn(async (url: string | URL, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const name = url.toString().split("/api/config/")[1] ?? "";
      const value = (JSON.parse(String(init.body)) as { value: string }).value;
      return { ok: true, json: async () => onPut(name, value) };
    }
    return { ok: true, json: async () => CONFIG };
  });
}

async function expandConfig() {
  fireEvent.click(await screen.findByRole("button", { name: /runtime configuration/i }));
}

describe("ConfigPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows each setting with its value and default once expanded", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch((name, value) => ({ ...findSetting(name), value })),
    );
    render(<ConfigPanel apiBaseUrl="http://test" />);
    await expandConfig();

    expect(await screen.findByText("LangSmith tracing")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "LangSmith tracing" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(screen.getByText("default: claude-opus-4-8")).toBeInTheDocument();
    // Exactly the two langsmith settings are flagged restart-required.
    expect(screen.getAllByText("restart to apply")).toHaveLength(2);
  });

  it("saves a toggle and flags restart-to-apply", async () => {
    const fetchMock = stubFetch((name, value) => ({ ...findSetting(name), value }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ConfigPanel apiBaseUrl="http://test" />);
    await expandConfig();

    fireEvent.click(await screen.findByRole("switch", { name: "LangSmith tracing" }));

    await waitFor(() => expect(screen.getByText("Saved — restart to apply")).toBeInTheDocument());
    const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PUT");
    expect(String(put?.[0])).toContain("/api/config/langsmithTracing");
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({ value: "true" });
  });

  it("saves the worker model via the dropdown (no restart note)", async () => {
    const fetchMock = stubFetch((name, value) => ({ ...findSetting(name), value }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ConfigPanel apiBaseUrl="http://test" />);
    await expandConfig();

    fireEvent.change(await screen.findByLabelText("Worker model"), {
      target: { value: "claude-sonnet-4-6" },
    });

    await waitFor(() => expect(screen.getByText("Saved")).toBeInTheDocument());
    // A model save is per-build, not restart-required — no restart note.
    expect(screen.queryByText("Saved — restart to apply")).not.toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([url]) =>
      String(url).includes("/api/config/modelWorker"),
    );
    expect(JSON.parse(String((put?.[1] as RequestInit).body))).toEqual({
      value: "claude-sonnet-4-6",
    });
  });

  it("shows a load error when the config fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })),
    );
    render(<ConfigPanel apiBaseUrl="http://test" />);
    await expandConfig();

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });

  it("surfaces a validation error from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string | URL, init?: RequestInit) => {
        if (init?.method === "PUT") {
          return { ok: false, status: 422, json: async () => ({ detail: "must not be empty" }) };
        }
        return { ok: true, json: async () => CONFIG };
      }),
    );
    render(<ConfigPanel apiBaseUrl="http://test" />);
    await expandConfig();

    fireEvent.click(await screen.findByRole("switch", { name: "LangSmith tracing" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/must not be empty/i));
  });

  it("describes the scope as per-account when per-user config is on", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch((name, value) => ({ ...findSetting(name), value })),
    );
    render(<ConfigPanel apiBaseUrl="http://test" perUserConfig />);
    await expandConfig();

    expect(await screen.findByText(/models your own builds use/i)).toBeInTheDocument();
  });

  it("describes the scope as operator-wide when per-user config is off", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch((name, value) => ({ ...findSetting(name), value })),
    );
    render(<ConfigPanel apiBaseUrl="http://test" />);
    await expandConfig();

    expect(await screen.findByText(/applied to every build on this server/i)).toBeInTheDocument();
  });
});

function findSetting(name: string) {
  return CONFIG.settings.find((s) => s.name === name);
}
