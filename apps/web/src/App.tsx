import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { AppFrame } from "./components/AppFrame";
import { PrereqGraphExplorer } from "./components/graph/PrereqGraphExplorer";
import { CourseReader, type LessonFocusRequest } from "./components/reader/CourseReader";
import { ViewToggle, type CourseView } from "./components/reader/ViewToggle";
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
import { useOpenedRun } from "./hooks/useOpenedRun";
import { useRuns } from "./hooks/useRuns";
import type { Course, CourseRun, CourseStatus } from "./types/course";
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
function CourseBody({
  course,
  onReload,
  onOpenLesson,
}: {
  course: Course;
  onReload: () => void;
  onOpenLesson?: ((kcId: string) => void) | undefined;
}) {
  return course.graph.nodes.length > 0 ? (
    <PrereqGraphExplorer course={course} onOpenLesson={onOpenLesson} />
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
  const opened = useOpenedRun(apiBaseUrl);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // A ready course defaults to the lesson reader (Learn); Map shows the prerequisite graph.
  const [viewMode, setViewMode] = useState<CourseView>("learn");
  // A Map → Learn drill-in: which concept's lesson to focus. The seq lets the reader honour a repeat
  // request for the same concept after the learner has navigated away.
  const [focusRequest, setFocusRequest] = useState<LessonFocusRequest | null>(null);
  const focusSeq = useRef(0);

  // When a build finishes, the new run was recorded server-side — refresh the history so it shows.
  // Depend on the stable `reloadRuns` (not the hook's per-render object) so this fires once per
  // completed build, not every render.
  const finishedCourseId = state.status === "ready" ? state.course.id : null;
  useEffect(() => {
    if (finishedCourseId) reloadRuns();
  }, [finishedCourseId, reloadRuns]);

  const { open: openRun, close: closeRun } = opened;
  const startNewCourse = useCallback(() => {
    setSettingsOpen(false);
    closeRun();
    reset();
  }, [closeRun, reset]);
  const selectRun = useCallback(
    (run: CourseRun) => {
      setSettingsOpen(false);
      openRun(run);
    },
    [openRun],
  );
  // Drill from a Map concept into its lesson: switch to the reader and request that lesson's focus.
  const openLessonForKc = useCallback((kc: string) => {
    focusSeq.current += 1;
    setFocusRequest({ kc, seq: focusSeq.current });
    setViewMode("learn");
  }, []);

  const selectedRunId = opened.state.status !== "closed" ? opened.state.courseId : undefined;

  // A ready course's canvas: the Learn | Map toggle + course metrics in the header, and either the
  // lesson reader (Learn, default) or the prerequisite-graph explorer (Map) in the body.
  const buildReadyCanvas = (course: Course, onReload: () => void) => ({
    title: course.topic,
    meta: (
      <>
        <ViewToggle value={viewMode} onChange={setViewMode} />
        <HeaderMeta course={course} />
      </>
    ),
    body:
      viewMode === "map" ? (
        <CourseBody course={course} onReload={onReload} onOpenLesson={openLessonForKc} />
      ) : (
        <CourseReader course={course} focusRequest={focusRequest} />
      ),
  });

  const sidebar = (
    <Sidebar
      runs={runsState}
      onReloadRuns={reloadRuns}
      onNewCourse={startNewCourse}
      onOpenSettings={() => setSettingsOpen(true)}
      settingsActive={settingsOpen}
      onSelectRun={selectRun}
      selectedRunId={selectedRunId}
    />
  );

  // Resolve the single canvas surface; the shell + sidebar wrap it once. Priority:
  // settings → an opened historical run → the live build (idle / streaming / error / ready).
  const canvas = ((): { title: string; meta: ReactNode; body: ReactNode } => {
    if (settingsOpen) {
      const body = <SettingsPanel apiBaseUrl={apiBaseUrl} onClose={() => setSettingsOpen(false)} />;
      return { title: "Settings", meta: null, body };
    }
    if (opened.state.status === "loading") {
      return { title: opened.state.topic, meta: null, body: <GraphSkeleton /> };
    }
    if (opened.state.status === "error") {
      const { courseId, topic, message } = opened.state;
      const body = (
        <ErrorState message={message} onRetry={() => openRun({ id: courseId, topic })} />
      );
      return { title: topic, meta: null, body };
    }
    if (opened.state.status === "ready") {
      const { course } = opened.state;
      const reopen = () => openRun({ id: course.id, topic: course.topic });
      return buildReadyCanvas(course, reopen);
    }
    if (state.status === "idle") {
      return { title: "New course", meta: null, body: <TopicForm onGenerate={generate} /> };
    }
    if (state.status === "streaming") {
      return {
        title: state.topic,
        meta: (
          <>
            <StatusDot label="building" tone="accent" live />
            <Button onClick={reset}>Cancel</Button>
          </>
        ),
        body: (
          <Transcript topic={state.topic} events={state.events} agentEvents={state.agentEvents} />
        ),
      };
    }
    if (state.status === "error") {
      const { topic, message } = state;
      return {
        title: topic,
        meta: null,
        body: <ErrorState message={message} onRetry={() => generate(topic)} />,
      };
    }
    return buildReadyCanvas(state.course, reset);
  })();

  return (
    <AgentShell sidebar={sidebar} title={canvas.title} meta={canvas.meta}>
      {canvas.body}
    </AgentShell>
  );
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_URL;
  return apiBaseUrl ? <StudioApp apiBaseUrl={apiBaseUrl} /> : <SeedApp />;
}
