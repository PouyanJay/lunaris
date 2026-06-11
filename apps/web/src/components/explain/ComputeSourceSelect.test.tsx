import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { COMPUTE_SOURCE_KEY } from "../../lib/computeSource";
import { ComputeSourceSelect } from "./ComputeSourceSelect";

describe("ComputeSourceSelect", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("offers both sources with the server selected by default", () => {
    // Arrange / Act
    render(<ComputeSourceSelect />);

    // Assert — a labelled select with the two compute options, defaulting to today's behavior.
    const select = screen.getByLabelText(/draft ai runs on/i);
    expect(select).toHaveValue("server");
    expect(screen.getByRole("option", { name: /lunaris server/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /this device/i })).toBeInTheDocument();
  });

  it("states the device trade: free builds and explanations, but the tab stays open", () => {
    // Arrange — the choice now governs BUILDS too, so the tab-open contract must be visible
    // at the moment of choosing, never implied.
    vi.stubGlobal("navigator", { gpu: {} });
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");

    // Act
    render(<ComputeSourceSelect />);

    // Assert — first that the DEVICE hint is the one showing (not the disabled-reason text),
    // then that it carries the contract.
    expect(screen.getByLabelText(/draft ai runs on/i)).toHaveValue("device");
    const hint = screen.getByText(/keep this tab open/i);
    expect(hint).toHaveTextContent(/builds/i);
    expect(hint).toHaveTextContent(/1\.8\s*GB/i);
  });

  it("states the server trade: capped but you can close the tab", () => {
    // Arrange — WebGPU present → the trade hint renders, not the disabled-reason paragraph.
    vi.stubGlobal("navigator", { gpu: {} });

    // Act
    render(<ComputeSourceSelect />);

    // Assert — the walk-away side of the trade is explicit too.
    expect(screen.getByText(/close this tab/i)).toBeInTheDocument();
  });

  it("disables the device option with a reason when WebGPU is unavailable", () => {
    // Arrange — jsdom has no navigator.gpu.

    // Act
    render(<ComputeSourceSelect />);

    // Assert — disabled, and the reason is visible (not a silent missing option).
    const device = screen.getByRole("option", { name: /this device/i });
    expect(device).toBeDisabled();
    expect(screen.getByText(/doesn't support webgpu/i)).toBeInTheDocument();
  });

  it("persists a device choice per device when WebGPU is available", () => {
    // Arrange
    vi.stubGlobal("navigator", { gpu: {} });
    render(<ComputeSourceSelect />);

    // Act
    fireEvent.change(screen.getByLabelText(/draft ai runs on/i), {
      target: { value: "device" },
    });

    // Assert — the choice is device-local (localStorage), the dropdown reflects it.
    expect(localStorage.getItem(COMPUTE_SOURCE_KEY)).toBe("device");
    expect(screen.getByLabelText(/draft ai runs on/i)).toHaveValue("device");
  });

  it("restores a previously saved choice", () => {
    // Arrange
    vi.stubGlobal("navigator", { gpu: {} });
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");

    // Act
    render(<ComputeSourceSelect />);

    // Assert
    expect(screen.getByLabelText(/draft ai runs on/i)).toHaveValue("device");
  });
});
