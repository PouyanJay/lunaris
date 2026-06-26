import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComputeChart } from "./ComputeChart";

const POINTS = [
  { hour: "2026-06-26T00:00:00Z", replicas: 1, cpuCores: 0.5, memoryGb: 1, cost: 0.05 },
  { hour: "2026-06-26T01:00:00Z", replicas: 3, cpuCores: 2, memoryGb: 4, cost: 0.25 },
];

describe("ComputeChart", () => {
  it("renders an empty state when there are no points", () => {
    render(<ComputeChart points={[]} currency="CAD" />);

    expect(screen.getByText(/No compute data/)).toBeInTheDocument();
  });

  it("defaults to the replicas metric and can switch to CPU", () => {
    render(<ComputeChart points={POINTS} currency="CAD" />);

    expect(screen.getByRole("img")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replicas" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    fireEvent.click(screen.getByRole("button", { name: "CPU" }));
    expect(screen.getByRole("button", { name: "CPU" })).toHaveAttribute("aria-pressed", "true");
  });
});
