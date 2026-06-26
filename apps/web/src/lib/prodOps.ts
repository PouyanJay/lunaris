import { detailOf } from "./apiErrors";
import { authedFetch } from "./apiClient";

/** The prod-operations overview (mirrors the API's ProdOpsSummaryView). */
export interface ProdOpsSummary {
  resourceGroup: string;
  currency: string;
}

export class ProdOpsError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "ProdOpsError";
  }
}

/** Admin: the prod-operations overview. 403 unless the caller is an admin. */
export async function fetchProdOpsSummary(
  apiBaseUrl: string,
  signal?: AbortSignal,
): Promise<ProdOpsSummary> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/admin/prod-ops/summary`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new ProdOpsError("Could not reach the prod-operations service.", { cause });
  }
  if (!response.ok) {
    throw new ProdOpsError(
      (await detailOf(response)) ?? `Could not load prod operations (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as ProdOpsSummary;
}
