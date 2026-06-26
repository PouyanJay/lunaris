import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchProdPowerMock, setProdPowerMock } = vi.hoisted(() => ({
  fetchProdPowerMock: vi.fn(),
  setProdPowerMock: vi.fn(),
}));
vi.mock("../../lib/prodOps", () => ({
  fetchProdPower: fetchProdPowerMock,
  setProdPower: setProdPowerMock,
}));

import { PowerSwitch } from "./PowerSwitch";

const ON = { isOn: true, apps: [{ name: "lunaris-prod-api", running: true }] };
const OFF = { isOn: false, apps: [{ name: "lunaris-prod-api", running: false }] };

describe("PowerSwitch", () => {
  beforeEach(() => {
    fetchProdPowerMock.mockReset();
    setProdPowerMock.mockReset();
    fetchProdPowerMock.mockResolvedValue(ON);
  });

  it("shows the current ON state and each governed app", async () => {
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    expect(await screen.findByText("Production is ON")).toBeInTheDocument();
    expect(screen.getByText("lunaris-prod-api")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Turn production off" })).toBeInTheDocument();
  });

  it("requires an explicit confirm before stopping prod, then reflects OFF", async () => {
    setProdPowerMock.mockResolvedValue(OFF);
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Turn production off" }));
    // A confirmation appears; nothing is sent yet.
    expect(screen.getByText(/Stop the prod apps\?/)).toBeInTheDocument();
    expect(setProdPowerMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm, turn off" }));

    await waitFor(() => expect(setProdPowerMock).toHaveBeenCalledWith("http://ctl.test", false));
    expect(await screen.findByText("Production is OFF")).toBeInTheDocument();
  });

  it("can cancel the confirmation without changing anything", async () => {
    render(<PowerSwitch controlBaseUrl="http://ctl.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Turn production off" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByText(/Stop the prod apps\?/)).not.toBeInTheDocument();
    expect(setProdPowerMock).not.toHaveBeenCalled();
  });
});
