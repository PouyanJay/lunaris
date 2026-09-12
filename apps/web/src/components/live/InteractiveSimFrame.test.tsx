import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SimContract } from "../../lib/simContract";
import { InteractiveSimFrame } from "./InteractiveSimFrame";
import { SimSessionContext } from "./SimSessionContext";

const contract: SimContract = {
  version: 1,
  objective: "Compare y = 2x",
  parameters: { x: { label: "x", minimum: 0, maximum: 10, step: 1, default: 2 } },
};
const session = {
  apiBaseUrl: "http://api",
  sessionId: "s",
  turnSeq: 1,
  instanceId: "instance",
  exchanges: [],
};
const event = {
  type: "lunaris.sim.event",
  version: 1,
  instanceId: "instance",
  appId: "linear",
  kind: "param_changed",
  state: { x: 4 },
};

function mount() {
  const element = () => (
    <SimSessionContext.Provider value={{ ...session }}>
      <InteractiveSimFrame
        url="/sim"
        title="Linear relationship"
        appId="linear"
        contract={contract}
        answerable
        busy={false}
      />
    </SimSessionContext.Provider>
  );
  const view = render(element());
  const frame = view.container.querySelector("iframe")!;
  const post = vi.spyOn(frame.contentWindow!, "postMessage");
  return { frame, post, rerender: () => view.rerender(element()) };
}

function receive(source: Window | null, data: unknown) {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { source, data }));
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("the shared-state simulator host", () => {
  it("initializes only at readiness and preserves unsent controls on parent rerender", () => {
    const { frame, post, rerender } = mount();
    expect(screen.getByRole("status")).toHaveTextContent("Loading the simulator");
    receive(frame.contentWindow, { type: "lunaris.sim.ready", version: 1 });
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: "lunaris.sim.init", state: { x: 2 } }),
      "*",
    );
    post.mockClear();
    rerender();
    expect(post.mock.calls.filter(([message]) => message.type === "lunaris.sim.init")).toHaveLength(
      0,
    );
    expect(frame).toHaveAttribute("sandbox", "allow-scripts");
  });

  it("shows an explanation fallback for an unsupported contract", () => {
    render(
      <InteractiveSimFrame
        url="/sim"
        title="Future"
        appId="future"
        contract={{ ...contract, version: 2 } as unknown as SimContract}
        answerable
        busy={false}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("needs a newer app version");
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("rejects foreign frames, stale instances and invalid snapshots before making requests", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const { frame } = mount();
    receive(window, event);
    receive(frame.contentWindow, { ...event, instanceId: "old" });
    receive(frame.contentWindow, { ...event, state: { x: 11 } });
    receive(frame.contentWindow, { ...event, state: { x: true } });
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends one gesture while busy and applies the tutor's state without submitting an answer", async () => {
    let finish: (response: Response) => void = () => {};
    const fetch = vi.fn<typeof globalThis.fetch>(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetch);
    const { frame, post } = mount();
    receive(frame.contentWindow, { type: "lunaris.sim.ready", version: 1 });
    receive(frame.contentWindow, event);
    receive(frame.contentWindow, event);
    expect(fetch).toHaveBeenCalledTimes(1);
    const submitted = JSON.parse(fetch.mock.calls[0]![1]!.body as string);
    await act(async () =>
      finish(
        new Response(
          JSON.stringify({
            event: submitted,
            reaction: { text: "Compare this position.", state: { x: 0 } },
            runId: "r",
          }),
        ),
      ),
    );
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("Compare this position."),
    );
    expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: "lunaris.sim.command", state: { x: 0 } }),
      "*",
    );
    expect(fetch).toHaveBeenCalledWith("http://api/api/live/sessions/s/sim", expect.anything());
  });
  it("keeps new submissions disabled after failure and retries the identical event", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockRejectedValueOnce(new Error("Offline"));
    vi.stubGlobal("fetch", fetch);
    const { frame, post } = mount();
    receive(frame.contentWindow, { type: "lunaris.sim.ready", version: 1 });
    receive(frame.contentWindow, event);
    await screen.findByRole("alert");
    expect(post.mock.calls.at(-1)?.[0]).toMatchObject({
      type: "lunaris.sim.availability",
      active: false,
    });
    receive(frame.contentWindow, event);
    expect(fetch).toHaveBeenCalledTimes(1);
    const submitted = JSON.parse(fetch.mock.calls[0]![1]!.body as string);
    fetch.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          event: submitted,
          reaction: { text: "Recovered.", state: { x: 0 } },
          runId: "r",
        }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry tutor response" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Recovered."));
    expect(fetch.mock.calls[1]![1]!.body).toBe(fetch.mock.calls[0]![1]!.body);
  });
});
