import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { messageFor } from "../../lib/apiErrors";
import {
  fetchProdPower,
  powerChangeWasSent,
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

const LOAD_FAILED = "Could not load power state.";

const CONFIRM_COPY = {
  on: "Start every prod app and the simulator VM? Everything takes a few minutes to come up, and this page follows it.",
  off: "Stop every prod app and deallocate the simulator VM? Lunaris goes offline for everyone until you turn it back on. Compute billing stops; only storage costs remain (the container registry and the VM’s disk and IP).",
};

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

function confirmLabel(on: boolean, busy: boolean): string {
  if (busy) return on ? "Starting…" : "Stopping…";
  return on ? "Confirm, turn on" : "Confirm, turn off";
}

/** The power state, loaded on mount (and on `reload`, after an error). `refresh` re-reads without
 *  blanking the view, so the list stays put while it updates. */
function usePowerState(controlBaseUrl: string) {
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [reloadCount, setReloadCount] = useState(0);

  const refresh = useCallback(
    (signal?: AbortSignal) =>
      fetchProdPower(controlBaseUrl, signal)
        .then((power) => {
          if (!signal?.aborted) setLoad({ status: "ready", power });
        })
        .catch((cause) => {
          if (!signal?.aborted)
            setLoad({ status: "error", message: messageFor(cause, LOAD_FAILED) });
        }),
    [controlBaseUrl],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoad({ status: "loading" });
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh, reloadCount]);

  return {
    load,
    show: (power: ProdPowerState) => setLoad({ status: "ready", power }),
    refresh,
    reload: () => setReloadCount((n) => n + 1),
  };
}

/** Follows a change under way: re-reads every 5s while `load` is still moving (towards `target`),
 *  for up to ten minutes, after which `expired` is set until `restart`. */
function usePowerWatch(load: Load, target: boolean | null, refresh: (s?: AbortSignal) => unknown) {
  const [expired, setExpired] = useState(false);
  const startedAt = useRef<number | null>(null);
  const changing = load.status === "ready" && !expired && isChanging(load.power, target);

  useEffect(() => {
    if (!changing) {
      startedAt.current = null;
      return;
    }
    startedAt.current ??= Date.now();
    if (Date.now() - startedAt.current >= WATCH_LIMIT_MS) {
      setExpired(true);
      return;
    }
    // Re-armed by every landed read (`load` changes), even when nothing moved.
    const controller = new AbortController();
    const timer = setTimeout(() => void refresh(controller.signal), POLL_INTERVAL_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [changing, load, refresh]);

  return { changing, expired, restart: () => setExpired(false) };
}

/** The full production on/off switch. OFF stops every prod app and deallocates the simulator VM
 *  (compute billing stops; only storage remains); ON restores them. Stopping prod is a
 *  self-inflicted outage, so the toggle requires an explicit inline confirmation. Azure applies
 *  the change in the background, so the switch follows it until every resource has finished.
 *  Talks to the always-on control plane (AD-3), not the API it governs, so it still works when
 *  prod is off. */
export function PowerSwitch({ controlBaseUrl }: { controlBaseUrl: string }) {
  const { load, show, refresh, reload } = usePowerState(controlBaseUrl);
  // The direction last sent to Azure from this page; null until a change actually went out.
  const [target, setTarget] = useState<boolean | null>(null);
  const { changing, expired, restart } = usePowerWatch(load, target, refresh);
  const [confirming, setConfirming] = useState<null | boolean>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function apply(on: boolean) {
    setBusy(true);
    setActionError(null);
    restart();
    try {
      const power = await setProdPower(controlBaseUrl, on);
      setTarget(on);
      show(power);
    } catch (cause) {
      setActionError(messageFor(cause, "Could not change production power."));
      // Follow the change only if it reached Azure; a refusal before that changed nothing.
      if (powerChangeWasSent(cause)) setTarget(on);
      void refresh();
    } finally {
      setConfirming(null);
      setBusy(false);
    }
  }

  function askToConfirm(on: boolean) {
    setActionError(null);
    setConfirming(on);
  }

  function refreshNow() {
    restart();
    void refresh();
  }

  if (load.status === "loading") {
    return (
      <Section>
        <p className={styles.status} role="status" aria-live="polite">
          Loading power state…
        </p>
      </Section>
    );
  }
  if (load.status === "error") {
    return (
      <Section>
        <ErrorWithRetry message={load.message} onRetry={reload} />
      </Section>
    );
  }

  const { power } = load;
  return (
    <Section>
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
            onClick={() => askToConfirm(!power.isOn)}
          >
            {power.isOn ? "Turn production off" : "Turn production on"}
          </Button>
        )}
      </div>

      {confirming !== null && (
        <ConfirmPanel
          on={confirming}
          busy={busy}
          onCancel={() => setConfirming(null)}
          onConfirm={() => void apply(confirming)}
        />
      )}

      {actionError && (
        <p className={styles.error} role="alert">
          {actionError}
        </p>
      )}

      {expired && <WatchExpiredNote onRefresh={refreshNow} />}

      <ResourceList resources={power.resources} target={target} />
    </Section>
  );
}

function Section({ children }: { children: ReactNode }) {
  return (
    <>
      <h3 className={prodOps.subheading}>Production power</h3>
      {children}
    </>
  );
}

function ConfirmPanel({
  on,
  busy,
  onCancel,
  onConfirm,
}: {
  on: boolean;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className={prodOps.confirmPanel} role="group" aria-label="Confirm power change">
      <p className={prodOps.confirmWarning}>{on ? CONFIRM_COPY.on : CONFIRM_COPY.off}</p>
      <div className={prodOps.confirmActions}>
        <Button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button
          type="button"
          variant={on ? "secondary" : "danger"}
          onClick={onConfirm}
          disabled={busy}
        >
          {confirmLabel(on, busy)}
        </Button>
      </div>
    </div>
  );
}

function WatchExpiredNote({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className={prodOps.watchNote}>
      <p className={prodOps.confirmWarning}>
        Still changing after 10 minutes. Refresh to check where things stand.
      </p>
      <Button type="button" onClick={onRefresh}>
        Refresh
      </Button>
    </div>
  );
}

function ResourceList({
  resources,
  target,
}: {
  resources: ProdResourcePower[];
  target: boolean | null;
}) {
  return (
    <ul className={prodOps.appList}>
      {resources.map((resource) => {
        const status = statusOf(resource, target);
        return (
          <li key={resource.name} className={prodOps.appItem}>
            <span className={prodOps.resourceName}>
              <span className={prodOps.resourceLabel}>{resource.name}</span>
              {resource.kind === "virtual_machine" && <span className={prodOps.kindTag}>VM</span>}
            </span>
            <StatusDot label={status.label} tone={status.tone} live={status.live} />
          </li>
        );
      })}
    </ul>
  );
}
