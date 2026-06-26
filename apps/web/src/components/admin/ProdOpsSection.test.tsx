import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchProdOpsSummaryMock, fetchProdCostMock, fetchProdComputeMock } = vi.hoisted(() => ({
  fetchProdOpsSummaryMock: vi.fn(),
  fetchProdCostMock: vi.fn(),
  fetchProdComputeMock: vi.fn(),
}));
vi.mock("../../lib/prodOps", () => ({
  fetchProdOpsSummary: fetchProdOpsSummaryMock,
  fetchProdCost: fetchProdCostMock,
  fetchProdCompute: fetchProdComputeMock,
}));

import { ProdOpsSection } from "./ProdOpsSection";

function series(days: number) {
  return {
    currency: "CAD",
    points: Array.from({ length: days }, (_, i) => ({
      day: `2026-06-${String(i + 1).padStart(2, "0")}`,
      amount: 2 + i,
      isPartial: i === days - 1,
    })),
  };
}

function computeSeries(hours: number) {
  return {
    currency: "CAD",
    points: Array.from({ length: hours }, (_, i) => ({
      hour: `2026-06-01T${String(i % 24).padStart(2, "0")}:00:00Z`,
      replicas: 1,
      cpuCores: 0.5,
      memoryGb: 1,
      cost: 0.05,
    })),
  };
}

describe("ProdOpsSection", () => {
  beforeEach(() => {
    fetchProdOpsSummaryMock.mockReset();
    fetchProdCostMock.mockReset();
    fetchProdComputeMock.mockReset();
    fetchProdOpsSummaryMock.mockResolvedValue({
      resourceGroup: "rg-lunaris-prod",
      currency: "CAD",
    });
    fetchProdCostMock.mockResolvedValue(series(7));
    fetchProdComputeMock.mockResolvedValue(computeSeries(24));
  });

  it("renders the overview plus cost and compute charts defaulting to 7 days", async () => {
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    expect(await screen.findByText("rg-lunaris-prod")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prod operations" })).toBeInTheDocument();
    // Both charts render (cost bar chart + compute dual-axis chart).
    await waitFor(() => expect(screen.getAllByRole("img").length).toBe(2));
    // Defaults to the 7-day window for both series.
    expect(fetchProdCostMock).toHaveBeenCalledWith("http://api.test", 7, expect.anything());
    expect(fetchProdComputeMock).toHaveBeenCalledWith("http://api.test", 7, expect.anything());
    expect(screen.getByRole("button", { name: "7d" })).toHaveAttribute("aria-pressed", "true");
  });

  it("refetches both series when the window changes", async () => {
    fetchProdCostMock.mockResolvedValueOnce(series(7)).mockResolvedValue(series(30));
    fetchProdComputeMock
      .mockResolvedValueOnce(computeSeries(24))
      .mockResolvedValue(computeSeries(48));
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "30d" }));

    await waitFor(() => {
      expect(fetchProdCostMock).toHaveBeenCalledWith("http://api.test", 30, expect.anything());
      expect(fetchProdComputeMock).toHaveBeenCalledWith("http://api.test", 30, expect.anything());
    });
    expect(screen.getByRole("button", { name: "30d" })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches the compute usage metric", async () => {
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    const cpu = await screen.findByRole("button", { name: "CPU" });
    fireEvent.click(cpu);
    expect(cpu).toHaveAttribute("aria-pressed", "true");
  });

  it("shows an error with a retry when the overview load fails", async () => {
    fetchProdOpsSummaryMock.mockRejectedValue(
      new Error("Could not reach the prod-operations service."),
    );
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    await waitFor(() =>
      expect(screen.getByText("Could not reach the prod-operations service.")).toBeInTheDocument(),
    );
    expect(screen.getAllByRole("button", { name: "Retry" }).length).toBeGreaterThan(0);
  });
});
