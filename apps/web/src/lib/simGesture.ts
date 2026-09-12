import { validSimState, type SimContract, type SimEvent } from "./simContract";

/** Validate untrusted iframe data before attaching the host-owned sequence and turn. */
export function simGesture(
  data: Record<string, unknown>,
  {
    contract,
    appId,
    context,
    sequence,
  }: {
    contract: SimContract;
    appId: string;
    context: { instanceId: string; turnSeq: number };
    sequence: number;
  },
): SimEvent | null {
  if (
    sequence > 20 ||
    data.type !== "lunaris.sim.event" ||
    data.instanceId !== context.instanceId ||
    data.appId !== appId ||
    !["param_changed", "milestone_reached", "misconception_signal"].includes(String(data.kind)) ||
    !validSimState(contract, data.state)
  )
    return null;
  return {
    version: 1,
    instanceId: context.instanceId,
    appId,
    turnSeq: context.turnSeq,
    sequence,
    kind: data.kind as SimEvent["kind"],
    state: data.state,
  };
}
