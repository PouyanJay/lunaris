import { useEffect } from "react";

import { putHeartbeat } from "../lib/activity";

/** One studied minute per beat, minute-bucketed server-side. */
const HEARTBEAT_INTERVAL_MS = 60_000;

/**
 * The reader's session heartbeat: beat once on mount and then once per minute, but ONLY while
 * the document is visible — a backgrounded tab accrues no study minutes (Page Visibility API).
 * `active` gates it to a mounted reader with a reachable API; everything is fire-and-forget
 * telemetry (a lost beat is never surfaced).
 */
export function useStudyHeartbeat(apiBaseUrl: string, active: boolean): void {
  useEffect(() => {
    if (!apiBaseUrl || !active) return;
    let timer: number | null = null;
    const beat = () => void putHeartbeat(apiBaseUrl);
    const start = () => {
      if (timer !== null) return;
      beat();
      timer = window.setInterval(beat, HEARTBEAT_INTERVAL_MS);
    };
    const stop = () => {
      if (timer === null) return;
      window.clearInterval(timer);
      timer = null;
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") start();
      else stop();
    };
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [apiBaseUrl, active]);
}
