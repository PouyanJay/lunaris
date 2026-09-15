import { useLocation, useNavigate } from "react-router";
import { isConceptGraph, type ConceptGraph } from "../../lib/liveGraph";
import { isCorpusGraphReady } from "../../lib/liveCorpusGraph";
import { Button } from "../primitives/Button";
import { CorpusSource } from "./CorpusSource";
import { CorpusPreparationReport } from "./CorpusPreparationReport";
import { useCoursePreparation } from "./useCoursePreparation";
import styles from "./CourseLiveEntry.module.css";

/** Select a published Studio source; a successful preparation opens its reviewable learning plan. */
export function CourseLiveEntry({
  apiBaseUrl,
  initialCourseId,
}: {
  apiBaseUrl: string;
  initialCourseId: string;
}) {
  const navigate = useNavigate();
  const { state } = useLocation();
  const previous =
    state &&
    typeof state === "object" &&
    "previousGraph" in state &&
    isConceptGraph(state.previousGraph)
      ? state.previousGraph
      : null;
  function prepared(graph: ConceptGraph) {
    if (isCorpusGraphReady(graph))
      navigate(`/live?graph=${encodeURIComponent(graph.graphId)}`, {
        state: {
          previousGraph: previous?.corpus?.courseId === graph.corpus?.courseId ? previous : null,
        },
      });
  }
  const preparation = useCoursePreparation(apiBaseUrl, initialCourseId, prepared);
  if (preparation.library.status === "loading")
    return <p role="status">Loading your published courses…</p>;
  if (preparation.library.status === "failed")
    return (
      <section className={styles.root}>
        <p role="alert">Could not load your courses. Retry to choose a source.</p>
        <Button onClick={preparation.reload}>Retry courses</Button>
      </section>
    );
  const graph = preparation.graph;
  return (
    <section className={styles.root} aria-label="Learn from a course">
      <h1>Learn from a course</h1>
      <p>Choose a published course. Review its learning plan before starting a Live session.</p>
      <CorpusSource
        courses={preparation.library.courses}
        courseId={preparation.courseId}
        onSelect={preparation.select}
        onPrepare={(id) => void preparation.prepare(id)}
        busy={preparation.busy}
        error={preparation.error}
      />
      {graph?.corpus && !isCorpusGraphReady(graph) && (
        <CorpusPreparationReport
          graph={{ ...graph, corpus: graph.corpus }}
          previousGraph={previous?.corpus ? { ...previous, corpus: previous.corpus } : null}
        />
      )}
    </section>
  );
}
