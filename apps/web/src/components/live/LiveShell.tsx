import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import { ConceptMap } from "./ConceptMap";
import { ConceptSpecPanel } from "./ConceptSpecPanel";
import { SessionList } from "./SessionList";
import { SessionView } from "./SessionView";
import { useLiveGraph } from "../../hooks/useLiveGraph";
import { type ConceptGraph } from "../../lib/liveGraph";
import { ROUTES } from "../../lib/routes";
import { BrandMark } from "../shell/BrandMark";
import styles from "./LiveShell.module.css";

/** Where a learner's own sessions are listed. Lives beside the shell that routes to it rather than
 *  in `routes.ts`, which is Studio's route table: `resolveProductRoute` already claims everything
 *  under `/live`, so this is Live's own business. */
export const LIVE_SESSIONS_PATH = "/live/sessions";

interface LiveShellProps {
  /** Where the API lives — threaded from the app root, as every other request surface is. */
  apiBaseUrl: string;
}

/** Lunaris Live's app shell.
 *
 *  A topic arrives from the composer and a session opens on it at once (P2c, U5): the tutor is
 *  talking within seconds, the map compiles behind the conversation, and nobody watches a progress
 *  bar. A map the learner already has (`?graph=`) is the other way in — read it, then start a
 *  session on it — which is the opening P2a and P2b built and U1 keeps.
 *
 *  Loaded lazily by {@link ProductRouter} so Live's dependencies never reach Studio's bundle. */
export default function LiveShell({ apiBaseUrl }: LiveShellProps) {
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const topic = params.get("topic")?.trim();
  const graphId = params.get("graph")?.trim();
  // Live's first sub-route. Read here rather than through a nested router because the shell has
  // exactly two destinations and a router for two is more machinery than either of them needs.
  const listing = pathname === LIVE_SESSIONS_PATH || pathname === `${LIVE_SESSIONS_PATH}/`;

  useEffect(() => {
    const previous = document.title;
    document.title = topic ? `${topic} · Lunaris Live` : "Lunaris Live";
    return () => {
      document.title = previous;
    };
  }, [topic]);

  return (
    <div className={styles.shell}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <BrandMark size={24} />
          <span className={styles.wordmark}>Lunaris</span>
        </div>
      </header>
      {listing ? (
        <main className={styles.canvas} data-state="sessions">
          <SessionList apiBaseUrl={apiBaseUrl} />
        </main>
      ) : topic ? (
        <main className={styles.canvas} data-state="session">
          <div className={styles.teaching}>
            <SessionView
              apiBaseUrl={apiBaseUrl}
              topic={topic}
              copilotUrl={import.meta.env.VITE_COPILOT_URL}
            />
          </div>
        </main>
      ) : graphId ? (
        <MapEntry apiBaseUrl={apiBaseUrl} graphId={graphId} />
      ) : (
        <main className={styles.canvas} data-state="idle">
          <IdleState />
        </main>
      )}
    </div>
  );
}

/** A map the learner already has, read from the store, and the way into a session on it. */
function MapEntry({ apiBaseUrl, graphId }: { apiBaseUrl: string; graphId: string }) {
  const { state, retry } = useLiveGraph(apiBaseUrl, graphId);
  return (
    <main className={styles.canvas} data-state={state.status}>
      {state.status === "loading" ? <LoadingMap /> : null}
      {state.status === "failed" ? <FailedState message={state.message} onRetry={retry} /> : null}
      {state.status === "ready" ? (
        <MapWorkspace graph={state.graph} apiBaseUrl={apiBaseUrl} />
      ) : null}
    </main>
  );
}

/** The map beside the notes for whichever concept is open — and the way into a session on it. The
 *  map is a map of the subject, never a route through the session: it is what a learner reads
 *  *before* being taught, and what keeps score once they are. */
function MapWorkspace({ graph, apiBaseUrl }: { graph: ConceptGraph; apiBaseUrl: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [teaching, setTeaching] = useState(false);
  const selected = graph.nodes.find((node) => node.id === selectedId) ?? null;

  if (teaching) {
    return (
      <div className={styles.teaching}>
        <button type="button" className={styles.back} onClick={() => setTeaching(false)}>
          &larr; Back to the map
        </button>
        <SessionView
          apiBaseUrl={apiBaseUrl}
          graphId={graph.graphId}
          topic={graph.topic}
          copilotUrl={import.meta.env.VITE_COPILOT_URL}
        />
      </div>
    );
  }

  return (
    <div className={styles.mapArea}>
      <div className={styles.startBar}>
        <p className={styles.startLead}>
          {graph.nodes.length} concepts, ordered so nothing arrives before what it needs.
        </p>
        <button type="button" className={styles.start} onClick={() => setTeaching(true)}>
          Start a session
        </button>
      </div>
      <div className={styles.workspace}>
        <ConceptMap
          graph={graph}
          selectedId={selected?.id ?? null}
          onSelect={(id) => setSelectedId((current) => (current === id ? null : id))}
        />
        {selected && (
          <ConceptSpecPanel graph={graph} concept={selected} onClose={() => setSelectedId(null)} />
        )}
      </div>
    </div>
  );
}

/** No topic yet — Live cannot open a session on nothing, so it says what it needs and where. */
function IdleState() {
  return (
    <div className={styles.empty}>
      <p className={`eyebrow ${styles.eyebrow}`}>Nothing to start yet</p>
      <h1 className={styles.title}>Lunaris Live</h1>
      <p className={styles.body}>
        Name a topic and Live starts a session on it straight away — a few questions about you while
        it works out what the subject is made of, then the teaching begins.
      </p>
      <Link to={ROUTES.home} className={styles.action}>
        Name a topic
      </Link>
    </div>
  );
}

/** The gap between asking for a map and having it: one read, so a sentence rather than a bar. */
function LoadingMap() {
  return (
    <p className={styles.body} role="status">
      Opening the map…
    </p>
  );
}

/** A map that could not be read is recoverable — the id is still known, so retrying is one press. */
function FailedState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.empty}>
      <p className={`eyebrow ${styles.eyebrow}`}>Couldn&rsquo;t open the map</p>
      <p className={styles.body} role="alert">
        {message}
      </p>
      <button type="button" className={styles.action} onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
