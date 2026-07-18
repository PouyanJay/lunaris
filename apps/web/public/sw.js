// Course-cover image cache (library-instant-covers follow-up).
//
// Course covers are CONSTANT — an artwork only changes when it's regenerated, which mints a new
// job-id and therefore a new storage path. But each `/api/courses` read signs a fresh 1-hour token,
// so the cover URL rotates and the browser's URL-keyed HTTP cache re-downloads identical bytes every
// visit. This worker does cache-first for cover images keyed by the object PATH (token stripped), so
// the same artwork is served instantly from Cache Storage across reloads and tabs regardless of the
// token, and a regenerated cover (new path) naturally misses and re-fetches.
//
// It only ever handles cover-image GETs; every other request falls straight through to the network,
// so the app shell, API calls, and other assets are untouched. The URL logic mirrors the tested
// `src/lib/coverCache.ts` — keep the two in sync.

const CACHE = "lunaris-covers-v1";
const STORAGE_MARKER = "/storage/v1/";
const COVER_BUCKET_MARKER = "/course-covers/";

function isCoverImageUrl(rawUrl) {
  try {
    const { pathname } = new URL(rawUrl);
    return pathname.includes(STORAGE_MARKER) && pathname.includes(COVER_BUCKET_MARKER);
  } catch {
    return false;
  }
}

function coverCacheKey(rawUrl) {
  const url = new URL(rawUrl);
  url.searchParams.delete("token");
  return url.toString();
}

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Drop any older cover-cache versions, then take control of open pages this activation.
      const names = await caches.keys();
      await Promise.all(
        names
          .filter((name) => name.startsWith("lunaris-covers-") && name !== CACHE)
          .map((name) => caches.delete(name)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || !isCoverImageUrl(request.url)) return; // fall through untouched

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE);
      const key = coverCacheKey(request.url);
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
