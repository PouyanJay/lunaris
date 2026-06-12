import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { COMPUTE_SOURCE_KEY } from "../../lib/computeSource";
import { ComputeSourceSelect } from "./ComputeSourceSelect";

describe("ComputeSourceSelect", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("offers both sources as a labelled segmented choice, server selected by default", () => {
    // Act
    render(<ComputeSourceSelect />);

    // Assert — a labelled radiogroup with the two compute options, defaulting to today's
    // behavior (the server). A two-option choice reads as segments, not a dropdown.
    expect(screen.getByRole("radiogroup", { name: /draft ai runs on/i })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /lunaris server/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /this device/i })).not.toBeChecked();
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
    expect(screen.getByRole("radio", { name: /this device/i })).toBeChecked();
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
    expect(screen.getByRole("radio", { name: /this device/i })).toBeDisabled();
    expect(screen.getByText(/doesn't support webgpu/i)).toBeInTheDocument();
  });

  it("persists a device choice per device when WebGPU is available", () => {
    // Arrange
    vi.stubGlobal("navigator", { gpu: {} });
    render(<ComputeSourceSelect />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: /this device/i }));

    // Assert — the choice is device-local (localStorage), the control reflects it.
    expect(localStorage.getItem(COMPUTE_SOURCE_KEY)).toBe("device");
    expect(screen.getByRole("radio", { name: /this device/i })).toBeChecked();
  });

  it("restores a previously saved choice", () => {
    // Arrange
    vi.stubGlobal("navigator", { gpu: {} });
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");

    // Act
    render(<ComputeSourceSelect />);

    // Assert
    expect(screen.getByRole("radio", { name: /this device/i })).toBeChecked();
  });

  it("switches back to the server when that segment is chosen again", () => {
    // Arrange — device currently chosen; the reverse path persists too.
    vi.stubGlobal("navigator", { gpu: {} });
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");
    render(<ComputeSourceSelect />);

    // Act
    fireEvent.click(screen.getByRole("radio", { name: /lunaris server/i }));

    // Assert
    expect(localStorage.getItem(COMPUTE_SOURCE_KEY)).toBe("server");
    expect(screen.getByRole("radio", { name: /lunaris server/i })).toBeChecked();
  });

  describe("compact variant (the Draft banner's status row)", () => {
    it("keeps the tab-open contract as a one-liner while the device is chosen", () => {
      // Arrange — device compute selected; compact drops the verbose trade copy but the
      // load-bearing line (closing the tab ends the build) must survive.
      vi.stubGlobal("navigator", { gpu: {} });
      localStorage.setItem(COMPUTE_SOURCE_KEY, "device");

      // Act
      render(<ComputeSourceSelect variant="compact" />);

      // Assert — the contract, without the long download/trade explanation.
      const hint = screen.getByText(/keep this tab open/i);
      expect(hint).toHaveTextContent(/ends the build/i);
      expect(screen.queryByText(/1\.8\s*GB/i)).not.toBeInTheDocument();
    });

    it("shows no hint at all for the server choice", () => {
      // Arrange — server compute: nothing the user must do, so compact says nothing.
      vi.stubGlobal("navigator", { gpu: {} });

      // Act
      render(<ComputeSourceSelect variant="compact" />);

      // Assert — the control itself still renders; only the hint is dropped.
      expect(screen.getByRole("radiogroup", { name: /draft ai runs on/i })).toBeInTheDocument();
      expect(screen.queryByText(/close this tab/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/keep this tab open/i)).not.toBeInTheDocument();
    });

    it("still explains a disabled device option", () => {
      // Arrange — jsdom has no navigator.gpu: the unavailable reason is load-bearing too.

      // Act
      render(<ComputeSourceSelect variant="compact" />);

      // Assert
      expect(screen.getByRole("radio", { name: /this device/i })).toBeDisabled();
      expect(screen.getByText(/doesn't support webgpu/i)).toBeInTheDocument();
    });
  });
});
