import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { fetchProdOpsSummaryMock } = vi.hoisted(() => ({
  fetchProdOpsSummaryMock: vi.fn(),
}));
vi.mock("../../lib/prodOps", () => ({
  fetchProdOpsSummary: fetchProdOpsSummaryMock,
}));

import { ProdOpsSection } from "./ProdOpsSection";

describe("ProdOpsSection", () => {
  beforeEach(() => {
    fetchProdOpsSummaryMock.mockReset();
  });

  it("renders the resource group and currency the figures cover", async () => {
    fetchProdOpsSummaryMock.mockResolvedValue({ resourceGroup: "rg-lunaris-prod", currency: "CAD" });
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    expect(await screen.findByText("rg-lunaris-prod")).toBeInTheDocument();
    expect(screen.getByText("CAD")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prod operations" })).toBeInTheDocument();
  });

  it("shows an error with a retry when the load fails", async () => {
    fetchProdOpsSummaryMock.mockRejectedValue(new Error("Could not reach the prod-operations service."));
    render(<ProdOpsSection apiBaseUrl="http://api.test" />);

    await waitFor(() =>
      expect(screen.getByText("Could not reach the prod-operations service.")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
