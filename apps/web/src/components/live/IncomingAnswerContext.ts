import { createContext } from "react";

export interface IncomingAnswer {
  id: string;
  text: string;
}

/** A scoped draft target; only the active text composer receives an incoming recording. */
export const IncomingAnswerContext = createContext<IncomingAnswer | null>(null);
