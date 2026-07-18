import { describe, expect, it } from "vitest";

import { coverCacheKey, isCoverImageUrl } from "./coverCache";

const SIGN =
  "https://ref.supabase.co/storage/v1/object/sign/course-covers/u1/c1/job1/cover.png?token=AAA";
const RENDER =
  "https://ref.supabase.co/storage/v1/render/image/sign/course-covers/u1/c1/job1/cover.png?token=AAA&width=1280&height=720";

describe("isCoverImageUrl", () => {
  it("matches Supabase cover-storage URLs — object and render/transform routes", () => {
    expect(isCoverImageUrl(SIGN)).toBe(true);
    expect(isCoverImageUrl(RENDER)).toBe(true);
  });

  it("ignores everything that isn't a cover image (app assets, API, other buckets)", () => {
    expect(isCoverImageUrl("https://lunaris.pouyan.ai/assets/index-abc.js")).toBe(false);
    expect(isCoverImageUrl("https://api.lunaris.pouyan.ai/api/courses")).toBe(false);
    // A different storage bucket must not be swept into the cover cache.
    expect(
      isCoverImageUrl("https://ref.supabase.co/storage/v1/object/sign/course-videos/x/mp4?token=A"),
    ).toBe(false);
    expect(isCoverImageUrl("not a url")).toBe(false);
  });
});

describe("coverCacheKey", () => {
  it("strips the rotating token so a constant cover maps to one key across tokens", () => {
    const a = "https://ref.supabase.co/storage/v1/object/sign/course-covers/c/j/cover.png?token=AAA";
    const b = "https://ref.supabase.co/storage/v1/object/sign/course-covers/c/j/cover.png?token=ZZZ";

    expect(coverCacheKey(a)).toBe(coverCacheKey(b));
    expect(coverCacheKey(a)).not.toContain("token=");
  });

  it("keeps the size/transform params (a thumb and its master are distinct entries)", () => {
    const key = coverCacheKey(RENDER);
    expect(key).toContain("width=1280");
    expect(key).toContain("height=720");
    expect(key).not.toContain("token=");
  });

  it("keeps the object path so the dark and light twins never collide", () => {
    const dark = coverCacheKey(
      "https://ref.supabase.co/storage/v1/object/sign/course-covers/c/j/cover.png?token=AAA",
    );
    const light = coverCacheKey(
      "https://ref.supabase.co/storage/v1/object/sign/course-covers/c/j/cover-light.png?token=AAA",
    );
    expect(dark).not.toBe(light);
  });
});
