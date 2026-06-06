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
