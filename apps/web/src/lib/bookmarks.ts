import { authedFetch } from "./apiClient";

export type BookmarkKind = "lesson" | "concept" | "source";

/** The longest claim quote a source bookmark stores — mirrors the DB's snippet check. */
export const MAX_SNIPPET_LENGTH = 2000;

export interface Bookmark {
  kind: BookmarkKind;
  courseId: string;
  targetId: string;
  courseTitle?: string | null;
  title?: string | null;
  lessonId?: string | null;
  snippet?: string | null;
  conceptTier?: number | null;
  trustTier?: string | null;
  credibility?: number | null;
  note?: string | null;
  savedAt: string;
}

/** What a save affordance sends — everything but savedAt (the server stamps it). */
export type BookmarkDraft = Omit<Bookmark, "savedAt">;

/** The toggle's natural key — the client never knows row ids. */
export interface BookmarkRef {
  kind: BookmarkKind;
  courseId: string;
  targetId: string;
}

export class BookmarksError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "BookmarksError";
  }
}

/** Fetch the caller's saves (newest first). Rejects with BookmarksError on transport/HTTP
 *  failure — and on an alien payload shape (trust-boundary check: consumers read fields
 *  unguarded). */
export async function fetchBookmarks(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<Bookmark[]> {
  let response: Response;
  try {
    response = await authedFetch(`${apiBaseUrl}/api/bookmarks`, signal ? { signal } : undefined);
  } catch (cause) {
    throw new BookmarksError("Could not reach your bookmarks.", { cause });
  }
  if (!response.ok) {
    throw new BookmarksError(`Couldn't load your bookmarks (HTTP ${response.status}).`);
  }
  const body = (await response.json()) as Bookmark[] | null;
  if (!Array.isArray(body) || body.some((item) => typeof item?.targetId !== "string")) {
    throw new BookmarksError("Couldn't read your bookmarks (unexpected response).");
  }
  return body;
}

/** Save (idempotent upsert on the natural key). Rejects on failure so the caller can reconcile
 *  an optimistic toggle. */
export async function putBookmark(apiBaseUrl: string, draft: BookmarkDraft): Promise<void> {
  const response = await authedFetch(`${apiBaseUrl}/api/bookmarks`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!response.ok)
    throw new BookmarksError(`Couldn't save the bookmark (HTTP ${response.status}).`);
}

/** Remove by the natural key (idempotent). Rejects on failure for optimistic reconcile. */
export async function deleteBookmark(apiBaseUrl: string, ref: BookmarkRef): Promise<void> {
  const params = new URLSearchParams({
    kind: ref.kind,
    courseId: ref.courseId,
    targetId: ref.targetId,
  });
  const response = await authedFetch(`${apiBaseUrl}/api/bookmarks?${params}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new BookmarksError(`Couldn't remove the bookmark (HTTP ${response.status}).`);
  }
}
