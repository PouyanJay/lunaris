// Signed-storage image cache (library-instant-covers follow-up).
//
// Course covers and video posters are CONSTANT — the artwork only changes when it's regenerated,
// which mints a new job-id and therefore a new storage path. But each API read signs a fresh 1-hour
// token, so the signed URL rotates and the browser's URL-keyed HTTP cache re-downloads identical
// bytes every visit. This worker does cache-first for signed storage IMAGES (any private bucket)
// keyed by the object PATH (token stripped), so the same artwork is served instantly from Cache
// Storage across reloads and tabs regardless of the token, and a regenerated image (new path)
// naturally misses and re-fetches.
//
// It only ever handles signed-storage image GETs (covers, video posters, …) — non-image objects
// (mp4 video, captions) and every other request fall straight through to the network, so the app
// shell, API calls, and streamed media are untouched. The URL logic mirrors the tested
// `src/lib/imageCache.ts` — keep the two in sync.

const CACHE = "lunaris-images-v1";
const STORAGE_MARKER = "/storage/v1/";
const SIGNED_MARKER = "/sign/";
const RENDER_MARKER = "/render/image/";
const IMAGE_EXT = /\.(?:png|jpe?g|webp|avif|gif)$/i;

function isSignedStorageImage(rawUrl) {
  try {
    const { pathname } = new URL(rawUrl);
    if (!pathname.includes(STORAGE_MARKER) || !pathname.includes(SIGNED_MARKER)) return false;
    return pathname.includes(RENDER_MARKER) || IMAGE_EXT.test(pathname);
  } catch {
    return false;
  }
}

function storageImageCacheKey(rawUrl) {
  const url = new URL(rawUrl);
  url.searchParams.delete("token");
  return url.toString();
}

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Drop any older image-cache versions (incl. the former `lunaris-covers-*`), then take
      // control of open pages this activation.
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((name) => name.startsWith("lunaris-") && name !== CACHE)
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || !isSignedStorageImage(request.url)) return; // fall through

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const key = storageImageCacheKey(request.url);
      const hit = await cache.match(key);
      if (hit) return hit;

      const response = await fetch(request);
      // Cache a good fetch — including the cross-origin OPAQUE response the storage host returns
      // (no CORS); an opaque response still renders in an <img> and serves fine from cache. Never
      // cache an error, so a transient failure doesn't get pinned.
      if (response && (response.ok || response.type === "opaque")) {
        await cache.put(key, response.clone());
      }
      return response;
    })(),
  );
});
