import { useState } from "react";
import { createRoot } from "react-dom/client";
import { CorpusSource } from "../src/components/live/CorpusSource";
import { Button } from "../src/components/primitives/Button";
import { authedFetch } from "../src/lib/apiClient";
import "../src/index.css";

const api = new URLSearchParams(location.search).get("api")!;
const courses = [{ courseId: "corpus-fixture", title: "Fixture course" }];
interface SourceGraph {
  graphId: string;
  corpus: { courseId: string; title: string; status: "pending" };
}
async function request(path: string, init?: RequestInit): Promise<SourceGraph> {
  const response = await authedFetch(`${api}${path}`, init);
  if (!response.ok) throw new Error("Could not prepare this course. Try again.");
  const body: unknown = await response.json();
  if (
    !body ||
    typeof body !== "object" ||
    !("graphId" in body) ||
    typeof body.graphId !== "string" ||
    !("corpus" in body) ||
    !body.corpus ||
    typeof body.corpus !== "object" ||
    !("title" in body.corpus) ||
    typeof body.corpus.title !== "string" ||
    !("courseId" in body.corpus) ||
    typeof body.corpus.courseId !== "string" ||
    !("status" in body.corpus) ||
    body.corpus.status !== "pending"
  )
    throw new Error("Unexpected course source response. Try again.");
  return body as SourceGraph;
}
/** Browser-only authenticated course preparation roundtrip. */
export function CorpusRoundtrip() {
  const [courseId, setCourseId] = useState("");
  const [graph, setGraph] = useState<SourceGraph | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function perform(action: () => Promise<SourceGraph>) {
    setBusy(true);
    setError(null);
    try {
      setGraph(await action());
    } catch {
      setError("Could not prepare this course. Try again.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main data-graph-id={graph?.graphId}>
      <h1>Course source integration</h1>
      <CorpusSource
        courses={courses}
        courseId={courseId}
        onSelect={(value) => {
          setCourseId(value);
          setGraph(null);
        }}
        onPrepare={(value) =>
          void perform(() =>
            request("/api/live/graphs", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ topic: "Fixture course", corpus: { courseId: value } }),
            }),
          )
        }
        busy={busy}
        error={error}
        source={graph?.corpus}
      />
      {graph && (
        <Button
          disabled={busy}
          onClick={() =>
            void perform(() => request(`/api/live/graphs/${encodeURIComponent(graph.graphId)}`))
          }
        >
          Reload source
        </Button>
      )}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<CorpusRoundtrip />);
