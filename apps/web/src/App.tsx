import { useState } from "react";

import { AppFrame } from "./components/AppFrame";
import { BuildProgress } from "./components/build/BuildProgress";
import { PrereqGraphExplorer } from "./components/graph/PrereqGraphExplorer";
import { Button } from "./components/primitives/Button";
import { StatusDot, type StatusTone } from "./components/primitives/StatusDot";
import { EmptyState } from "./components/states/EmptyState";
import { ErrorState } from "./components/states/ErrorState";
import { SettingsPanel } from "./components/settings/SettingsPanel";
import { GraphSkeleton } from "./components/states/GraphSkeleton";
import { TopicForm } from "./components/TopicForm";
import { useCourse } from "./hooks/useCourse";
import { useCourseStream } from "./hooks/useCourseStream";
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

/** A loaded course's graph, or its empty state when no concepts were mapped. */
function CourseBody({ course, onReload }: { course: Course; onReload: () => void }) {
  return course.graph.nodes.length > 0 ? (
    <PrereqGraphExplorer course={course} />
  ) : (
    <EmptyState onReload={onReload} />
  );
}

/** Offline surface (no VITE_API_URL): load and explore the bundled sample course. */
function SeedApp() {
  const { state, reload } = useCourse();
  const course = state.status === "ready" ? state.course : null;

  return (
    <AppFrame
      title={course ? course.topic : "Loading course…"}
      meta={course ? <HeaderMeta course={course} /> : undefined}
    >
      {state.status === "loading" && <GraphSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}
      {state.status === "ready" && <CourseBody course={state.course} onReload={reload} />}
    </AppFrame>
  );
}

/** Live surface: name a topic, watch the pipeline build it, then explore the result. */
function StudioApp({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { state, generate, reset } = useCourseStream(apiBaseUrl);
  const [settingsOpen, setSettingsOpen] = useState(false);

  if (settingsOpen) {
    return (
      <AppFrame title="Settings">
        <SettingsPanel apiBaseUrl={apiBaseUrl} onClose={() => setSettingsOpen(false)} />
      </AppFrame>
    );
  }

  const settingsButton = (
    <Button type="button" onClick={() => setSettingsOpen(true)}>
      Settings
    </Button>
  );

  if (state.status === "idle") {
    return (
      <AppFrame title="New course" meta={settingsButton}>
        <TopicForm onGenerate={generate} />
      </AppFrame>
    );
  }
  if (state.status === "streaming") {
    return (
      <AppFrame
        title={state.topic}
        meta={
          <>
            <StatusDot label="building" tone="accent" live />
            <Button onClick={reset}>Cancel</Button>
          </>
        }
      >
        <BuildProgress topic={state.topic} events={state.events} />
      </AppFrame>
    );
  }
  if (state.status === "error") {
    return (
      <AppFrame title={state.topic} meta={settingsButton}>
        <ErrorState message={state.message} onRetry={() => generate(state.topic)} />
      </AppFrame>
    );
  }
  return (
    <AppFrame
      title={state.course.topic}
      meta={
        <>
          <HeaderMeta course={state.course} />
          <Button variant="primary" onClick={reset}>
            New course
          </Button>
          {settingsButton}
        </>
      }
    >
      <CourseBody course={state.course} onReload={reset} />
    </AppFrame>
  );
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_URL;
  return apiBaseUrl ? <StudioApp apiBaseUrl={apiBaseUrl} /> : <SeedApp />;
}
