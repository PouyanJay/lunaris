import { describe, expect, it } from "vitest";
import { isNodeAsset } from "./liveMaterials";

const digest = "a".repeat(64);
const locator = `video:job:${digest}:0:0`;
const material = {
  assetId: "clip",
  kind: "video_clip",
  origin: "ingested",
  locator,
  sourceDigest: digest,
  title: "Consent",
  excerpt: "Consent has a purpose.",
  sourceLabel: "Course",
  verification: { runId: "r", verifierVersion: "v1", sourceDigest: digest },
  clip: {
    jobId: "job",
    sourceDigest: digest,
    locator,
    startS: 2,
    endS: 5,
    durationS: 10,
    title: "Consent",
    transcript: [{ startS: 2, endS: 5, text: "Consent has a purpose." }],
  },
};
describe("public material boundary", () => {
  it("accepts original verified clip evidence", () => expect(isNodeAsset(material)).toBe(true));
  it.each([
    { ...material, locator: "https://storage.test/signed?token=private" },
    { ...material, clip: { ...material.clip, endS: Infinity } },
    { ...material, clip: { ...material.clip, locator: `video:other:${digest}:0:0` } },
    {
      ...material,
      clip: { ...material.clip, transcript: [{ startS: 1, endS: 5, text: "outside" }] },
    },
    { ...material, clip: null },
    { ...material, answerKey: "private" },
    { ...material, kind: { toString: null } },
  ])("refuses malformed or private material", (value) => expect(isNodeAsset(value)).toBe(false));
  it("permits unverified legacy lesson references but never treats them as verified", () => {
    expect(isNodeAsset({ ...material, kind: "lesson", clip: null, verification: null })).toBe(true);
  });
});
