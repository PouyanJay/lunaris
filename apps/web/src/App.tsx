import { useEffect, useState } from "react";

import { AppFrame } from "./components/AppFrame";
import { PrereqGraphExplorer } from "./components/graph/PrereqGraphExplorer";
import { Button } from "./components/primitives/Button";
import { StatusDot, type StatusTone } from "./components/primitives/StatusDot";
import { AgentShell } from "./components/shell/AgentShell";
import { Sidebar } from "./components/shell/Sidebar";
import { Transcript } from "./components/transcript/Transcript";
import { EmptyState } from "./components/states/EmptyState";
import { ErrorState } from "./components/states/ErrorState";
import { SettingsPanel } from "./components/settings/SettingsPanel";
import { GraphSkeleton } from "./components/states/GraphSkeleton";
import { TopicForm } from "./components/TopicForm";
import { useCourse } from "./hooks/useCourse";
import { useCourseStream } from "./hooks/useCourseStream";
import { useRuns } from "./hooks/useRuns";
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

/** Live surface: name a topic, watch the pipeline build it, then explore the result. The sidebar
 *  (run history + nav) persists across every state; only the canvas changes. */
function StudioApp({ apiBaseUrl }: { apiBaseUrl: string }) {
  const { state, generate, reset } = useCourseStream(apiBaseUrl);
  const { state: runsState, reload: reloadRuns } = useRuns(apiBaseUrl);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // When a build finishes, the new run was recorded server-side — refresh the history so it shows.
  // Depend on the stable `reloadRuns` (not the hook's per-render object) so this fires once per
  // completed build, not every render.
  const finishedCourseId = state.status === "ready" ? state.course.id : null;
  useEffect(() => {
    if (finishedCourseId) reloadRuns();
  }, [finishedCourseId, reloadRuns]);

  const startNewCourse = () => {
    setSettingsOpen(false);
    reset();
  };

  const sidebar = (
    <Sidebar
      runs={runsState}
      onReloadRuns={reloadRuns}
      onNewCourse={startNewCourse}
      onOpenSettings={() => setSettingsOpen(true)}
      settingsActive={settingsOpen}
    />
  );

  if (settingsOpen) {
    return (
      <AgentShell sidebar={sidebar} title="Settings">
        <SettingsPanel apiBaseUrl={apiBaseUrl} onClose={() => setSettingsOpen(false)} />
      </AgentShell>
    );
  }
  if (state.status === "idle") {
    return (
      <AgentShell sidebar={sidebar} title="New course">
        <TopicForm onGenerate={generate} />
      </AgentShell>
    );
  }
  if (state.status === "streaming") {
    return (
      <AgentShell
        sidebar={sidebar}
        title={state.topic}
        meta={
          <>
            <StatusDot label="building" tone="accent" live />
            <Button onClick={reset}>Cancel</Button>
          </>
        }
      >
        <Transcript topic={state.topic} events={state.events} agentEvents={state.agentEvents} />
      </AgentShell>
    );
  }
  if (state.status === "error") {
    return (
      <AgentShell sidebar={sidebar} title={state.topic}>
        <ErrorState message={state.message} onRetry={() => generate(state.topic)} />
      </AgentShell>
    );
  }
  return (
    <AgentShell
      sidebar={sidebar}
      title={state.course.topic}
      meta={<HeaderMeta course={state.course} />}
    >
      <CourseBody course={state.course} onReload={reset} />
    </AgentShell>
  );
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_URL;
  return apiBaseUrl ? <StudioApp apiBaseUrl={apiBaseUrl} /> : <SeedApp />;
}
