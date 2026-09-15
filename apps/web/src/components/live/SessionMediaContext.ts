import { createContext } from "react";
import type { SessionMediaCoordinator } from "./SessionMediaCoordinator";

export const SessionMediaContext = createContext<SessionMediaCoordinator | null>(null);
