import { authedFetch } from "./apiClient";
import { validSimState, type SimContract, type SimEvent, type SimExchange } from "./simContract";

/** Submit one idempotent gesture to the authenticated host, never an iframe-provided URL. */
export async function requestSimExchange(
  endpoint: string,
  event: SimEvent,
  contract: SimContract,
): Promise<SimExchange> {
  const response = await authedFetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
    signal: AbortSignal.timeout(35000),
  });
  if (!response.ok)
    throw new Error("The tutor could not respond. Retry or continue with your explanation.");
  const exchange = (await response.json()) as SimExchange;
  if (
    exchange.event?.instanceId !== event.instanceId ||
    exchange.event.sequence !== event.sequence ||
    typeof exchange.reaction?.text !== "string" ||
    !validSimState(contract, exchange.reaction?.state)
  ) {
    throw new Error("The simulator response was invalid. Continue with your explanation.");
  }
  return exchange;
}
