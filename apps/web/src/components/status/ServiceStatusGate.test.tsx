import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));
vi.mock("../../hooks/useAuth", () => ({ useAuth: useAuthMock }));

import { ServiceStatusGate } from "./ServiceStatusGate";

function healthy(): Response {
  return new Response('{"status":"ok"}', { status: 200 });
}

function renderGate() {
  return render(
    <ServiceStatusGate apiBaseUrl="http://api.test">
      <p>the app</p>
    </ServiceStatusGate>,
  );
}

/** Let the in-flight probe settle and its state update land. */
async function flushProbe() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe("ServiceStatusGate", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useAuthMock.mockReturnValue({ enabled: false, loading: false, session: null });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("keeps the app mounted once the API answers healthy", async () => {
    const fetchMock = vi.fn().mockResolvedValue(healthy());
    vi.stubGlobal("fetch", fetchMock);

    renderGate();
    expect(screen.getByText("the app")).toBeInTheDocument();
    await flushProbe();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("the app")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /offline/i })).not.toBeInTheDocument();
  });

  it.each([
    ["is unreachable", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["answers 503", () => Promise.resolve(new Response("", { status: 503 }))],
  ])("replaces the app with the offline notice when the API %s", async (_case, answer) => {
    vi.stubGlobal("fetch", vi.fn(answer));

    renderGate();
    await flushProbe();

    expect(screen.getByRole("heading", { name: "Lunaris is offline" })).toBeInTheDocument();
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
  });

  it("brings the app back by itself once the API answers again", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue(healthy());
    vi.stubGlobal("fetch", fetchMock);
    renderGate();
    await flushProbe();
    expect(screen.getByRole("heading", { name: "Lunaris is offline" })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });

    expect(screen.getByText("the app")).toBeInTheDocument();
  });

  it("re-probes at once on Try again", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValue(healthy());
    vi.stubGlobal("fetch", fetchMock);
    renderGate();
    await flushProbe();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await flushProbe();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText("the app")).toBeInTheDocument();
  });

  it("stops probing once it unmounts", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = renderGate();
    await flushProbe();

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
