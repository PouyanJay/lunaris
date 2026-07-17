import type { CapabilityMode, CapabilityName } from "../types/course";
import { authedFetch } from "./apiClient";

/** Which provider a key-gated capability is using right now: its keyed provider ("live") or its
 *  keyless local fallback. Flips to "live" the moment the capability's key is stored. Tenant-aware
 *  under BYOK (reads the caller's own keys). */
export interface CapabilityStatus {
  capability: CapabilityName;
  mode: CapabilityMode;
  provider: string;
  /** For a keyless fallback that runs on the local model server (the LLM): whether inference is on
   *  GPU or CPU. Absent/null for live capabilities and keyless web services (search/video). */
  compute?: "cpu" | "gpu" | null;
}

/** Human label per capability — shared by the live settings badge and the per-course build tag so
 *  the two indicators name a capability identically. */
export const CAPABILITY_LABELS: Record<CapabilityName, string> = {
  llm: "Language model",
  embeddings: "Embeddings",
  search: "Web search",
  video: "Video",
  cover: "Image generation",
};

/** Fetch the per-capability live/fallback status. Best-effort: a failure resolves to an empty list
 *  (the Draft banner simply doesn't show) rather than throwing into the app shell. */
export async function fetchCapabilities(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<CapabilityStatus[]> {
  const response = await authedFetch(
    `${apiBaseUrl}/api/capabilities`,
    signal ? { signal } : undefined,
  );
  if (!response.ok) return [];
  const body = await response.json();
  return Array.isArray(body) ? (body as CapabilityStatus[]) : [];
}

/** Whether the language model runs on its keyless fallback — i.e. this user's explanations are
 *  keyless too, and the per-device compute choice applies. */
export function isLlmKeyless(capabilities: CapabilityStatus[]): boolean {
  return capabilities.some((c) => c.capability === "llm" && c.mode === "fallback");
}
