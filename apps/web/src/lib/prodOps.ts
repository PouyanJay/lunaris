import { detailOf } from "./apiErrors";
import { authedFetch } from "./apiClient";

/** The prod-operations overview (mirrors the API's ProdOpsSummaryView). */
export interface ProdOpsSummary {
  resourceGroup: string;
  currency: string;
}

/** One day's Azure spend (mirrors the API's CostPointView). `isPartial` marks the most recent day,
 *  whose figure is still settling (Cost Management lags ~8-24h). */
export interface ProdCostPoint {
  day: string;
  amount: number;
  isPartial: boolean;
}

/** Daily Azure spend for the cost chart (mirrors the API's CostSeriesView), oldest day first. */
export interface ProdCostSeries {
  currency: string;
  points: ProdCostPoint[];
}

/** One hour of prod compute (mirrors the API's ComputePointView): usage + amortized cost. */
export interface ProdComputePoint {
  hour: string;
  replicas: number;
  cpuCores: number;
  memoryGb: number;
  cost: number;
}

/** Hourly prod compute for the dual-axis chart (mirrors ComputeSeriesView), oldest hour first. */
export interface ProdComputeSeries {
  currency: string;
  points: ProdComputePoint[];
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

/** Admin: daily Azure spend over the last `days` days (default 7). 403 unless the caller is admin. */
export async function fetchProdCost(
  apiBaseUrl: string,
  days: number,
  signal?: AbortSignal,
): Promise<ProdCostSeries> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/admin/prod-ops/cost?days=${days}`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new ProdOpsError("Could not reach the prod-operations service.", { cause });
  }
  if (!response.ok) {
    throw new ProdOpsError(
      (await detailOf(response)) ?? `Could not load prod cost (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as ProdCostSeries;
}

/** Admin: hourly compute (usage + cost) over the last `days` days. 403 unless the caller is admin. */
export async function fetchProdCompute(
  apiBaseUrl: string,
  days: number,
  signal?: AbortSignal,
): Promise<ProdComputeSeries> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/admin/prod-ops/compute?days=${days}`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new ProdOpsError("Could not reach the prod-operations service.", { cause });
  }
  if (!response.ok) {
    throw new ProdOpsError(
      (await detailOf(response)) ?? `Could not load prod compute (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as ProdComputeSeries;
}
