import { useEffect, useState, type ReactNode } from "react";

import { fetchProdOpsSummary, type ProdOpsSummary } from "../../lib/prodOps";
import { Button } from "../primitives/Button";
import styles from "./AdminPortal.module.css";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; summary: ProdOpsSummary };

function messageFor(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback;
}

/** Prod operations: cost + compute charts and the on/off switch for the production environment.
 *  A section of the Admin Portal — owns its own loading/error state inline. The walking skeleton
 *  renders only the overview (which resource group + currency the figures cover); the charts and
 *  switch land in later tasks. */
export function ProdOpsSection({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchProdOpsSummary(apiBaseUrl, controller.signal)
      .then((summary) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", summary });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", message: messageFor(cause, "Could not load prod operations.") });
      });
    return () => controller.abort();
  }, [apiBaseUrl, reloadCount]);

  let body: ReactNode;
  if (state.status === "loading") {
    body = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading…
      </p>
    );
  } else if (state.status === "error") {
    body = (
      <div className={styles.statusRegion}>
        <p className={styles.error} role="alert">
          {state.message}
        </p>
        <div>
          <Button type="button" onClick={() => setReloadCount((n) => n + 1)}>
            Retry
          </Button>
        </div>
      </div>
    );
  } else {
    body = (
      <p className={styles.intro}>
        Figures cover{" "}
        <span className={styles.meta}>{state.summary.resourceGroup}</span>, reported in{" "}
        <span className={styles.meta}>{state.summary.currency}</span>.
      </p>
    );
  }

  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>Prod operations</h2>
      {body}
    </section>
  );
}
