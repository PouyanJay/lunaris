import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { AppFrame } from "./components/AppFrame";
import { CorpusPanel } from "./components/corpus/CorpusPanel";
import { PrereqGraphExplorer } from "./components/graph/PrereqGraphExplorer";
import { CourseReader, type LessonFocusRequest } from "./components/reader/CourseReader";
import { ViewToggle, type CourseView } from "./components/reader/ViewToggle";
import { Button } from "./components/primitives/Button";
import { StatusDot, type StatusTone } from "./components/primitives/StatusDot";
import { AgentShell } from "./components/shell/AgentShell";
import { Sidebar } from "./components/shell/Sidebar";
import { BuildTimeline } from "./components/transcript/BuildTimeline";
import { BuildReplay } from "./components/transcript/BuildReplay";
import { ExplainProvider } from "./components/transcript/ExplainContext";
import { BuildingState } from "./components/states/BuildingState";
import { EmptyState } from "./components/states/EmptyState";
import { ErrorState } from "./components/states/ErrorState";
import { SettingsPanel } from "./components/settings/SettingsPanel";
import { GraphSkeleton } from "./components/states/GraphSkeleton";
import { PersonalizePanel } from "./components/personalize/PersonalizePanel";
import { TopicForm } from "./components/TopicForm";
import { useCourse } from "./hooks/useCourse";
import { useCourseStream } from "./hooks/useCourseStream";
import { useTheme, type ThemeProps } from "./hooks/useTheme";
import { useOpenedRun } from "./hooks/useOpenedRun";
import { useRuns } from "./hooks/useRuns";
import { useSidebarLayout } from "./hooks/useSidebarLayout";
import { ConfirmDialog } from "./components/overlays/ConfirmDialog";
import { regenerateLesson } from "./lib/loadCourse";
import { fetchSettings } from "./lib/settings";
import { useCancelRun } from "./hooks/useCancelRun";
import { useDeleteRun } from "./hooks/useDeleteRun";
import { useTerminateBuild } from "./hooks/useTerminateBuild";
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
function SeedApp({ theme, onToggleTheme }: ThemeProps) {
  const { state, reload } = useCourse();
  const course = state.status === "ready" ? state.course : null;

  return (
    <AppFrame
      title={course ? course.topic : "Loading course…"}
      meta={course ? <HeaderMeta course={course} /> : undefined}
      theme={theme}
      onToggleTheme={onToggleTheme}
    >
      {state.status === "loading" && <GraphSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={reload} />}
      {state.status === "ready" && <CourseBody course={state.course} onReload={reload} />}
    </AppFrame>
  );
}

/** Live surface: name a topic, watch the pipeline build it, then explore the result. The sidebar
 *  (run history + nav) persists across every state; only the canvas changes. */
function StudioApp({ apiBaseUrl, theme, onToggleTheme }: { apiBaseUrl: string } & ThemeProps) {
  const { state, generate, reset } = useCourseStream(apiBaseUrl);
  const { state: runsState, reload: reloadRuns } = useRuns(apiBaseUrl);
  const opened = useOpenedRun(apiBaseUrl);
  const sidebarLayout = useSidebarLayout();
  const [settingsOpen, setSettingsOpen] = useState(false);
  // The topic the learner opted to personalize (P7.5): non-null shows the confirm panel in place of
  // the topic form. Cleared on confirm/cancel and when starting a fresh course.
  const [personalizeTopic, setPersonalizeTopic] = useState<string | null>(null);
  // The per-lesson regenerate action only works on a pipeline that implements it (the single-shot
  // Orchestrator); the deep-agent builder 501s. Read the capability once and hide the action when
  // it's unsupported, rather than offering a button that always fails. Fail closed on any error.
  const [canRegenerate, setCanRegenerate] = useState(false);
  // Whether the transcript may offer "Explain" on a JSON blob — available only when an Anthropic key
  // is reachable. Read alongside the regenerate capability; fail closed so a button never 503s.
  const [canExplain, setCanExplain] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchSettings(apiBaseUrl, controller.signal)
      .then((settings) => {
        if (controller.signal.aborted) return;
        setCanRegenerate(settings.supportsLessonRegeneration);
        setCanExplain(settings.supportsExplain);
      })
      .catch(() => {
        // Fail closed: a settings fetch we can't complete hides the actions. Guard the unmount race
        // like the success path so an aborted fetch never sets state on a gone component.
        if (controller.signal.aborted) return;
        setCanRegenerate(false);
        setCanExplain(false);
      });
    return () => controller.abort();
  }, [apiBaseUrl]);
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

  // The run is recorded RUNNING server-side before its first event is emitted, so the run_id on that
  // first event is a race-free cue that the row exists — refetch so the sidebar shows the new run
  // without a browser refresh (useRuns then polls while it's running). Keyed on the run_id so it
  // fires once per build, not per streamed event.
  const streamingRunId = state.status === "streaming" ? state.runId : undefined;
  useEffect(() => {
    if (streamingRunId) reloadRuns();
  }, [streamingRunId, reloadRuns]);

  const { open: openRun, close: closeRun } = opened;
  const startNewCourse = useCallback(() => {
    setSettingsOpen(false);
    setPersonalizeTopic(null);
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

  // Delete a run: a confirm-before dialog (irreversible) → DELETE the course → drop any open view
  // of it + refresh the history. The workflow lives in its own hook to keep StudioApp lean.
  const deleteRun = useDeleteRun(apiBaseUrl, opened.state, closeRun, reloadRuns);
  // Cancel an in-flight run (no confirm — it's recoverable): POST cancel → refresh (flips CANCELLED).
  const cancellation = useCancelRun(apiBaseUrl, reloadRuns);
  // Terminate the live (streaming) build: a confirm step → cancel server-side → reset the stream.
  const termination = useTerminateBuild(apiBaseUrl, reset, reloadRuns);

  // A ready course's canvas: the Learn | Map | Build toggle + course metrics in the header, and the
  // lesson reader (Learn, default), the prerequisite-graph explorer (Map), or the build-session
  // replay (Build) in the body. `runId` (when known) lets Build replay this course's build log.
  const buildReadyCanvas = (course: Course, onReload: () => void, runId: string | undefined) => ({
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
      ) : viewMode === "build" ? (
        <ExplainProvider apiBaseUrl={apiBaseUrl} available={canExplain}>
          <BuildReplay apiBaseUrl={apiBaseUrl} runId={runId} topic={course.topic} />
        </ExplainProvider>
      ) : viewMode === "corpus" ? (
        <CorpusPanel apiBaseUrl={apiBaseUrl} courseId={course.id} onReground={onReload} />
      ) : (
        <CourseReader
          course={course}
          focusRequest={focusRequest}
          onRegenerate={
            canRegenerate
              ? (lessonId) => regenerateLesson(apiBaseUrl, course.id, lessonId)
              : undefined
          }
        />
      ),
  });

  const sidebar = (
    <Sidebar
      runs={runsState}
      onReloadRuns={reloadRuns}
      onNewCourse={startNewCourse}
      onOpenSettings={() => setSettingsOpen(true)}
      settingsActive={settingsOpen}
      collapsed={sidebarLayout.collapsed}
      onToggleCollapse={sidebarLayout.toggleCollapsed}
      onSelectRun={selectRun}
      onDeleteRun={deleteRun.request}
      onCancelRun={(run) => cancellation.cancel(run.runId)}
      cancellingRunId={cancellation.cancellingRunId}
      selectedRunId={selectedRunId}
      theme={theme}
      onToggleTheme={onToggleTheme}
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
    if (opened.state.status === "building") {
      const { topic, runId } = opened.state;
      return {
        title: topic,
        meta: <StatusDot label="building" tone="accent" live />,
        body: (
          <BuildingState
            onRecheck={opened.recheck}
            onCancel={() => cancellation.cancel(runId)}
            cancelling={cancellation.cancellingRunId === runId}
          />
        ),
      };
    }
    if (opened.state.status === "error") {
      const { courseId, topic, message } = opened.state;
      const onRetry = () => openRun({ id: courseId, topic, status: "completed" });
      const body = <ErrorState message={message} onRetry={onRetry} />;
      return { title: topic, meta: null, body };
    }
    if (opened.state.status === "ready") {
      const { course, runId } = opened.state;
      const reopen = () => openRun({ id: course.id, topic: course.topic, status: "completed" });
      return buildReadyCanvas(course, reopen, runId);
    }
    if (state.status === "idle") {
      if (personalizeTopic !== null) {
        return {
          title: "New course",
          meta: null,
          body: (
            <PersonalizePanel
              apiBaseUrl={apiBaseUrl}
              topic={personalizeTopic}
              onConfirm={(topic, clarification) => {
                setPersonalizeTopic(null);
                generate(topic, clarification);
              }}
              onCancel={() => setPersonalizeTopic(null)}
            />
          ),
        };
      }
      return {
        title: "New course",
        meta: null,
        body: <TopicForm onGenerate={generate} onPersonalize={setPersonalizeTopic} />,
      };
    }
    if (state.status === "streaming") {
      const { runId } = state;
      return {
        title: state.topic,
        meta: (
          <>
            <StatusDot label="building" tone="accent" live />
            <Button onClick={() => termination.request(runId)}>Terminate</Button>
          </>
        ),
        body: (
          <ExplainProvider apiBaseUrl={apiBaseUrl} available={canExplain}>
            <BuildTimeline
              topic={state.topic}
              events={state.events}
              agentEvents={state.agentEvents}
              stageTimes={state.stageTimes}
            />
          </ExplainProvider>
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
    return buildReadyCanvas(state.course, reset, state.runId);
  })();

  return (
    <>
      <AgentShell sidebar={sidebar} title={canvas.title} meta={canvas.meta} layout={sidebarLayout}>
        {canvas.body}
      </AgentShell>
      <ConfirmDialog
        open={deleteRun.pendingDelete !== null}
        title="Delete this course?"
        description={
          deleteRun.pendingDelete
            ? `“${deleteRun.pendingDelete.topic}” and its build history will be permanently removed. This can’t be undone.`
            : ""
        }
        confirmLabel="Delete course"
        pendingLabel="Deleting…"
        danger
        pending={deleteRun.isDeleting}
        errorMessage={deleteRun.deleteError}
        onConfirm={deleteRun.confirm}
        onCancel={deleteRun.cancel}
      />
      <ConfirmDialog
        open={termination.isConfirming}
        title="Terminate course generation?"
        description="This stops the build that's in progress and records the run as cancelled. You can start a new course anytime."
        confirmLabel="Terminate"
        pendingLabel="Terminating…"
        danger
        pending={termination.isTerminating}
        errorMessage={termination.terminateError}
        onConfirm={termination.confirm}
        onCancel={termination.dismiss}
      />
    </>
  );
}

export default function App() {
  const apiBaseUrl = import.meta.env.VITE_API_URL;
  // App-wide light/dark theme (default light), so both surfaces switch from the one toggle.
  const { theme, toggle } = useTheme();
  return apiBaseUrl ? (
    <StudioApp apiBaseUrl={apiBaseUrl} theme={theme} onToggleTheme={toggle} />
  ) : (
    <SeedApp theme={theme} onToggleTheme={toggle} />
  );
}
