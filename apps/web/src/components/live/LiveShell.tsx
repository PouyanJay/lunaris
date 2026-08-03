import { useEffect } from "react";
import { Link, useSearchParams } from "react-router";

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
 *  Phase 1 fills the Phase 0 placeholder with the compile plane: a topic arrives from the composer
 *  and Live builds its concept map — what the subject is made of, and what has to be learned before
 *  what. Nothing teaches yet; the session loop is Phase 2.
 *
 *  This is the walking-skeleton surface. It renders the map as an ordered list rather than a laid
 *  out graph, because T1's job is to prove the whole path (web → API → compiler → store) rather
 *  than to be the finished canvas — T7 builds that.
 *
 *  Loaded lazily by {@link ProductRouter} so Live's dependencies never reach Studio's bundle. */
export default function LiveShell({ apiBaseUrl }: LiveShellProps) {
  const topic = useSearchParams()[0].get("topic")?.trim();
  const { state, retry } = useCompileGraph(apiBaseUrl, topic);

  useEffect(() => {
    const previous = document.title;
    document.title = "Lunaris Live";
    return () => {
      document.title = previous;
    };
  }, []);

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
        {state.status === "compiling" ? <CompilingState topic={topic ?? ""} /> : null}
        {state.status === "failed" ? <FailedState message={state.message} onRetry={retry} /> : null}
        {state.status === "ready" ? <ConceptMap graph={state.graph} /> : null}
      </main>
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

/** The compile takes minutes, so this is the state a learner sees most. It says what is happening
 *  rather than spinning — Phase 2 replaces the wait entirely with the placement interview. */
function CompilingState({ topic }: { topic: string }) {
  return (
    <div className={styles.empty} role="status" aria-live="polite">
      <p className={`eyebrow ${styles.eyebrow}`}>Working out what this is made of</p>
      <h1 className={styles.title}>{topic}</h1>
      <p className={styles.body}>
        Live is mapping the ideas in this topic and the order they have to be learned in. This takes
        a couple of minutes.
      </p>
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

/** The compiled map, in the order the concepts have to be learned — the walking skeleton's honest
 *  rendering of a DAG the server has already sorted. T7 lays it out as a graph. */
function ConceptMap({ graph }: { graph: ConceptGraph }) {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const ordered = graph.topoOrder
    .map((id) => byId.get(id))
    .filter((node): node is NonNullable<typeof node> => node !== undefined);

  return (
    <div className={styles.map}>
      <header className={styles.mapHead}>
        <p className={`eyebrow ${styles.eyebrow}`}>Concept map</p>
        <h1 className={styles.title}>{graph.topic}</h1>
        <p className={styles.mapMeta}>
          <span className="mono">{graph.nodes.length}</span> concepts, in the order they have to be
          learned.
        </p>
      </header>
      <ol className={styles.nodes}>
        {ordered.map((node) => (
          <li key={node.id} className={styles.node}>
            <span className={styles.nodeName}>{node.name}</span>
            <span className={styles.nodeDefinition}>{node.definition}</span>
            <span className={styles.nodeRequires}>
              {node.requires.length > 0
                ? `Needs first: ${node.requires.map((id) => byId.get(id)?.name ?? id).join(", ")}`
                : "Start here"}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
