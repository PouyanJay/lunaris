import { describe, expect, it } from "vitest";

import { groundingLedger, readinessScorecard } from "./instruments";
import { makeAgentEvent, makeProgressEvent } from "../test/fixtures";
import type { TrustTier } from "../types/course";

function source(sequence: number, tier: TrustTier, accepted = true, credibility = 0.9) {
  return makeAgentEvent("source_evaluated", sequence, {
    stage: "grounding_discovered",
    source: {
      kcId: "kc-1",
      domain: `d${sequence}.org`,
      trustTier: tier,
      credibility,
      sourceType: "reference",
      accepted,
      reason: "",
    },
  });
}

describe("groundingLedger", () => {
  it("is null before any grounding signal arrives", () => {
    expect(groundingLedger([makeProgressEvent("run_started", 0)], [])).toBeNull();
  });

  it("sums claim verdicts across modules and counts accepted sources by trust tier", () => {
    const events = [
      makeProgressEvent("claims_verified", 1, { claimsTotal: 10, claimsSupported: 8, claimsCut: 2 }),
      makeProgressEvent("claims_verified", 2, { claimsTotal: 5, claimsSupported: 5, claimsCut: 0 }),
    ];
    const agentEvents = [
      source(0, "official"),
      source(1, "official"),
      source(2, "reputable"),
      source(3, "open", false), // rejected — not a grounding source
    ];

    const ledger = groundingLedger(events, agentEvents)!;

    expect(ledger.supported).toBe(13);
    expect(ledger.cut).toBe(2);
    expect(ledger.sources).toBe(3);
    expect(ledger.trustMix).toEqual([
      { tier: "official", count: 2, pct: 67 },
      { tier: "reputable", count: 1, pct: 33 },
    ]);
  });
});

describe("readinessScorecard", () => {
  it("is empty before any source event exists — an instrument with no reading shows nothing", () => {
    expect(readinessScorecard([], [])).toEqual([]);
    expect(readinessScorecard([makeProgressEvent("run_started", 0)], [])).toEqual([]);
  });

  it("reads grounding as a clean success when nothing was cut", () => {
    const gauges = readinessScorecard(
      [makeProgressEvent("claims_verified", 0, { claimsTotal: 5, claimsSupported: 5, claimsCut: 0 })],
      [],
    );

    expect(gauges[0]).toMatchObject({ key: "grounding", value: "100%", tone: "success" });
  });

  it("renders only the gauges whose source events have arrived — no fake gauges", () => {
    const gauges = readinessScorecard(
      [
        makeProgressEvent("graph_built", 0, {
          edgeCount: 27,
          graph: { nodes: [], edges: [], frontier: [], isAcyclic: true, topoOrder: [] },
        }),
      ],
      [],
    );

    expect(gauges.map((gauge) => gauge.key)).toEqual(["structure"]);
    expect(gauges[0]!.value).toBe("acyclic");
    expect(gauges[0]!.tone).toBe("success");
  });

  it("derives grounding, coverage, and trust from their real events", () => {
    const events = [
      makeProgressEvent("claims_verified", 1, { claimsTotal: 10, claimsSupported: 8, claimsCut: 2 }),
      makeProgressEvent("coverage_verified", 2, { gapCount: 0 }),
    ];
    const agentEvents = [source(0, "official", true, 0.9), source(1, "open", true, 0.7)];

    const gauges = readinessScorecard(events, agentEvents);
    const byKey = new Map(gauges.map((gauge) => [gauge.key, gauge]));

    expect(byKey.get("grounding")!.value).toBe("80%");
    expect(byKey.get("grounding")!.tone).toBe("warning"); // claims were cut — a fact, not a gate
    expect(byKey.get("coverage")!.value).toBe("no gaps");
    expect(byKey.get("coverage")!.tone).toBe("success");
    expect(byKey.get("trust")!.value).toBe("80%"); // mean credibility of accepted sources
  });

  it("flags coverage gaps amber with the honest count", () => {
    const gauges = readinessScorecard([makeProgressEvent("coverage_verified", 0, { gapCount: 3 })], []);

    const coverage = gauges.find((gauge) => gauge.key === "coverage")!;
    expect(coverage.value).toBe("3 gaps");
    expect(coverage.tone).toBe("warning");
  });
});
