import { useEffect, useState, type ReactNode } from "react";

import {
  fetchProdCompute,
  fetchProdCost,
  fetchProdOpsSummary,
  prodControlBaseUrl,
  type ProdComputeSeries,
  type ProdCostSeries,
  type ProdOpsSummary,
} from "../../lib/prodOps";
import { Button } from "../primitives/Button";
import { ComputeChart } from "./ComputeChart";
import { CostChart } from "./CostChart";
import { PowerSwitch } from "./PowerSwitch";
import styles from "./AdminPortal.module.css";
import prodOps from "./ProdOps.module.css";

const RANGES = [7, 14, 30] as const;

type SummaryState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; summary: ProdOpsSummary };

type CostState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; series: ProdCostSeries };

type ComputeState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; series: ProdComputeSeries };

function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

function ErrorWithRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.statusRegion}>
      <p className={styles.error} role="alert">
        {message}
      </p>
      <div>
        <Button type="button" onClick={onRetry}>
          Retry
        </Button>
      </div>
    </div>
  );
}

/** Prod operations: cost + compute charts and (later) the on/off switch for production. A section of
 *  the Admin Portal — owns its own loading/error state inline; a shared window drives both charts. */
export function ProdOpsSection({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [summary, setSummary] = useState<SummaryState>({ status: "loading" });
  const [cost, setCost] = useState<CostState>({ status: "loading" });
  const [compute, setCompute] = useState<ComputeState>({ status: "loading" });
  const [days, setDays] = useState<number>(RANGES[0]);
  const [reloadCount, setReloadCount] = useState(0);

  const retry = () => setReloadCount((n) => n + 1);

  useEffect(() => {
    const controller = new AbortController();
    setSummary({ status: "loading" });
    fetchProdOpsSummary(apiBaseUrl, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setSummary({ status: "ready", summary: value });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setSummary({
          status: "error",
          message: messageFor(cause, "Could not load prod operations."),
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl, reloadCount]);

  useEffect(() => {
    const controller = new AbortController();
    setCost({ status: "loading" });
    fetchProdCost(apiBaseUrl, days, controller.signal)
      .then((series) => {
        if (controller.signal.aborted) return;
        setCost({ status: "ready", series });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setCost({ status: "error", message: messageFor(cause, "Could not load prod cost.") });
      });
    return () => controller.abort();
  }, [apiBaseUrl, days, reloadCount]);

  useEffect(() => {
    const controller = new AbortController();
    setCompute({ status: "loading" });
    fetchProdCompute(apiBaseUrl, days, controller.signal)
      .then((series) => {
        if (controller.signal.aborted) return;
        setCompute({ status: "ready", series });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setCompute({ status: "error", message: messageFor(cause, "Could not load prod compute.") });
      });
    return () => controller.abort();
  }, [apiBaseUrl, days, reloadCount]);

  let overview: ReactNode;
  if (summary.status === "loading") {
    overview = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading…
      </p>
    );
  } else if (summary.status === "error") {
    overview = <ErrorWithRetry message={summary.message} onRetry={retry} />;
  } else {
    overview = (
      <p className={styles.intro}>
        Figures cover <span className={prodOps.meta}>{summary.summary.resourceGroup}</span>,
        reported in <span className={prodOps.meta}>{summary.summary.currency}</span>.
      </p>
    );
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>Prod operations</h2>
      {overview}

      <div className={prodOps.controls}>
        <span className={prodOps.controlLabel} id="window-label">
          Window
        </span>
        <div className={prodOps.rangeGroup} role="group" aria-labelledby="window-label">
          {RANGES.map((value) => (
            <button
              key={value}
              type="button"
              className={`${prodOps.rangeButton} ${value === days ? prodOps.rangeButtonActive : ""}`}
              aria-pressed={value === days}
              onClick={() => setDays(value)}
            >
              {value}d
            </button>
          ))}
        </div>
      </div>

      <h3 className={prodOps.subheading}>Cost per day</h3>
      {cost.status === "loading" ? (
        <p className={styles.status} role="status" aria-live="polite">
          Loading cost…
        </p>
      ) : cost.status === "error" ? (
        <ErrorWithRetry message={cost.message} onRetry={retry} />
      ) : (
        <>
          <CostChart points={cost.series.points} currency={cost.series.currency} />
          <p className={prodOps.partialNote}>
            The most recent day is partial — billing data lags ~8-24h.
          </p>
        </>
      )}

      <h3 className={prodOps.subheading}>Compute per hour</h3>
      {compute.status === "loading" ? (
        <p className={styles.status} role="status" aria-live="polite">
          Loading compute…
        </p>
      ) : compute.status === "error" ? (
        <ErrorWithRetry message={compute.message} onRetry={retry} />
      ) : (
        <ComputeChart points={compute.series.points} currency={compute.series.currency} />
      )}

      <PowerSwitch controlBaseUrl={prodControlBaseUrl(apiBaseUrl)} />
    </section>
  );
}
