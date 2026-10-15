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

/** What kind of Azure resource the switch governs (mirrors the API's ResourceKind). */
export type ProdResourceKind = "container_app" | "virtual_machine";

/** One resource's power status (mirrors PowerStatus). `transitioning` while Azure is still starting
 *  or stopping it; `unknown` for a state Azure reported that is neither (it is not waited on). */
export type ProdPowerStatus = "running" | "stopped" | "transitioning" | "unknown";

/** One governed prod resource's run state (mirrors ResourcePowerView). */
export interface ProdResourcePower {
  name: string;
  kind: ProdResourceKind;
  status: ProdPowerStatus;
  running: boolean;
}

/** Whether production is on, plus each governed resource's run state (mirrors PowerStateView).
 *  `settled` is false while any resource is mid-transition. */
export interface ProdPowerState {
  isOn: boolean;
  settled: boolean;
  resources: ProdResourcePower[];
}

/** Where the power switch talks to. Production stops the main API itself (AD-3), so the start/stop
 *  control is served by a separate always-on control app — `VITE_PROD_CONTROL_URL` points at it.
 *  Falls back to the API base for local/dev where the same router serves the route. */
export function prodControlBaseUrl(apiBaseUrl: string): string {
  const configured = import.meta.env.VITE_PROD_CONTROL_URL as string | undefined;
  return configured && configured.length > 0 ? configured : apiBaseUrl;
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

/** Admin: whether production is on + each app's run state. 403 unless the caller is admin. */
export async function fetchProdPower(
  controlBaseUrl: string,
  signal?: AbortSignal,
): Promise<ProdPowerState> {
  let response: Response;
  try {
    response = await authedFetch(
      `${controlBaseUrl}/api/admin/prod-ops/power`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new ProdOpsError("Could not reach the prod-operations service.", { cause });
  }
  if (!response.ok) {
    throw new ProdOpsError(
      (await detailOf(response)) ?? `Could not load prod power state (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as ProdPowerState;
}

/** Admin: start (`on=true`) or stop (`on=false`) production. The caller has already confirmed in the
 *  UI, so `confirm: true` is sent. Returns the new state. */
export async function setProdPower(controlBaseUrl: string, on: boolean): Promise<ProdPowerState> {
  let response: Response;
  try {
    response = await authedFetch(`${controlBaseUrl}/api/admin/prod-ops/power`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on, confirm: true }),
    });
  } catch (cause) {
    throw new ProdOpsError("Could not reach the prod-operations service.", { cause });
  }
  if (!response.ok) {
    throw new ProdOpsError(
      (await detailOf(response)) ?? `Could not change production power (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as ProdPowerState;
}
