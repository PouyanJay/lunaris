import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchProdOpsSummaryMock, fetchProdCostMock } = vi.hoisted(() => ({
  fetchProdOpsSummaryMock: vi.fn(),
  fetchProdCostMock: vi.fn(),
}));
vi.mock("../../lib/prodOps", () => ({
  fetchProdOpsSummary: fetchProdOpsSummaryMock,
  fetchProdCost: fetchProdCostMock,
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

describe("ProdOpsSection", () => {
  beforeEach(() => {
    fetchProdOpsSummaryMock.mockReset();
    fetchProdCostMock.mockReset();
    fetchProdOpsSummaryMock.mockResolvedValue({
      resourceGroup: "rg-lunaris-prod",
      currency: "CAD",
    });
    fetchProdCostMock.mockResolvedValue(series(7));
  });

  it("renders the overview and a cost chart defaulting to 7 days", async () => {
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    expect(await screen.findByText("rg-lunaris-prod")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prod operations" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("img")).toBeInTheDocument());
    // Defaults to the 7-day window.
    expect(fetchProdCostMock).toHaveBeenCalledWith("http://api.test", 7, expect.anything());
    expect(screen.getByRole("button", { name: "7d" })).toHaveAttribute("aria-pressed", "true");
  });

  it("refetches cost when the range changes", async () => {
    fetchProdCostMock.mockResolvedValueOnce(series(7)).mockResolvedValue(series(30));
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    fireEvent.click(await screen.findByRole("button", { name: "30d" }));

    await waitFor(() =>
      expect(fetchProdCostMock).toHaveBeenCalledWith("http://api.test", 30, expect.anything()),
    );
    expect(screen.getByRole("button", { name: "30d" })).toHaveAttribute("aria-pressed", "true");
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
