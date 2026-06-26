import { useEffect, useState, type ReactNode } from "react";

import {
  fetchProdCost,
  fetchProdOpsSummary,
  type ProdCostSeries,
  type ProdOpsSummary,
} from "../../lib/prodOps";
import { Button } from "../primitives/Button";
import { CostChart } from "./CostChart";
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

function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/** Prod operations: cost + compute charts and the on/off switch for the production environment.
 *  A section of the Admin Portal — owns its own loading/error state inline. */
export function ProdOpsSection({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [summary, setSummary] = useState<SummaryState>({ status: "loading" });
  const [cost, setCost] = useState<CostState>({ status: "loading" });
  const [days, setDays] = useState<number>(RANGES[0]);
  const [reloadCount, setReloadCount] = useState(0);

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

  let overview: ReactNode;
  if (summary.status === "loading") {
    overview = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading…
      </p>
    );
  } else if (summary.status === "error") {
    overview = (
      <div className={styles.statusRegion}>
        <p className={styles.error} role="alert">
          {summary.message}
        </p>
        <div>
          <Button type="button" onClick={() => setReloadCount((n) => n + 1)}>
            Retry
          </Button>
        </div>
      </div>
    );
  } else {
    overview = (
      <p className={styles.intro}>
        Figures cover <span className={prodOps.meta}>{summary.summary.resourceGroup}</span>,
        reported in <span className={prodOps.meta}>{summary.summary.currency}</span>.
      </p>
    );
  }

  let costBody: ReactNode;
  if (cost.status === "loading") {
    costBody = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading cost…
      </p>
    );
  } else if (cost.status === "error") {
    costBody = (
      <div className={styles.statusRegion}>
        <p className={styles.error} role="alert">
          {cost.message}
        </p>
        <div>
          <Button type="button" onClick={() => setReloadCount((n) => n + 1)}>
            Retry
          </Button>
        </div>
      </div>
    );
  } else {
    costBody = (
      <>
        <CostChart points={cost.series.points} currency={cost.series.currency} />
        <p className={prodOps.partialNote}>
          The most recent day is partial — billing data lags ~8-24h.
        </p>
      </>
    );
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>Prod operations</h2>
      {overview}
      <div className={prodOps.controls}>
        <span className={prodOps.controlLabel} id="cost-range-label">
          Cost per day
        </span>
        <div className={prodOps.rangeGroup} role="group" aria-labelledby="cost-range-label">
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
      {costBody}
    </section>
  );
}
