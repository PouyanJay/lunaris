// The cover cache's URL logic, shared as the tested spec for the service worker in `public/sw.js`
// (which mirrors `isCoverImageUrl` + `coverCacheKey` verbatim — keep the two in sync).

const STORAGE_MARKER = "/storage/v1/";
const COVER_BUCKET_MARKER = "/course-covers/";

/** Whether a URL is a course-cover image served from Supabase storage — the only requests the cover
 *  cache handles, so app assets and API calls fall straight through. Both the object and the
 *  render/transform routes carry the private cover bucket in their path. */
export function isCoverImageUrl(rawUrl: string): boolean {
  try {
    const { pathname } = new URL(rawUrl);
    return pathname.includes(STORAGE_MARKER) && pathname.includes(COVER_BUCKET_MARKER);
  } catch {
    return false;
  }
}

/** The content-stable cache key for a cover URL: the signed URL minus its rotating `token`. A cover
 *  is immutable per its job-id path and the size/transform params stay on the key, so identical
 *  artwork maps to ONE cache entry no matter which short-lived token fetched it — the whole point of
 *  caching a constant image that hides behind a rotating signed URL. */
export function coverCacheKey(rawUrl: string): string {
  const url = new URL(rawUrl);
  url.searchParams.delete("token");
  return url.toString();
}

/** Register the cover-cache service worker. Production builds only — a local Vite dev server needs no
 *  SW (and it only ever intercepts cover images regardless). Best-effort: a registration failure (no
 *  SW support, an insecure context) just means covers load uncached, never a broken app. */
export function registerCoverCache(): void {
  if (!import.meta.env.PROD || typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return;
  }
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {
      // A cover that loads over the network (uncached) is fine — never surface a registration error.
    });
  });
}
