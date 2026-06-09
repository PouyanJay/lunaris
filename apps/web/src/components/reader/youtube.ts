/** Extract a YouTube video id from a URL (watch?v=, youtu.be/, /embed/, /shorts/), or null when the
 *  URL isn't a recognisable YouTube video — so the resource thumbnail can hotlink the real frame
 *  (`i.ytimg.com/vi/<id>/hqdefault.jpg`) for videos and fall back to a glyph for everything else. */
const ID = /^[\w-]{11}$/;

export function youTubeId(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  const host = parsed.hostname.replace(/^www\./, "");
  if (host === "youtu.be") {
    const id = parsed.pathname.slice(1);
    return ID.test(id) ? id : null;
  }
  if (host === "youtube.com" || host === "m.youtube.com" || host === "youtube-nocookie.com") {
    const v = parsed.searchParams.get("v");
    if (v && ID.test(v)) return v;
    const path = parsed.pathname.match(/^\/(?:embed|shorts)\/([\w-]{11})/);
    if (path) return path[1] ?? null;
  }
  return null;
}

export function youTubeThumbnail(id: string): string {
  return `https://i.ytimg.com/vi/${id}/hqdefault.jpg`;
}

/** Referrer policy for the embed iframes. `youtube-nocookie.com` (privacy mode) validates the
 *  embedding domain from the request `Referer`, so it needs at least the origin. Prod serves the SPA
 *  with `Referrer-Policy: same-origin` (no referrer is sent cross-origin) → the player fails with
 *  "Error 153 · Video player configuration error". Setting this per-iframe overrides the document
 *  policy for just these frames, sending the origin to YouTube while leaving the app's policy intact.
 *  (It works on localhost because the dev server sends no such header.) */
export const YOUTUBE_EMBED_REFERRER_POLICY = "strict-origin-when-cross-origin";

/** The privacy-enhanced embed URL (`youtube-nocookie.com`) for in-reader playback. `autoplay` is set
 *  only after a user gesture (a click on the facade), and `rel=0` keeps related videos in-channel. */
export function youTubeEmbed(id: string, options: { autoplay?: boolean } = {}): string {
  const params = new URLSearchParams({ rel: "0", modestbranding: "1" });
  if (options.autoplay) params.set("autoplay", "1");
  return `https://www.youtube-nocookie.com/embed/${id}?${params.toString()}`;
}
