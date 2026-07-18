import { describe, expect, it } from "vitest";

import { isSignedStorageImage, storageImageCacheKey } from "./imageCache";

const COVER =
  "https://ref.supabase.co/storage/v1/object/sign/course-covers/u1/c1/job1/cover.png?token=AAA";
const COVER_RENDER =
  "https://ref.supabase.co/storage/v1/render/image/sign/course-covers/u1/c1/job1/cover.png?token=AAA&width=1280&height=720";
const VIDEO_POSTER =
  "https://ref.supabase.co/storage/v1/object/sign/course-videos/u1/c1/job1/poster.jpg?token=AAA";
const VIDEO_MP4 =
  "https://ref.supabase.co/storage/v1/object/sign/course-videos/u1/c1/job1/final.mp4?token=AAA";
const VIDEO_CAPTIONS =
  "https://ref.supabase.co/storage/v1/object/sign/course-videos/u1/c1/job1/captions.vtt?token=AAA";

describe("isSignedStorageImage", () => {
  it("matches signed storage IMAGES across buckets — covers and video posters", () => {
    expect(isSignedStorageImage(COVER)).toBe(true);
    expect(isSignedStorageImage(COVER_RENDER)).toBe(true); // the transform/render route
    expect(isSignedStorageImage(VIDEO_POSTER)).toBe(true); // a different bucket, still an image
  });

  it("does NOT match non-image storage objects (mp4 video, captions)", () => {
    expect(isSignedStorageImage(VIDEO_MP4)).toBe(false);
    expect(isSignedStorageImage(VIDEO_CAPTIONS)).toBe(false);
  });

  it("ignores everything that isn't a signed storage image (app assets, API, junk)", () => {
    expect(isSignedStorageImage("https://lunaris.pouyan.ai/assets/index-abc.js")).toBe(false);
    expect(isSignedStorageImage("https://api.lunaris.pouyan.ai/api/courses")).toBe(false);
    // A PUBLIC (unsigned) image isn't our rotating-URL problem — leave it to the browser cache.
    expect(isSignedStorageImage("https://cdn.example.com/logo.png")).toBe(false);
    expect(isSignedStorageImage("not a url")).toBe(false);
  });
});

describe("storageImageCacheKey", () => {
  it("strips the rotating token so a constant image maps to one key across tokens", () => {
    const a = COVER;
    const b = COVER.replace("token=AAA", "token=ZZZ");

    expect(storageImageCacheKey(a)).toBe(storageImageCacheKey(b));
    expect(storageImageCacheKey(a)).not.toContain("token=");
  });

  it("keeps the size/transform params (a thumb and its master are distinct entries)", () => {
    const key = storageImageCacheKey(COVER_RENDER);
    expect(key).toContain("width=1280");
    expect(key).toContain("height=720");
    expect(key).not.toContain("token=");
  });

  it("keeps the object path so twins and different buckets never collide", () => {
    const dark = storageImageCacheKey(COVER);
    const light = storageImageCacheKey(COVER.replace("cover.png", "cover-light.png"));
    expect(dark).not.toBe(light);
    expect(storageImageCacheKey(COVER)).not.toBe(storageImageCacheKey(VIDEO_POSTER));
  });
});
