import { detailOf } from "./apiErrors";
import { authedFetch } from "./apiClient";

/** The per-course cost breakdown (mirrors the rollup's `breakdown` JSONB). Amounts are in the
 *  rollup's `currency`; the maps are keyed by the raw provider / component / pocket identifiers. */
export interface CostBreakdown {
  /** Per pipeline-stage subtotal, e.g. `{ planner: 0.02, render: 0.003 }`. */
  byComponent: Record<string, number>;
  /** Per provider subtotal, e.g. `{ anthropic: 0.4, voyage: 0.01, manim: 0.003 }`. */
  byProvider: Record<string, number>;
  /** The who-paid split: `{ user_key, platform }` — BYOK spend vs Lunaris-platform spend. */
  byPocket: Record<string, number>;
  /** How many metered calls the total was summed from (the "from N paid calls" count). */
  eventCount: number;
}

/** A course's build-cost rollup (mirrors the API's `CourseCost`): the total the Overview reads,
 *  plus the breakdown behind it. `GET /api/courses/{id}/cost` returns `null` for a course that was
 *  never metered (built before metering, still building, or another owner's). */
export interface CourseCost {
  courseId: string;
  totalAmount: number;
  currency: string;
  breakdown: CostBreakdown;
  priceBookVersion: string;
  updatedAt: string;
}

/** One row of the append-only cost ledger (mirrors the API's `CostEvent`) — a single metered call,
 *  the drill-through behind the total. `usage` is the raw measured units the `amount` was
 *  calculated from (e.g. `{ input_tokens, output_tokens }`, `{ chars }`, `{ compute_seconds }`). */
export interface CostEvent {
  runId: string;
  courseId: string;
  seq: number;
  component: string;
  provider: string;
  model: string | null;
  pocket: string;
  usage: Record<string, number>;
  amount: number;
  currency: string;
  priceBookVersion: string;
}

export class CostError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "CostError";
  }
}

/** Format an amount as locale-aware currency, falling back to `1.23 USD` if the code is unknown. */
export function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

/** The course's build-cost rollup, or `null` when the course has no metered cost (a 200 null body,
 *  not a 404 — the panel renders it as a "not metered" state, not an error). */
export async function fetchCourseCost(
  apiBaseUrl: string,
  courseId: string,
  signal?: AbortSignal,
): Promise<CourseCost | null> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/cost`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new CostError("Could not reach the cost service.", { cause });
  }
  if (!response.ok) {
    throw new CostError(
      (await detailOf(response)) ?? `Could not load the build cost (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as CourseCost | null;
}

/** The course's full cost ledger for the drill-through, in emission order. An unmetered course
 *  returns an empty list (never a 404). */
export async function fetchCourseCostEvents(
  apiBaseUrl: string,
  courseId: string,
  signal?: AbortSignal,
): Promise<CostEvent[]> {
  let response: Response;
  try {
    response = await authedFetch(
      `${apiBaseUrl}/api/courses/${encodeURIComponent(courseId)}/cost/events`,
      signal ? { signal } : undefined,
    );
  } catch (cause) {
    throw new CostError("Could not reach the cost service.", { cause });
  }
  if (!response.ok) {
    throw new CostError(
      (await detailOf(response)) ?? `Could not load the cost breakdown (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as CostEvent[];
}
