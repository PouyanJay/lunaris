import { authedFetch } from "./apiClient";

/** The signed-in caller's identity, plus whether they may manage the signup invite-gate. */
export interface MeView {
  userId: string;
  isAdmin: boolean;
}

/** Fetch the authenticated caller's identity. Throws on a non-2xx (e.g. 401 when not signed in). */
export async function fetchMe(apiBaseUrl: string, signal?: AbortSignal): Promise<MeView> {
  const response = await authedFetch(
    `${apiBaseUrl}/api/me`,
    signal ? { signal } : undefined,
  );
  if (!response.ok) {
    throw new Error(`Could not load your identity (HTTP ${response.status}).`);
  }
  return (await response.json()) as MeView;
}
