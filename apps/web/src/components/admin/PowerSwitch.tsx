import { useEffect, useState, type ReactNode } from "react";

import { messageFor } from "../../lib/apiErrors";
import { fetchProdPower, setProdPower, type ProdPowerState } from "../../lib/prodOps";
import { Button } from "../primitives/Button";
import { ErrorWithRetry } from "./ErrorWithRetry";
import styles from "./AdminPortal.module.css";
import prodOps from "./ProdOps.module.css";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; power: ProdPowerState };

/** The full production on/off switch. OFF stops the prod apps (saves the always-on cost; only the
 *  fixed registry floor remains); ON restores them. Stopping prod is a self-inflicted outage, so the
 *  toggle requires an explicit inline confirmation. Talks to the always-on control plane (AD-3), not
 *  the API it governs, so it still works when prod is off. */
export function PowerSwitch({ controlBaseUrl }: { controlBaseUrl: string }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [confirming, setConfirming] = useState<null | boolean>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reloadCount, setReloadCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchProdPower(controlBaseUrl, controller.signal)
      .then((power) => {
        if (controller.signal.aborted) return;
        setState({ status: "ready", power });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setState({ status: "error", message: messageFor(cause, "Could not load power state.") });
      });
    return () => controller.abort();
  }, [controlBaseUrl, reloadCount]);

  async function apply(on: boolean) {
    setBusy(true);
    setActionError(null);
    try {
      const power = await setProdPower(controlBaseUrl, on);
      setState({ status: "ready", power });
      setConfirming(null);
    } catch (cause) {
      setActionError(messageFor(cause, "Could not change production power."));
    } finally {
      setBusy(false);
    }
  }

  let body: ReactNode;
  if (state.status === "loading") {
    body = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading power state…
      </p>
    );
  } else if (state.status === "error") {
    body = <ErrorWithRetry message={state.message} onRetry={() => setReloadCount((n) => n + 1)} />;
  } else {
    const { isOn, apps } = state.power;
    const target = !isOn;
    body = (
      <>
        <div className={prodOps.powerRow}>
          <span
            className={`${prodOps.powerBadge} ${isOn ? prodOps.powerOn : prodOps.powerOff}`}
            role="status"
          >
            {isOn ? "Production is ON" : "Production is OFF"}
          </span>
          {confirming === null && (
            <Button
              type="button"
              variant={isOn ? "danger" : "secondary"}
              onClick={() => {
                setActionError(null);
                setConfirming(target);
              }}
            >
              {isOn ? "Turn production off" : "Turn production on"}
            </Button>
          )}
        </div>

        {confirming !== null && (
          <div className={prodOps.confirmPanel} role="group" aria-label="Confirm power change">
            <p className={prodOps.confirmWarning}>
              {confirming
                ? "Start the prod apps and bring production back online?"
                : "Stop the prod apps? The site goes offline until you turn it back on. This zeroes the always-on cost; only the ~$0.25/day registry floor remains."}
            </p>
            <div className={prodOps.confirmActions}>
              <Button type="button" onClick={() => setConfirming(null)} disabled={busy}>
                Cancel
              </Button>
              <Button
                type="button"
                variant={confirming ? "secondary" : "danger"}
                onClick={() => void apply(confirming)}
                disabled={busy}
              >
                {busy
                  ? confirming
                    ? "Starting…"
                    : "Stopping…"
                  : confirming
                    ? "Confirm, turn on"
                    : "Confirm, turn off"}
              </Button>
            </div>
          </div>
        )}

        {actionError && (
          <p className={styles.error} role="alert">
            {actionError}
          </p>
        )}

        <ul className={prodOps.appList}>
          {apps.map((app) => (
            <li key={app.name} className={prodOps.appItem}>
              <span className={prodOps.meta}>{app.name}</span>
              <span className={app.running ? prodOps.appRunning : prodOps.appStopped}>
                {app.running ? "running" : "stopped"}
              </span>
            </li>
          ))}
        </ul>
      </>
    );
  }

  return (
    <>
      <h3 className={prodOps.subheading}>Production power</h3>
      {body}
    </>
  );
}
