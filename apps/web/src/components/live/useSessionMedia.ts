import { useLayoutEffect, useMemo } from "react";
import { SessionMediaCoordinator } from "./SessionMediaCoordinator";

/** Fence local media to the exact API/session/turn and interrupt it before an answer runs. */
export function useSessionMedia(scope: string, busy: boolean): SessionMediaCoordinator {
  const coordinator = useMemo(() => new SessionMediaCoordinator(scope), [scope]);
  useLayoutEffect(() => () => coordinator.stopAll(), [coordinator]);
  useLayoutEffect(() => {
    if (busy) return coordinator.block("answer");
  }, [coordinator, busy]);
  return coordinator;
}
