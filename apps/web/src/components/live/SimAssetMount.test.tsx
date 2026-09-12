import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { authedFetch } from "../../lib/apiClient";
import { InteractiveSimFrame } from "./InteractiveSimFrame";
import { SimSessionContext } from "./SimSessionContext";

vi.mock("../../lib/apiClient", () => ({ authedFetch: vi.fn() }));
afterEach(() => vi.clearAllMocks());
const path = "/api/live/sims/assets/00000000-0000-4000-8000-000000000001";
function mount() {
  return render(
    <SimSessionContext.Provider
      value={{
        apiBaseUrl: "https://api.test",
        sessionId: "s",
        turnSeq: 1,
        instanceId: "r",
        exchanges: [],
      }}
    >
      <InteractiveSimFrame
        url={path}
        title="Doubling"
        appId="asset"
        answerable
        busy={false}
        contract={{
          version: 1,
          objective: "Double x",
          parameters: {
            x: { label: "Input", minimum: 0, maximum: 10, default: 2, step: 1 },
          },
        }}
      />
    </SimSessionContext.Provider>,
  );
}

it("authenticates asset loading and applies the runtime CSP before mounting generated code", async () => {
  vi.mocked(authedFetch).mockResolvedValue(
    new Response("<h1>Approved simulator</h1>", {
      headers: { "Content-Type": "text/html" },
    }),
  );
  const view = mount();
  await waitFor(() =>
    expect(authedFetch).toHaveBeenCalledWith(
      "https://api.test" + path,
      expect.objectContaining({ signal: expect.any(AbortSignal), redirect: "error" }),
    ),
  );
  await waitFor(() => expect(view.container.querySelector("iframe")).not.toBeNull());
  const frame = view.container.querySelector("iframe")!;
  expect(frame).not.toHaveAttribute("src");
  expect(frame).toHaveAttribute("sandbox", "allow-scripts");
  expect(frame.srcdoc).toContain("Content-Security-Policy");
  expect(frame.srcdoc).toContain("connect-src 'none'");
  expect(frame.srcdoc).toContain("Approved simulator");
});

it("keeps a text fallback and mounts no code when the asset is revoked or inaccessible", async () => {
  vi.mocked(authedFetch).mockResolvedValue(new Response("Not found", { status: 404 }));
  const view = mount();
  await screen.findByText(/could not load.*continue with your explanation/i);
  expect(view.container.querySelector("iframe")).toBeNull();
});
