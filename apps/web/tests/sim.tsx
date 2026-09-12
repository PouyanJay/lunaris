import React from "react";
import { createRoot } from "react-dom/client";
import { SimSessionContext } from "../src/components/live/SimSessionContext";
import { SurfaceCard } from "../src/components/live/SurfaceCard";
import "../src/index.css";
import { authedFetch } from "../src/lib/apiClient";

const query = new URLSearchParams(location.search);
const api = query.get("api")!;
const id = query.get("session");
const session = await authedFetch(id ? `${api}/api/live/sessions/${id}` : `${api}/test/session`, {
  method: id ? "GET" : "POST",
}).then((r) => r.json());
query.set("session", session.sessionId);
history.replaceState(null, "", `?${query}`);
const turn = session.turns.at(-1);
const surface = {
  ...turn.surface,
  url: turn.surface.url.startsWith("/api/live/sims/assets/")
    ? turn.surface.url
    : `${api}${turn.surface.url}`,
};
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <SimSessionContext.Provider
      value={{
        apiBaseUrl: api,
        sessionId: session.sessionId,
        turnSeq: turn.seq,
        instanceId: turn.runId,
        exchanges: turn.simExchanges,
      }}
    >
      <SurfaceCard spec={surface} busy={false} answerable onAnswer={() => {}} />
    </SimSessionContext.Provider>
  </React.StrictMode>,
);
