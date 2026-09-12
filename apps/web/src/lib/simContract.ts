/** Version 1 of Live's iframe bridge. This is not an MCP Apps protocol claim. */
export interface SimContract {
  version: 1;
  objective: string;
  parameters: Record<
    string,
    { label: string; minimum: number; maximum: number; step: number; default: number }
  >;
}

export interface SimEvent {
  version: 1;
  instanceId: string;
  turnSeq: number;
  sequence: number;
  appId: string;
  kind: "param_changed" | "milestone_reached" | "misconception_signal";
  state: Record<string, number>;
}

export interface SimExchange {
  event: SimEvent;
  reaction: { text: string; state: Record<string, number> };
  runId: string;
}

export function validSimState(
  contract: SimContract,
  state: unknown,
): state is Record<string, number> {
  if (!state || typeof state !== "object" || Array.isArray(state)) return false;
  const entries = Object.entries(state);
  if (entries.length !== Object.keys(contract.parameters).length) return false;
  return entries.every(([key, value]) => {
    const parameter = contract.parameters[key];
    if (!parameter || typeof value !== "number" || !Number.isFinite(value)) return false;
    const steps = (value - parameter.minimum) / parameter.step;
    return (
      value >= parameter.minimum &&
      value <= parameter.maximum &&
      Math.abs(steps - Math.round(steps)) < 1e-7
    );
  });
}
