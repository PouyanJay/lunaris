import { authedFetch } from "./apiClient";

/** The keyless serverless-GPU endpoint's serve-readiness, mirroring the API ReadinessStatus
 *  (keyless-fallbacks T8). The runtime list is the single source; the type is derived from it so the
 *  two can't drift: `ready` (loaded), `provisioning` (the GPU is waking / the model is loading),
 *  `unreachable` (no endpoint wired), `not_applicable` (the caller's LLM is keyed — no GPU). */
const KEYLESS_READINESS_STATUSES = [
  "ready",
  "provisioning",
  "unreachable",
  "not_applicable",
] as const;

export type KeylessReadinessStatus = (typeof KEYLESS_READINESS_STATUSES)[number];

/** Probe whether the keyless GPU is ready. Best-effort: any failure (or an unexpected shape) resolves
 *  to `null` so the provisioning UI simply doesn't show, rather than throwing into the build view. */
export async function fetchKeylessReadiness(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<KeylessReadinessStatus | null> {
  const response = await authedFetch(
    `${apiBaseUrl}/api/keyless/readiness`,
    signal ? { signal } : undefined,
  );
  if (!response.ok) return null;
  const body = await response.json();
  const status = body?.status;
  return (KEYLESS_READINESS_STATUSES as readonly string[]).includes(status)
    ? (status as KeylessReadinessStatus)
    : null;
}
