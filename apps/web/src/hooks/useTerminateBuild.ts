import { useCallback, useRef, useState } from "react";

import { cancelRun, CourseLoadError } from "../lib/loadCourse";

interface TerminateBuild {
  /** Whether the terminate confirmation is showing. */
  isConfirming: boolean;
  /** Whether the terminate is in flight (the confirm is disabled + shows a pending label). */
  isTerminating: boolean;
  /** A failed terminate's reason, surfaced in the dialog (the build keeps running). */
  terminateError: string | null;
  /** Ask to terminate the live build — opens the confirm. `runId` targets the running build. */
  request: (runId: string | undefined) => void;
  /** Dismiss the confirm without terminating (no-op while terminating). */
  dismiss: () => void;
  /** Confirm: cancel the build server-side, then stop the local stream. */
  confirm: () => void;
}

/** Terminate the live (streaming) build behind a confirm step. Cancels server-side FIRST — so the
 *  run lands CANCELLED, not the disconnect→FAILED path — then resets the local stream and refreshes
 *  the history. On a real failure the dialog stays open with the reason (the build keeps running);
 *  a 404 means it already finished, so we just stop locally. Kept out of StudioApp to stay lean. */
export function useTerminateBuild(
  apiBaseUrl: string,
  resetStream: () => void,
  reloadRuns: () => void,
): TerminateBuild {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isTerminating, setIsTerminating] = useState(false);
  const [terminateError, setTerminateError] = useState<string | null>(null);
  const runIdRef = useRef<string | undefined>(undefined);

  const request = useCallback((runId: string | undefined) => {
    runIdRef.current = runId;
    setTerminateError(null);
    setIsConfirming(true);
  }, []);

  const dismiss = useCallback(() => {
    if (!isTerminating) setIsConfirming(false);
  }, [isTerminating]);

  const stopLocally = useCallback(() => {
    resetStream();
    reloadRuns();
    setIsConfirming(false);
  }, [resetStream, reloadRuns]);

  const confirm = useCallback(async () => {
    const runId = runIdRef.current;
    setIsTerminating(true);
    setTerminateError(null);
    try {
      if (runId !== undefined) await cancelRun(apiBaseUrl, runId);
      stopLocally();
    } catch (error: unknown) {
      // 404 = the run already finished (a race) → terminating is moot, just stop locally. Any other
      // failure means the build may still be running, so keep the dialog open with the reason.
      if (error instanceof CourseLoadError && error.status === 404) {
        stopLocally();
      } else {
        setTerminateError(error instanceof Error ? error.message : "Couldn’t terminate the build.");
      }
    } finally {
      setIsTerminating(false);
    }
  }, [apiBaseUrl, stopLocally]);

  return { isConfirming, isTerminating, terminateError, request, dismiss, confirm };
}
