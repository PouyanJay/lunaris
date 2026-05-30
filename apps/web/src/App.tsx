import { AppFrame } from "./components/AppFrame";
import { PrereqGraphExplorer } from "./components/graph/PrereqGraphExplorer";
import { StatusDot, type StatusTone } from "./components/primitives/StatusDot";
import { EmptyState } from "./components/states/EmptyState";
import { ErrorState } from "./components/states/ErrorState";
import { GraphSkeleton } from "./components/states/GraphSkeleton";
import { useCourse } from "./hooks/useCourse";
import type { Course, CourseStatus } from "./types/course";
import styles from "./App.module.css";

const RUNNING: CourseStatus[] = ["diagnosing", "mapping", "sequencing", "authoring", "verifying"];

function statusTone(status: CourseStatus): { tone: StatusTone; live: boolean } {
  if (status === "published") return { tone: "success", live: false };
  if (status === "review") return { tone: "warning", live: false };
  if (RUNNING.includes(status)) return { tone: "accent", live: true };
  return { tone: "neutral", live: false };
}

function HeaderMeta({ course }: { course: Course }) {
  const { graph, status } = course;
  const { tone, live } = statusTone(status);
  return (
    <>
      <dl className={styles.metrics}>
        <Metric label="KCs" value={String(graph.nodes.length)} />
        <Metric label="Edges" value={String(graph.edges.length)} />
        <Metric label="Acyclic" value={graph.isAcyclic ? "yes" : "no"} />
      </dl>
      <StatusDot label={status} tone={tone} live={live} />
    </>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metric}>
      <dt className="eyebrow">{label}</dt>
      <dd className={`${styles.metricValue} mono`}>{value}</dd>
    </div>
  );
}

export default function App() {
  const { state, reload } = useCourse();

  const course = state.status === "ready" ? state.course : null;
  const title = course ? course.topic : "Loading course…";
  const meta = course ? <HeaderMeta course={course} /> : undefined;

  return (
    <AppFrame title={title} meta={meta}>
      {state.status === "loading" && <GraphSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}
      {state.status === "ready" && state.course.graph.nodes.length === 0 && (
        <EmptyState onReload={reload} />
      )}
      {state.status === "ready" && state.course.graph.nodes.length > 0 && (
        <PrereqGraphExplorer course={state.course} />
      )}
    </AppFrame>
  );
}
