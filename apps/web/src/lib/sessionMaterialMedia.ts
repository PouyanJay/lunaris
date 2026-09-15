import { authedFetch } from "./apiClient";

interface MaterialScope {
  apiBaseUrl: string;
  sessionId: string;
  turnSeq: number;
}

/** Resolve current authorized playback access without caching a signed URL. */
export async function sessionMaterialMedia(
  scope: MaterialScope,
  assetId: string,
  signal: AbortSignal,
): Promise<string> {
  const response = await authedFetch(
    `${scope.apiBaseUrl}/api/live/sessions/${encodeURIComponent(scope.sessionId)}/materials/${encodeURIComponent(assetId)}/media?turn=${scope.turnSeq}`,
    { signal, cache: "no-store" },
  );
  if (!response.ok) throw new Error("Material unavailable");
  const body: unknown = await response.json();
  if (!body || typeof body !== "object" || !("url" in body) || typeof body.url !== "string")
    throw new Error("Invalid media response");
  return body.url;
}
