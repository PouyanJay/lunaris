import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { requestSimExchange } from "../../lib/requestSimExchange";
import { type SimContract, type SimEvent, type SimExchange } from "../../lib/simContract";
import { simGesture } from "../../lib/simGesture";
import { SimSessionContext } from "./SimSessionContext";

const MAX_EXCHANGES = 20;

/** Owns request/replay state and the iframe protocol independently of the visual host. */
export function useSimBridge(contract: SimContract, appId: string, active: boolean) {
  const context = useContext(SimSessionContext);
  const frame = useRef<HTMLIFrameElement>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const available = useRef(active);
  const pending = useRef<SimEvent | null>(null);
  const latest = useRef<SimExchange | undefined>(context?.exchanges.at(-1));
  const [message, setMessage] = useState(
    latest.current?.reaction.text ?? "Move a control, then discuss the change with your tutor.",
  );
  const [failed, setFailed] = useState(false);
  const [working, setWorking] = useState(false);
  const [ready, setReady] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    mounted.current = true;
    const timer = window.setTimeout(() => setUnavailable(true), 10000);
    return () => {
      mounted.current = false;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    available.current =
      active && !!context && (latest.current?.event.sequence ?? 0) < MAX_EXCHANGES;
    frame.current?.contentWindow?.postMessage(
      {
        type: "lunaris.sim.availability",
        version: 1,
        instanceId: context?.instanceId,
        active: available.current && !working && !pending.current,
      },
      "*",
    );
  }, [active, context, working]);

  const initialize = useCallback(() => {
    if (!context) return;
    frame.current?.contentWindow?.postMessage(
      {
        type: "lunaris.sim.init",
        version: 1,
        instanceId: context.instanceId,
        appId,
        state:
          latest.current?.reaction.state ??
          Object.fromEntries(
            Object.entries(contract.parameters).map(([key, p]) => [key, p.default]),
          ),
        active: available.current && !inFlight.current && !pending.current,
      },
      "*",
    );
  }, [context, appId, contract]);

  const applyExchange = useCallback(
    (exchange: SimExchange) => {
      latest.current = exchange;
      pending.current = null;
      setMessage(exchange.reaction.text);
      frame.current?.contentWindow?.postMessage(
        {
          type: "lunaris.sim.command",
          version: 1,
          instanceId: context?.instanceId,
          state: exchange.reaction.state,
          active: available.current && exchange.event.sequence < MAX_EXCHANGES,
        },
        "*",
      );
    },
    [context?.instanceId],
  );

  const send = useCallback(
    async (event: SimEvent) => {
      if (!context || inFlight.current || !available.current) return;
      inFlight.current = true;
      pending.current = event;
      setWorking(true);
      setFailed(false);
      try {
        const exchange = await requestSimExchange(
          `${context.apiBaseUrl}/api/live/sessions/${encodeURIComponent(context.sessionId)}/sim`,
          event,
          contract,
        );
        if (!mounted.current) return;
        applyExchange(exchange);
      } catch (error) {
        if (!mounted.current) return;
        setFailed(true);
        setMessage(error instanceof Error ? error.message : "The tutor could not respond.");
      } finally {
        inFlight.current = false;
        if (mounted.current) setWorking(false);
      }
    },
    [context, contract, applyExchange],
  );

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow || !event.data || event.data.version !== 1)
        return;
      const data = event.data;
      if (data.type === "lunaris.sim.ready") {
        setReady(true);
        initialize();
        return;
      }
      if (!available.current || !context || inFlight.current || pending.current) return;
      const gesture = simGesture(data, {
        contract,
        appId,
        context,
        sequence: (latest.current?.event.sequence ?? 0) + 1,
      });
      if (gesture) void send(gesture);
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [context, contract, appId, initialize, send]);

  return {
    frame,
    initialize,
    ready,
    unavailable,
    working,
    failed,
    message,
    markUnavailable: () => setUnavailable(true),
    retry: () => {
      if (pending.current) void send(pending.current);
    },
  };
}
