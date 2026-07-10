import { describe, expect, it } from "vitest";

import type { CoverArtifact } from "../types/course";
import { coverProgress, isCoverTerminal, resolveCoverJobId } from "./coverJobs";

describe("coverProgress", () => {
  it("rises monotonically through the working stages", () => {
    const working = ["queued", "art_directing", "rendering", "qa", "uploading"] as const;
    const percents = working.map((s) => coverProgress(s).percent);
    const ascending = percents.every((p, i) => i === 0 || p > percents[i - 1]!);
    expect(ascending).toBe(true);
    expect(percents.at(-1)).toBeLessThan(100); // still short of done while uploading
  });

  it("labels each stage in plain language", () => {
    expect(coverProgress("art_directing").label).toMatch(/art-direct/i);
    expect(coverProgress("ready").percent).toBe(100);
  });
});

describe("isCoverTerminal", () => {
  it("is true only for settled states", () => {
    expect(isCoverTerminal("ready")).toBe(true);
    expect(isCoverTerminal("failed")).toBe(true);
    expect(isCoverTerminal("cancelled")).toBe(true);
    expect(isCoverTerminal("rendering")).toBe(false);
    expect(isCoverTerminal("queued")).toBe(false);
  });
});

describe("resolveCoverJobId", () => {
  it("prefers the provenance jobId, falling back to the artifact's own", () => {
    const withProvenance = {
      status: "ready",
      jobId: "artifact-id",
      provenance: { jobId: "provenance-id" },
    } as CoverArtifact;
    expect(resolveCoverJobId(withProvenance)).toBe("provenance-id");

    const failed = { status: "failed", jobId: "artifact-id" } as CoverArtifact;
    expect(resolveCoverJobId(failed)).toBe("artifact-id");

    expect(resolveCoverJobId(null)).toBeNull();
  });
});
