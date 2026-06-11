import { afterEach, describe, expect, it, vi } from "vitest";

import {
  COMPUTE_SOURCE_KEY,
  detectWebGpu,
  loadComputeSource,
  saveComputeSource,
} from "./computeSource";

describe("compute-source preference", () => {
  afterEach(() => {
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("defaults to the server when nothing is stored", () => {
    expect(loadComputeSource()).toBe("server");
  });

  it("round-trips a saved choice through localStorage", () => {
    // Act
    saveComputeSource("device");

    // Assert — persisted under the stable key, and read back.
    expect(loadComputeSource()).toBe("device");
    expect(localStorage.getItem(COMPUTE_SOURCE_KEY)).toBe("device");
  });

  it("treats a corrupted stored value as the default", () => {
    // Arrange — a value no current version ever wrote.
    localStorage.setItem(COMPUTE_SOURCE_KEY, "mainframe");

    // Act / Assert
    expect(loadComputeSource()).toBe("server");
  });
});

describe("WebGPU detection", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("reports unsupported with a reason when navigator has no gpu", () => {
    // Arrange — jsdom's navigator has no `gpu` (the realistic unsupported browser).

    // Act
    const support = detectWebGpu();

    // Assert — a disabled-state reason the dropdown can show verbatim.
    expect(support.supported).toBe(false);
    expect(support.reason).toMatch(/webgpu/i);
  });

  it("reports supported when the browser exposes WebGPU", () => {
    // Arrange
    vi.stubGlobal("navigator", { gpu: {} });

    // Act / Assert
    expect(detectWebGpu()).toEqual({ supported: true, reason: null });
  });
});
