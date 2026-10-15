import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { fetchProdPowerMock, setProdPowerMock } = vi.hoisted(() => ({
  fetchProdPowerMock: vi.fn(),
  setProdPowerMock: vi.fn(),
}));
vi.mock("../../lib/prodOps", () => ({
  fetchProdPower: fetchProdPowerMock,
  setProdPower: setProdPowerMock,
}));

import type { ProdPowerState, ProdPowerStatus } from "../../lib/prodOps";
import { PowerSwitch } from "./PowerSwitch";

const API = "lunaris-prod-api";
const VM = "lunaris-prod-sim-worker";

/** A power state where the API and the VM report `api` and `vm`. */
function power(api: ProdPowerStatus, vm: ProdPowerStatus): ProdPowerState {
  return {
    isOn: api === "running",
    settled: api !== "transitioning" && vm !== "transitioning",
    resources: [
      { name: API, kind: "container_app", status: api, running: api === "running" },
      { name: VM, kind: "virtual_machine", status: vm, running: vm === "running" },
    ],
  };
}

const ON = power("running", "running");
const OFF = power("stopped", "stopped");

function rowFor(name: string): HTMLElement {
  return screen.getByText(name).closest("li")!;
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("PowerSwitch", () => {
  beforeEach(() => {
    fetchProdPowerMock.mockReset();
    setProdPowerMock.mockReset();
    fetchProdPowerMock.mockResolvedValue(ON);
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows the current state and each governed resource, marking the VM", async () => {
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    expect(await screen.findByText("Production is ON")).toBeInTheDocument();
    expect(within(rowFor(API)).getByText("RUNNING")).toBeInTheDocument();
    expect(within(rowFor(VM)).getByText("VM")).toBeInTheDocument();
    expect(within(rowFor(API)).queryByText("VM")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn production off" })).toBeEnabled();
  });

  it("says what turning off does before anything is sent, and can be cancelled", async () => {
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Turn production off" }));

    const warning = screen.getByRole("group", { name: "Confirm power change" });
    expect(warning).toHaveTextContent(/deallocate the simulator VM/i);
    expect(warning).toHaveTextContent(/offline for everyone/i);
    expect(warning).toHaveTextContent(/only storage costs remain/i);
    expect(setProdPowerMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("group", { name: "Confirm power change" })).not.toBeInTheDocument();
    expect(setProdPowerMock).not.toHaveBeenCalled();
  });

  it.each([
    {
      direction: "off",
      start: ON,
      // Azure accepts the stop at once but the read straight after can still show the old state.
      accepted: power("running", "running"),
      midway: power("stopped", "transitioning"),
      done: OFF,
      toggle: "Turn production off",
      confirm: "Confirm, turn off",
      watching: "Turning production off…",
      mid: "STOPPING",
      final: "Production is OFF",
    },
    {
      direction: "on",
      start: OFF,
      accepted: power("stopped", "transitioning"),
      midway: power("transitioning", "running"),
      done: ON,
      toggle: "Turn production on",
      confirm: "Confirm, turn on",
      watching: "Turning production on…",
      mid: "STARTING",
      final: "Production is ON",
    },
  ])(
    "turning $direction watches Azure until every resource has finished",
    async ({ start, accepted, midway, done, toggle, confirm, watching, mid, final }) => {
      vi.useFakeTimers();
      fetchProdPowerMock.mockReset();
      fetchProdPowerMock
        .mockResolvedValueOnce(start)
        .mockResolvedValueOnce(midway)
        .mockResolvedValue(done);
      setProdPowerMock.mockResolvedValue(accepted);
      render(<PowerSwitch controlBaseUrl="http://ctl.test" />);
      await advance(0);

      fireEvent.click(screen.getByRole("button", { name: toggle }));
      fireEvent.click(screen.getByRole("button", { name: confirm }));
      await advance(0);

      expect(setProdPowerMock).toHaveBeenCalledWith("http://ctl.test", toggle.endsWith("on"));
      expect(screen.getByText(watching)).toBeInTheDocument();
      // No second change can be started while one is under way.
      expect(screen.queryByRole("button", { name: /turn production/i })).not.toBeInTheDocument();

      // Each read costs a round of ARM calls, so the switch asks every 5s, no more often.
      const readsBeforePoll = fetchProdPowerMock.mock.calls.length;
      await advance(4_999);
      expect(fetchProdPowerMock).toHaveBeenCalledTimes(readsBeforePoll);
      await advance(1);
      expect(screen.getByText(watching)).toBeInTheDocument();
      expect(screen.getByText(mid)).toBeInTheDocument();

      await advance(5_000);
      expect(screen.getByText(final)).toBeInTheDocument();
      const reads = fetchProdPowerMock.mock.calls.length;

      // Once everything has finished, it stops asking.
      await advance(60_000);
      expect(fetchProdPowerMock).toHaveBeenCalledTimes(reads);
    },
  );

  it("claims nothing until Azure has accepted the change", async () => {
    setProdPowerMock.mockReturnValue(new Promise<ProdPowerState>(() => {}));
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Turn production off" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm, turn off" }));

    expect(screen.getByRole("button", { name: "Stopping…" })).toBeDisabled();
    expect(screen.getByText("Production is ON")).toBeInTheDocument();
    expect(screen.queryByText("Turning production off…")).not.toBeInTheDocument();
  });

  it("stops watching after ten minutes and offers a refresh", async () => {
    vi.useFakeTimers();
    const stuck = power("stopped", "transitioning");
    fetchProdPowerMock.mockReset();
    fetchProdPowerMock.mockResolvedValueOnce(ON).mockResolvedValue(stuck);
    setProdPowerMock.mockResolvedValue(stuck);
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);
    await advance(0);
    fireEvent.click(screen.getByRole("button", { name: "Turn production off" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm, turn off" }));
    await advance(0);

    // Step through the ten minutes one poll at a time, as real time would.
    for (let elapsed = 0; elapsed < 10 * 60_000; elapsed += 5_000) await advance(5_000);
    const reads = fetchProdPowerMock.mock.calls.length;
    expect(reads).toBeGreaterThan(100);
    await advance(60_000);

    expect(fetchProdPowerMock).toHaveBeenCalledTimes(reads);
    expect(screen.getByText(/still changing after 10 minutes/i)).toBeInTheDocument();
    fetchProdPowerMock.mockResolvedValue(OFF);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await advance(0);
    expect(screen.getByText("Production is OFF")).toBeInTheDocument();
  });

  it("follows a change already under way when the page opens", async () => {
    vi.useFakeTimers();
    fetchProdPowerMock.mockReset();
    fetchProdPowerMock
      .mockResolvedValueOnce(power("stopped", "transitioning"))
      .mockResolvedValue(OFF);
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);
    await advance(0);

    expect(screen.getByText("Production is changing…")).toBeInTheDocument();
    expect(within(rowFor(VM)).getByText("CHANGING")).toBeInTheDocument();

    await advance(5_000);
    expect(screen.getByText("Production is OFF")).toBeInTheDocument();
  });

  it("shows a partly refused change and keeps watching what was sent", async () => {
    fetchProdPowerMock.mockReset();
    fetchProdPowerMock.mockResolvedValueOnce(ON).mockResolvedValue(power("stopped", "running"));
    setProdPowerMock.mockRejectedValue(
      new Error(
        "Could not stop: lunaris-prod-sim-worker. The other resources were sent the change.",
      ),
    );
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Turn production off" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm, turn off" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not stop: lunaris-prod-sim-worker",
    );
    // The rest of the change went out, so the state is re-read rather than left as it was.
    await waitFor(() => expect(within(rowFor(API)).getByText("STOPPED")).toBeInTheDocument());
    expect(within(rowFor(VM)).getByText("RUNNING")).toBeInTheDocument();
  });
});
