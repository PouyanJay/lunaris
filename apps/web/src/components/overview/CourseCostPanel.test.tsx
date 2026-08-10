import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CostEvent, CourseCost } from "../../lib/cost";

// Mock only the network seams — keep money() + CostError real so formatting and the hooks'
// `instanceof CostError` behave as in production.
const { fetchCourseCostMock, fetchCourseCostEventsMock } = vi.hoisted(() => ({
  fetchCourseCostMock: vi.fn(),
  fetchCourseCostEventsMock: vi.fn(),
}));
vi.mock("../../lib/cost", async (importActual) => {
  const actual = await importActual<typeof import("../../lib/cost")>();
  return {
    ...actual,
    fetchCourseCost: fetchCourseCostMock,
    fetchCourseCostEvents: fetchCourseCostEventsMock,
  };
});

import { CourseCostPanel } from "./CourseCostPanel";

function meteredRollup(overrides: Partial<CourseCost> = {}): CourseCost {
  return {
    subjectType: "course",
    subjectId: "c-1",
    totalAmount: 0.42,
    currency: "USD",
    breakdown: {
      byComponent: { planner: 0.4, render: 0.02 },
      byProvider: { anthropic: 0.4, manim: 0.02 },
      byPocket: { user_key: 0.4, platform: 0.02 },
      eventCount: 5,
    },
    priceBookVersion: "2026-07",
    updatedAt: "2026-07-26T10:00:00Z",
    ...overrides,
  };
}

function keylessRollup(): CourseCost {
  return meteredRollup({
    totalAmount: 0,
    breakdown: {
      byComponent: { planner: 0 },
      byProvider: { local: 0 },
      byPocket: { user_key: 0, platform: 0 },
      eventCount: 3,
    },
  });
}

function ledger(): CostEvent[] {
  return [
    {
      runId: "r-1",
      subjectType: "course",
      subjectId: "c-1",
      seq: 0,
      component: "planner",
      provider: "anthropic",
      model: "claude-opus-4-8",
      pocket: "user_key",
      usage: { input_tokens: 1000, output_tokens: 200 },
      amount: 0.4,
      currency: "USD",
      priceBookVersion: "2026-07",
    },
    {
      runId: "r-2",
      subjectType: "course",
      subjectId: "c-1",
      seq: 1,
      component: "render",
      provider: "manim",
      model: null,
      pocket: "platform",
      usage: { compute_seconds: 12.5 },
      amount: 0.02,
      currency: "USD",
      priceBookVersion: "2026-07",
    },
  ];
}

describe("CourseCostPanel", () => {
  beforeEach(() => {
    fetchCourseCostMock.mockReset();
    fetchCourseCostEventsMock.mockReset();
    fetchCourseCostEventsMock.mockResolvedValue(ledger());
  });

  it("shows the headline total, the paid-call count and the who-paid split", async () => {
    fetchCourseCostMock.mockResolvedValue(meteredRollup());
    render(<CourseCostPanel apiBaseUrl="http://api.test" courseId="c-1" />);

    // The one accent metric — the total, locale-formatted.
    expect(await screen.findByText("$0.42")).toBeInTheDocument();
    // The drill-through affordance names how many calls it summed.
    expect(screen.getByRole("button", { name: /5 paid calls/i })).toBeInTheDocument();
    // The BYOK-vs-platform split is surfaced with both figures, scoped to each pocket's accessible
    // group (the same amounts also appear in the per-provider breakdown, so scope to disambiguate).
    const yourKey = screen.getByRole("group", { name: /your key/i });
    expect(within(yourKey).getByText("$0.40")).toBeInTheDocument();
    const platform = screen.getByRole("group", { name: /platform/i });
    expect(within(platform).getByText("$0.02")).toBeInTheDocument();
    expect(fetchCourseCostMock).toHaveBeenCalledWith("http://api.test", "c-1", expect.anything());
  });

  it("expands the ledger drill-through on demand", async () => {
    fetchCourseCostMock.mockResolvedValue(meteredRollup());
    render(<CourseCostPanel apiBaseUrl="http://api.test" courseId="c-1" />);

    const toggle = await screen.findByRole("button", { name: /5 paid calls/i });
    // The ledger isn't fetched until the drill-through is opened.
    expect(fetchCourseCostEventsMock).not.toHaveBeenCalled();

    fireEvent.click(toggle);

    // Now the ledger loads and its rows render (one per metered call), with the measured usage
    // round-tripped from the ledger (proving the drill-through shows the auditable units).
    await waitFor(() => expect(fetchCourseCostEventsMock).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("planner")).toBeInTheDocument();
    expect(screen.getByText("render")).toBeInTheDocument();
    expect(screen.getByText(/12\.5 compute_seconds/)).toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("surfaces the ledger's own load error with a retry that re-fetches it", async () => {
    fetchCourseCostMock.mockResolvedValue(meteredRollup());
    fetchCourseCostEventsMock.mockRejectedValueOnce(new Error("ledger down"));
    render(<CourseCostPanel apiBaseUrl="http://api.test" courseId="c-1" />);

    fireEvent.click(await screen.findByRole("button", { name: /5 paid calls/i }));

    // The ledger fails on its own (the rollup total above it is fine) — its own alert + retry show.
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fetchCourseCostEventsMock.mockResolvedValue(ledger());
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(await screen.findByText("planner")).toBeInTheDocument();
  });

  it("reads a keyless (~$0) build as free, not as missing data", async () => {
    fetchCourseCostMock.mockResolvedValue(keylessRollup());
    render(<CourseCostPanel apiBaseUrl="http://api.test" courseId="c-1" />);

    expect(await screen.findByText(/keyless build/i)).toBeInTheDocument();
    // Still names the calls it summed, so ~$0 reads as measured-and-free, not "no data".
    expect(screen.getByRole("button", { name: /3 paid calls/i })).toBeInTheDocument();
  });

  it("renders a calm 'not metered' note for a pre-feature course", async () => {
    fetchCourseCostMock.mockResolvedValue(null);
    render(<CourseCostPanel apiBaseUrl="http://api.test" courseId="c-1" />);

    expect(await screen.findByText(/not metered/i)).toBeInTheDocument();
    // No total, no drill-through toggle when there's nothing on record.
    expect(screen.queryByRole("button", { name: /paid calls/i })).not.toBeInTheDocument();
  });

  it("surfaces a load error with a retry that re-fetches", async () => {
    fetchCourseCostMock.mockRejectedValueOnce(new Error("boom"));
    render(<CourseCostPanel apiBaseUrl="http://api.test" courseId="c-1" />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: /retry/i });

    fetchCourseCostMock.mockResolvedValue(meteredRollup());
    fireEvent.click(retry);

    expect(await screen.findByText("$0.42")).toBeInTheDocument();
  });
});
