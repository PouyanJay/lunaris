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
    const select = screen.getByLabelText(/explanations run on/i);
    expect(select).toHaveValue("server");
    expect(screen.getByRole("option", { name: /lunaris server/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /this device/i })).toBeInTheDocument();
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
    fireEvent.change(screen.getByLabelText(/explanations run on/i), {
      target: { value: "device" },
    });

    // Assert — the choice is device-local (localStorage), the dropdown reflects it.
    expect(localStorage.getItem(COMPUTE_SOURCE_KEY)).toBe("device");
    expect(screen.getByLabelText(/explanations run on/i)).toHaveValue("device");
  });

  it("restores a previously saved choice", () => {
    // Arrange
    vi.stubGlobal("navigator", { gpu: {} });
    localStorage.setItem(COMPUTE_SOURCE_KEY, "device");

    // Act
    render(<ComputeSourceSelect />);

    // Assert
    expect(screen.getByLabelText(/explanations run on/i)).toHaveValue("device");
  });
});
