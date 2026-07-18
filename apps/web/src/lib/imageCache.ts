// The image cache's URL logic, shared as the tested spec for the service worker in `public/sw.js`
// (which mirrors `isSignedStorageImage` + `storageImageCacheKey` verbatim — keep the two in sync).

const STORAGE_MARKER = "/storage/v1/";
const SIGNED_MARKER = "/sign/";
const RENDER_MARKER = "/render/image/";
const IMAGE_EXT = /\.(?:png|jpe?g|webp|avif|gif)$/i;

/** Whether a URL is a SIGNED Supabase-storage image — a course cover, a video poster, or any other
 *  private-bucket image whose signed URL rotates its token. These are the only requests the image
 *  cache handles, so app assets, API calls, and non-image files (mp4 video, captions) fall straight
 *  through. Matched by the signed-storage path plus the render/transform route or an image
 *  extension, so it works across every bucket without enumerating them. */
export function isSignedStorageImage(rawUrl: string): boolean {
  try {
    const { pathname } = new URL(rawUrl);
    if (!pathname.includes(STORAGE_MARKER) || !pathname.includes(SIGNED_MARKER)) return false;
    return pathname.includes(RENDER_MARKER) || IMAGE_EXT.test(pathname);
  } catch {
    return false;
  }
}

/** The content-stable cache key for a signed storage image: the URL minus its rotating `token`. The
 *  object is immutable per its path (a regenerate writes a new path) and the size/transform params
 *  stay on the key, so identical artwork maps to ONE cache entry no matter which short-lived token
 *  fetched it — the whole point of caching a constant image that hides behind a rotating signed URL. */
export function storageImageCacheKey(rawUrl: string): string {
  const url = new URL(rawUrl);
  url.searchParams.delete("token");
  return url.toString();
}

/** Register the image-cache service worker. Production builds only — a local Vite dev server needs
 *  no SW (and it only ever intercepts signed storage images regardless). Best-effort: a registration
 *  failure (no SW support, an insecure context) just means images load uncached, never a broken app. */
export function registerImageCache(): void {
  if (!import.meta.env.PROD || typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
    return;
  }
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {
      // An image that loads over the network (uncached) is fine — never surface a registration error.
    });
  });
}
