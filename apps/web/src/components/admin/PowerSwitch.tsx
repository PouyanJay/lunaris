import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { messageFor } from "../../lib/apiErrors";
import {
  fetchProdPower,
  setProdPower,
  type ProdPowerState,
  type ProdResourcePower,
} from "../../lib/prodOps";
import { Button } from "../primitives/Button";
import { StatusDot, type StatusTone } from "../primitives/StatusDot";
import { ErrorWithRetry } from "./ErrorWithRetry";
import styles from "./AdminPortal.module.css";
import prodOps from "./ProdOps.module.css";

/** How often a change under way is re-read. Azure accepts a start/stop at once and finishes it in
 *  the background; a VM takes a few minutes. */
const POLL_INTERVAL_MS = 5_000;
/** How long a change is followed before the switch stops asking and offers a manual refresh. */
const WATCH_LIMIT_MS = 10 * 60_000;

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; power: ProdPowerState };

/** Whether `power` is still moving: towards `target` (the direction asked for on this page), or,
 *  when nothing was asked here, simply not settled yet. */
function isChanging(power: ProdPowerState, target: boolean | null): boolean {
  if (target === null) return !power.settled;
  const goal = target ? "running" : "stopped";
  return power.resources.some((resource) => resource.status !== goal);
}

function headline(power: ProdPowerState, changing: boolean, target: boolean | null): string {
  if (changing) {
    if (target === null) return "Production is changing…";
    return target ? "Turning production on…" : "Turning production off…";
  }
  return power.isOn ? "Production is ON" : "Production is OFF";
}

function statusOf(
  resource: ProdResourcePower,
  target: boolean | null,
): { label: string; tone: StatusTone; live: boolean } {
  switch (resource.status) {
    case "running":
      return { label: "Running", tone: "success", live: false };
    case "stopped":
      return { label: "Stopped", tone: "neutral", live: false };
    case "unknown":
      return { label: "Unknown", tone: "danger", live: false };
    case "transitioning": {
      const label = target === null ? "Changing" : target ? "Starting" : "Stopping";
      return { label, tone: "accent", live: true };
    }
  }
}

/** The full production on/off switch. OFF stops every prod app and deallocates the simulator VM
 *  (compute billing stops; only storage remains); ON restores them. Stopping prod is a
 *  self-inflicted outage, so the toggle requires an explicit inline confirmation. Azure applies
 *  the change in the background, so the switch follows it until every resource has finished.
 *  Talks to the always-on control plane (AD-3), not the API it governs, so it still works when
 *  prod is off. */
export function PowerSwitch({ controlBaseUrl }: { controlBaseUrl: string }) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [confirming, setConfirming] = useState<null | boolean>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // The direction last asked for on this page; null until the admin changes anything.
  const [target, setTarget] = useState<boolean | null>(null);
  const [watchExpired, setWatchExpired] = useState(false);
  const [reloadCount, setReloadCount] = useState(0);
  const watchStartedAt = useRef<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoad({ status: "loading" });
    fetchProdPower(controlBaseUrl, controller.signal)
      .then((power) => {
        if (controller.signal.aborted) return;
        setLoad({ status: "ready", power });
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setLoad({ status: "error", message: messageFor(cause, "Could not load power state.") });
      });
    return () => controller.abort();
  }, [controlBaseUrl, reloadCount]);

  // Re-read without blanking the view (the list stays put while it refreshes).
  const refresh = useCallback(
    (signal?: AbortSignal) =>
      fetchProdPower(controlBaseUrl, signal)
        .then((power) => {
          if (!signal?.aborted) setLoad({ status: "ready", power });
        })
        .catch((cause) => {
          if (signal?.aborted) return;
          setLoad({ status: "error", message: messageFor(cause, "Could not load power state.") });
        }),
    [controlBaseUrl],
  );

  const changing = load.status === "ready" && !watchExpired && isChanging(load.power, target);

  useEffect(() => {
    if (!changing) {
      watchStartedAt.current = null;
      return;
    }
    watchStartedAt.current ??= Date.now();
    if (Date.now() - watchStartedAt.current >= WATCH_LIMIT_MS) {
      setWatchExpired(true);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => void refresh(controller.signal), POLL_INTERVAL_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
    // `load` re-arms the next read after each one lands, even when nothing moved.
  }, [changing, load, refresh]);

  async function apply(on: boolean) {
    setBusy(true);
    setActionError(null);
    setWatchExpired(false);
    try {
      const power = await setProdPower(controlBaseUrl, on);
      // Only once Azure has accepted the change does the switch say it is under way.
      setTarget(on);
      setLoad({ status: "ready", power });
    } catch (cause) {
      setTarget(on);
      setActionError(messageFor(cause, "Could not change production power."));
      // Part of the change may have gone out; show where things actually stand.
      void refresh();
    } finally {
      setConfirming(null);
      setBusy(false);
    }
  }

  function refreshNow() {
    setWatchExpired(false);
    void refresh();
  }

  let body: ReactNode;
  if (load.status === "loading") {
    body = (
      <p className={styles.status} role="status" aria-live="polite">
        Loading power state…
      </p>
    );
  } else if (load.status === "error") {
    body = <ErrorWithRetry message={load.message} onRetry={() => setReloadCount((n) => n + 1)} />;
  } else {
    const { power } = load;
    body = (
      <>
        <div className={prodOps.powerRow}>
          <span
            className={`${prodOps.powerBadge} ${power.isOn ? prodOps.powerOn : prodOps.powerOff}`}
            role="status"
          >
            {headline(power, changing, target)}
          </span>
          {confirming === null && !changing && (
            <Button
              type="button"
              variant={power.isOn ? "danger" : "secondary"}
              onClick={() => {
                setActionError(null);
                setConfirming(!power.isOn);
              }}
            >
              {power.isOn ? "Turn production off" : "Turn production on"}
            </Button>
          )}
        </div>

        {confirming !== null && (
          <div className={prodOps.confirmPanel} role="group" aria-label="Confirm power change">
            <p className={prodOps.confirmWarning}>
              {confirming
                ? "Start every prod app and the simulator VM? Everything takes a few minutes to come up, and this page follows it."
                : "Stop every prod app and deallocate the simulator VM? Lunaris goes offline for everyone until you turn it back on. Compute billing stops; only storage costs remain (the container registry and the VM’s disk and IP)."}
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

        {watchExpired && (
          <div className={prodOps.watchNote}>
            <p className={prodOps.confirmWarning}>
              Still changing after 10 minutes. Refresh to check where things stand.
            </p>
            <Button type="button" onClick={refreshNow}>
              Refresh
            </Button>
          </div>
        )}

        <ul className={prodOps.appList}>
          {power.resources.map((resource) => {
            const status = statusOf(resource, target);
            return (
              <li key={resource.name} className={prodOps.appItem}>
                <span className={prodOps.resourceName}>
                  <span className={prodOps.resourceLabel}>{resource.name}</span>
                  {resource.kind === "virtual_machine" && (
                    <span className={prodOps.kindTag}>VM</span>
                  )}
                </span>
                <StatusDot label={status.label} tone={status.tone} live={status.live} />
              </li>
            );
          })}
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
