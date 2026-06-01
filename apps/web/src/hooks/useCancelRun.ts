import { useCallback, useState } from "react";

import { cancelRun } from "../lib/loadCourse";

interface CancelRun {
  /** The run_id currently being cancelled (drives a pending affordance), or null. */
  cancellingRunId: string | null;
  /** Cancel an in-flight run by its run_id, then refresh the history (it flips to CANCELLED).
   *  A missing run_id is a no-op (defensive — a running run always carries one). */
  cancel: (runId: string | undefined) => void;
}

/** Cancel an in-flight build: POST the cancel, then reload the run history so the run shows its
 *  terminal status. A failed or raced cancel (e.g. it just finished → 404) is swallowed — the
 *  refresh reconciles the true status, so cancel stays a safe, no-confirm action. */
export function useCancelRun(apiBaseUrl: string, reloadRuns: () => void): CancelRun {
  const [cancellingRunId, setCancellingRunId] = useState<string | null>(null);
  const cancel = useCallback(
    (runId: string | undefined) => {
      if (!runId) return;
      setCancellingRunId(runId);
      cancelRun(apiBaseUrl, runId)
        .catch(() => {
          // 404 (already finished) or a transport error — reconciled by the refresh below.
        })
        .finally(() => {
          setCancellingRunId(null);
          reloadRuns();
        });
    },
    [apiBaseUrl, reloadRuns],
  );
  return { cancellingRunId, cancel };
}
