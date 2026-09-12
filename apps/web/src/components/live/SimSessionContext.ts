import { createContext } from "react";
import type { SimExchange } from "../../lib/simContract";

/** Host-owned session identity; an iframe never chooses the authenticated endpoint. */
export const SimSessionContext = createContext<{
  apiBaseUrl: string;
  sessionId: string;
  turnSeq: number;
  instanceId: string;
  exchanges: SimExchange[];
} | null>(null);
