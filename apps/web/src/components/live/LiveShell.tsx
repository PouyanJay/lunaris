import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { CompilingState } from "./CompilingState";
import { ConceptMap } from "./ConceptMap";
import { ConceptSpecPanel } from "./ConceptSpecPanel";
import { SessionView } from "./SessionView";
import { useCompileGraph } from "../../hooks/useCompileGraph";
import { type ConceptGraph } from "../../lib/liveGraph";
import { ROUTES } from "../../lib/routes";
import { BrandMark } from "../shell/BrandMark";
import styles from "./LiveShell.module.css";

interface LiveShellProps {
  /** Where the API lives — threaded from the app root, as every other request surface is. */
  apiBaseUrl: string;
}

/** Lunaris Live's app shell.
 *
 *  A topic arrives from the composer and Live builds its concept map — what the subject is made of,
 *  what has to be learned before what, and what each concept expects a learner to end up able to
 *  do. Nothing teaches yet; the session loop is Phase 2, and this surface is how the map is
 *  inspected before there is one.
 *
 *  Loaded lazily by {@link ProductRouter} so Live's dependencies never reach Studio's bundle. */
export default function LiveShell({ apiBaseUrl }: LiveShellProps) {
  const topic = useSearchParams()[0].get("topic")?.trim();
  const { state, retry } = useCompileGraph(apiBaseUrl, topic);

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
      <main className={styles.canvas} data-state={state.status}>
        {state.status === "idle" ? <IdleState /> : null}
        {state.status === "compiling" ? (
          <CompilingState topic={topic ?? ""} progress={state.progress} />
        ) : null}
        {state.status === "failed" ? <FailedState message={state.message} onRetry={retry} /> : null}
        {state.status === "ready" ? (
          <MapWorkspace graph={state.graph} apiBaseUrl={apiBaseUrl} />
        ) : null}
      </main>
    </div>
  );
}

/** The compiled map beside the notes for whichever concept is open — and the way into a session on
 *  it. The map is a map of the subject, never a route through the session: it is what a learner
 *  reads *before* being taught, and what keeps score once they are. */
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
        <SessionView apiBaseUrl={apiBaseUrl} graphId={graph.graphId} topic={graph.topic} />
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

/** No topic yet — Live cannot compile nothing, so it says what it needs and where to say it. */
function IdleState() {
  return (
    <div className={styles.empty}>
      <p className={`eyebrow ${styles.eyebrow}`}>Nothing to build yet</p>
      <h1 className={styles.title}>Lunaris Live</h1>
      <p className={styles.body}>
        Name a topic and Live works out what it is made of — every idea in it, and what you need to
        understand before what.
      </p>
      <Link to={ROUTES.home} className={styles.action}>
        Name a topic
      </Link>
    </div>
  );
}

/** A failed compile is recoverable — the topic is still known, so retrying is one press. */
function FailedState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className={styles.empty}>
      <p className={`eyebrow ${styles.eyebrow}`}>Couldn&rsquo;t build the map</p>
      <p className={styles.body} role="alert">
        {message}
      </p>
      <button type="button" className={styles.action} onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
