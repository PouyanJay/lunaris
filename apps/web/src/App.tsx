import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrowserRouter, useLocation, useNavigate } from "react-router";

import { AppFrame } from "./components/AppFrame";
import { AuthGate } from "./components/auth/AuthGate";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { CorpusPanel } from "./components/corpus/CorpusPanel";
import { CourseLibrary } from "./components/library/CourseLibrary";
import { HomeDashboard } from "./components/home/HomeDashboard";
import { CourseOverview } from "./components/overview/CourseOverview";
import { PrereqGraphExplorer } from "./components/graph/PrereqGraphExplorer";
import { CourseReader, type LessonFocusRequest } from "./components/reader/CourseReader";
import { ViewToggle, type CourseView } from "./components/reader/ViewToggle";
import { Button } from "./components/primitives/Button";
import { StatusDot, type StatusTone } from "./components/primitives/StatusDot";
import { AgentShell } from "./components/shell/AgentShell";
import { Sidebar } from "./components/shell/Sidebar";
import { BuildControlRoom } from "./components/controlroom/BuildControlRoom";
import { BuildReplay } from "./components/transcript/BuildReplay";
import { LiveBuildReplay } from "./components/transcript/LiveBuildReplay";
import { VideosGeneratingPanel } from "./components/transcript/VideosGeneratingPanel";
import { ExplainProvider } from "./components/explain/ExplainContext";
import { BuildingState } from "./components/states/BuildingState";
import { EmptyState } from "./components/states/EmptyState";
import { ErrorState } from "./components/states/ErrorState";
import { PreparingDeviceState } from "./components/states/PreparingDeviceState";
import { AdminPortalPanel } from "./components/admin/AdminPortalPanel";
import { SettingsPanel } from "./components/settings/SettingsPanel";
import { CanvasNotice } from "./components/states/CanvasNotice";
import { GraphSkeleton } from "./components/states/GraphSkeleton";
import { IdleCourseSetup } from "./components/configurator/IdleCourseSetup";
import { useCourse } from "./hooks/useCourse";
import { useCourseProgress } from "./hooks/useCourseProgress";
import { useBeforeUnloadGuard } from "./hooks/useBeforeUnloadGuard";
import { useCourseStream } from "./hooks/useCourseStream";
import { useTheme, type ThemeProps } from "./hooks/useTheme";
import { useOpenedRun } from "./hooks/useOpenedRun";
import { useBuildVideoProgress } from "./hooks/useBuildVideoProgress";
import { useRuns } from "./hooks/useRuns";
import { useCapabilities } from "./hooks/useCapabilities";
import { useMe } from "./hooks/useMe";
import { useKeylessReadiness } from "./hooks/useKeylessReadiness";
import { KeylessProvisioningBanner } from "./components/KeylessProvisioningBanner";
import { useSidebarLayout } from "./hooks/useSidebarLayout";
import { DraftModeBanner } from "./components/DraftModeBanner";
import { MOBILE_QUERY, useMediaQuery } from "./hooks/useMediaQuery";
import { ConfirmDialog } from "./components/overlays/ConfirmDialog";
import { regenerateLesson } from "./lib/loadCourse";
import { putCourseOpened } from "./lib/progress";
import { isLlmKeyless } from "./lib/capabilities";
import { coursePath, lessonPath, resolveRoute, ROUTES, type ShellRoute } from "./lib/routes";
import { fetchSettings } from "./lib/settings";
import { useCourseRouting } from "./hooks/useCourseRouting";
import { useCancelRun } from "./hooks/useCancelRun";
import { useDeleteRun } from "./hooks/useDeleteRun";
import { useTerminateBuild } from "./hooks/useTerminateBuild";
import type { Course, CourseRun, CourseStatus } from "./types/course";
import styles from "./App.module.css";

const RUNNING: CourseStatus[] = ["diagnosing", "mapping", "sequencing", "authoring", "verifying"];

/** The designed full-canvas notices for navigation destinations that carry no data yet: the 404
 *  and the coming-soon placeholders later phases fill (activity P9, bookmarks P10). */
function placeholderCanvas(
  route: ShellRoute,
  onGoHome: () => void,
): { title: string; meta: ReactNode; body: ReactNode } | null {
  if (route.kind === "not-found") {
    return {
      title: "Not found",
      meta: null,
      body: (
        <CanvasNotice
          eyebrow="404"
          title="Page not found"
          body="This page doesn't exist. It may have moved, or the link is wrong."
          actionLabel="Go home"
          onAction={onGoHome}
        />
      ),
    };
  }
  if (route.kind === "activity") {
    return {
      title: "Activity",
      meta: null,
      body: (
        <CanvasNotice
          eyebrow="Coming soon"
          title="Your learning activity lands here"
          body="Streaks, study minutes, and concepts mastered — day by day. Keep learning; the history starts counting soon."
          actionLabel="Go home"
          onAction={onGoHome}
        />
      ),
    };
  }
  if (route.kind === "bookmarks") {
    return {
      title: "Bookmarks",
      meta: null,
      body: (
        <CanvasNotice
          eyebrow="Coming soon"
          title="Saved lessons, concepts, and sources land here"
          body="Bookmark anything worth returning to — lessons mid-read, tricky concepts, and the sources behind the claims."
          actionLabel="Go home"
          onAction={onGoHome}
        />
      ),
    };
  }
  return null;
}

/** Whether a just-built course enqueued any explainer videos — true if it carries course-level
 *  videos or any lesson video pointer. Gates the build canvas's async-videos phase: a video-off
 *  build has none, so the canvas advances straight to the course (no spurious "generating" phase). */
function courseHasVideos(course: Course): boolean {
  if (course.videos?.summary || course.videos?.overview) return true;
  return course.modules.some((module) => module.lessons.some((lesson) => lesson.video));
}

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
  apiBaseUrl,
  onReload,
  onOpenLesson,
}: {
  course: Course;
  /** Origin for the learner's progress snapshot (P7 mastery badges); absent = offline, the map
   *  claims only what the build-time frontier knows. */
  apiBaseUrl?: string | undefined;
  onReload: () => void;
  onOpenLesson?: ((kcId: string) => void) | undefined;
}) {
  const { progress } = useCourseProgress(apiBaseUrl ?? "", course.id);
  return course.graph.nodes.length > 0 ? (
    <PrereqGraphExplorer
      course={course}
      kcMastery={progress?.kcMastery ?? null}
      onOpenLesson={onOpenLesson}
    />
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
  const { state: runsState, reload: reloadRuns } = useRuns(apiBaseUrl);
  const opened = useOpenedRun(apiBaseUrl);
  const sidebarLayout = useSidebarLayout();
  // Phone layout: the rail becomes an off-canvas drawer (the desktop collapse/resize chrome is hidden
  // by CSS). Track the breakpoint so the drawer always shows the full rail, never the mini icon-rail.
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const openMobileNav = useCallback(() => setMobileNavOpen(true), []);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);
  // Closing the drawer is a no-op on desktop, but if the viewport grows past the breakpoint while the
  // drawer is open, drop the open state so it can't linger as a stuck overlay.
  useEffect(() => {
    if (!isMobile) setMobileNavOpen(false);
  }, [isMobile]);
  // Navigation is the URL: the route (not React state) decides which canvas shows. Settings and
  // Admin are full-canvas nav views at /settings and /admin.
  const location = useLocation();
  const navigate = useNavigate();
  const route = resolveRoute(location.pathname);
  const settingsOpen = route.kind === "settings";
  // Leave a nav view toward wherever the user came from; a cold deep-link falls back to home.
  const closeNavView = useCallback(() => {
    if (location.key !== "default") navigate(-1);
    else navigate("/");
  }, [location.key, navigate]);
  const { isAdmin } = useMe(apiBaseUrl);
  // The signed-in email seeds the Home greeting's display name (offline/unauthed → null).
  const { user } = useAuth();
  // Per-capability live/fallback status drives the Draft-mode banner; refetch when Settings closes so
  // a key the user just added flips its capability back to live and the banner clears.
  const { capabilities, reload: reloadCapabilities } = useCapabilities(apiBaseUrl);
  useEffect(() => {
    if (!settingsOpen) reloadCapabilities();
  }, [settingsOpen, reloadCapabilities]);
  // The build stream needs the keyless signal: only a keyless user's device choice routes the
  // build's completions through this tab (a keyed user's builds are always hosted).
  const { state, generate, reset } = useCourseStream(apiBaseUrl, {
    llmKeyless: isLlmKeyless(capabilities),
  });
  // While THIS tab serves a device build (or its model is preparing), closing it kills the build —
  // intercept the reflex tab-close with the browser's native confirm.
  useBeforeUnloadGuard(
    state.status === "preparing-device" ||
      (state.status === "streaming" && state.servedByThisDevice),
  );
  // After a fresh build completes, its lesson + course videos keep rendering async on the cloud
  // worker (minutes, after the build SSE has already ended). Hold the build canvas on a "Videos N/M"
  // phase — polling the course's video jobs — instead of flipping straight to the course with empty
  // video slots (the "froze on Verify" complaint). The user can Open course early; the canvas
  // advances on its own once every video settles. Only when the build actually made videos.
  const liveReadyCourse = state.status === "ready" ? state.course : null;
  const buildHasVideos = liveReadyCourse !== null && courseHasVideos(liveReadyCourse);
  const [videosOpenedEarly, setVideosOpenedEarly] = useState(false);
  // Reset the open-early choice per built course, so the next build's videos phase shows again.
  // Adjusted during render (not in an effect) so the new course never flashes a frame with the
  // previous course's choice — the React "store info from prior renders" pattern.
  const [videosCourseId, setVideosCourseId] = useState<string | undefined>(undefined);
  if (liveReadyCourse?.id !== videosCourseId) {
    setVideosCourseId(liveReadyCourse?.id);
    setVideosOpenedEarly(false);
  }
  const videoProgress = useBuildVideoProgress(
    apiBaseUrl,
    liveReadyCourse?.id,
    buildHasVideos && !videosOpenedEarly,
  );
  const showVideosFinishing =
    buildHasVideos && !videosOpenedEarly && !(videoProgress?.settled ?? false);
  // The per-lesson regenerate action only works on a pipeline that implements it (the single-shot
  // Orchestrator); the deep-agent builder 501s. Read the capability once and hide the action when
  // it's unsupported, rather than offering a button that always fails. Fail closed on any error.
  const [canRegenerate, setCanRegenerate] = useState(false);
  // Explain availability is tiered: the transcript's dev-facing affordance stays hosted-only
  // (Anthropic key reachable), while the reader's learner-facing one answers on either tier
  // (hosted or the keyless server fallback). Fail closed so a button never 503s.
  const [canExplain, setCanExplain] = useState(false);
  const [canReaderExplain, setCanReaderExplain] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetchSettings(apiBaseUrl, controller.signal)
      .then((settings) => {
        if (controller.signal.aborted) return;
        setCanRegenerate(settings.supportsLessonRegeneration);
        setCanExplain(settings.supportsHostedExplain);
        setCanReaderExplain(settings.supportsExplain);
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
  // A ready course lands on its Overview tab; the view is a URL segment.
  const viewMode: CourseView = route.kind === "course" ? route.view : "overview";
  // A Map → lesson drill-in: which concept's lesson to focus. The seq lets the reader honour a repeat
  // request for the same concept after the learner has navigated away.
  const [focusRequest, setFocusRequest] = useState<LessonFocusRequest | null>(null);
  const focusSeq = useRef(0);

  // Whether THIS tab's build stream is the canvas for the routed course — streaming (once the
  // X-Course-Id header lands) or just-finished. When it is, the opened-run flow stays out of the
  // way: the SSE timeline is richer than the polled log it would otherwise fetch.
  const streamCourseId =
    state.status === "streaming"
      ? state.courseId
      : state.status === "ready"
        ? state.course.id
        : undefined;

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
  // While a keyless build is active, the self-hosted model server may be scaling from zero — poll
  // its readiness so the build view can show a "Provisioning…" notice instead of a silent stall.
  // Only when the LLM is on its keyless fallback (a keyed build never touches it → the endpoint
  // returns not_applicable and the banner stays hidden anyway, but gating here avoids needless polls).
  const llmIsFallback = capabilities.some((c) => c.capability === "llm" && c.mode === "fallback");
  const buildActive = state.status === "streaming" || opened.state.status === "building";
  const keylessReadiness = useKeylessReadiness(apiBaseUrl, buildActive && llmIsFallback);

  const { open: openRun } = opened;

  // URL ⇄ course-state wiring (opened-run sync + one-shot live handoff) lives in its own hook.
  const { routedCourseId, liveMatchesRoute, handedOff, clearHandoff } = useCourseRouting({
    route,
    streamCourseId,
    runs: runsState.status === "ready" ? runsState.runs : null,
    opened,
  });

  // Resetting the stream also forgets its handoff, so the next build hands off anew.
  const resetBuild = useCallback(() => {
    clearHandoff();
    reset();
  }, [clearHandoff, reset]);

  // Visiting a course's non-reader views refreshes its open-recency — the library's last-opened
  // sort. A bare touch; the reader view is excluded because CourseReader records the open itself
  // with better fidelity (it knows the lesson), so one open never fires two touches.
  // Fire-and-forget; a failed touch must never disturb the canvas.
  const visitedCourseId =
    route.kind === "course" && route.view !== "lessons" ? route.courseId : null;
  useEffect(() => {
    if (visitedCourseId) {
      putCourseOpened(apiBaseUrl, visitedCourseId).catch(() => {});
    }
  }, [apiBaseUrl, visitedCourseId]);

  // A nav action on a phone also dismisses the drawer so the chosen view isn't hidden behind it.
  // The composer lives at /new; Home (/) is the dashboard.
  const startNewCourse = useCallback(() => {
    setMobileNavOpen(false);
    resetBuild();
    navigate(ROUTES.composer);
  }, [resetBuild, navigate]);
  const selectRun = useCallback(
    (run: CourseRun) => {
      setMobileNavOpen(false);
      navigate(coursePath(run.id));
    },
    [navigate],
  );
  const openSettings = useCallback(() => {
    setMobileNavOpen(false);
    navigate("/settings");
  }, [navigate]);
  // Home → reader: resume a course at a specific lesson. The lesson is a URL segment (P6) — the
  // reader opens straight at it, refresh- and share-safe. Without a known lesson the bare reader
  // URL canonicalises to the focused lesson once the course loads.
  const openCourseLesson = useCallback(
    (courseId: string, lessonId?: string) => {
      setMobileNavOpen(false);
      navigate(lessonId ? lessonPath(courseId, lessonId) : coursePath(courseId, "lessons"));
    },
    [navigate],
  );
  const openCourseOverview = useCallback(
    (courseId: string) => {
      setMobileNavOpen(false);
      navigate(coursePath(courseId));
    },
    [navigate],
  );
  const selectedRunId = routedCourseId ?? undefined;

  // Delete a run: a confirm-before dialog (irreversible) → DELETE the course → drop any open view
  // of it + refresh the history. The workflow lives in its own hook to keep StudioApp lean.
  // Deleting the course you're looking at also leaves its now-dead URL.
  const closeDeletedRun = useCallback(() => {
    opened.close();
    navigate("/");
  }, [opened, navigate]);
  const deleteRun = useDeleteRun(apiBaseUrl, opened.state, closeDeletedRun, reloadRuns);
  // Cancel an in-flight run (no confirm — it's recoverable): POST cancel → refresh (flips CANCELLED).
  const cancellation = useCancelRun(apiBaseUrl, reloadRuns);
  // Terminate the live (streaming) build: a confirm step → cancel server-side → reset the stream.
  const termination = useTerminateBuild(apiBaseUrl, resetBuild, reloadRuns);

  // A ready course's canvas: the Overview | Lessons | Map | Build | Corpus toggle + course
  // metrics in the header; the Overview landing tab, the lesson reader, the prerequisite-graph
  // explorer, the build-session replay, or the corpus in the body. `runId` (when known) lets
  // Build replay this course's build log. The view lives in the URL; a Map → lesson drill-in
  // navigates to the reader with a focus request.
  const buildReadyCanvas = (course: Course, onReload: () => void, runId: string | undefined) => {
    // Every way into the reader: a known lesson is a URL (P6); a concept from the Map rides a
    // focus request — the reader resolves which lesson covers it, then canonicalises the URL.
    const openLessonForKc = (kc: string) => {
      focusSeq.current += 1;
      setFocusRequest({ kc, seq: focusSeq.current });
      navigate(coursePath(course.id, "lessons"));
    };
    const openLessonById = (lessonId?: string) =>
      navigate(lessonId ? lessonPath(course.id, lessonId) : coursePath(course.id, "lessons"));
    // Record over the CourseView union: adding a sixth view without a body is a type error,
    // never a silent fall-through to Overview.
    const bodies: Record<CourseView, () => ReactNode> = {
      overview: () => (
        <CourseOverview
          course={course}
          apiBaseUrl={apiBaseUrl}
          onContinue={openLessonById}
          onViewMap={() => navigate(coursePath(course.id, "map"))}
          onOpenLesson={openLessonById}
        />
      ),
      lessons: () => (
        <ExplainProvider
          apiBaseUrl={apiBaseUrl}
          available={canReaderExplain}
          llmKeyless={isLlmKeyless(capabilities)}
        >
          <CourseReader
            course={course}
            activeLessonId={route.kind === "course" ? route.lessonId : undefined}
            onNavigateLesson={(lessonId, options) =>
              navigate(lessonPath(course.id, lessonId), options)
            }
            focusRequest={focusRequest}
            onRegenerate={
              canRegenerate
                ? (lessonId) => regenerateLesson(apiBaseUrl, course.id, lessonId)
                : undefined
            }
            apiBaseUrl={apiBaseUrl}
            onExitToOverview={() => navigate(coursePath(course.id))}
          />
        </ExplainProvider>
      ),
      map: () => (
        <CourseBody
          course={course}
          apiBaseUrl={apiBaseUrl}
          onReload={onReload}
          onOpenLesson={openLessonForKc}
        />
      ),
      build: () => (
        <ExplainProvider apiBaseUrl={apiBaseUrl} available={canExplain}>
          <BuildReplay apiBaseUrl={apiBaseUrl} runId={runId} topic={course.topic} />
        </ExplainProvider>
      ),
      corpus: () => (
        <CorpusPanel apiBaseUrl={apiBaseUrl} courseId={course.id} onReground={onReload} />
      ),
    };
    return {
      title: course.topic,
      meta: (
        <>
          <ViewToggle value={viewMode} onChange={(view) => navigate(coursePath(course.id, view))} />
          <HeaderMeta course={course} />
        </>
      ),
      body: bodies[viewMode](),
    };
  };

  const sidebar = (
    <Sidebar
      runs={runsState}
      onReloadRuns={reloadRuns}
      onNewCourse={startNewCourse}
      showAdmin={isAdmin}
      onNavigate={closeMobileNav}
      collapsed={isMobile ? false : sidebarLayout.collapsed}
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

  // Resolve the single canvas surface; the shell + sidebar wrap it once. The URL decides the
  // navigation surface (not-found / settings / admin); the home route then resolves an opened
  // historical run or the live build (idle / streaming / error / ready).
  const canvas = ((): { title: string; meta: ReactNode; body: ReactNode } => {
    const placeholder = placeholderCanvas(route, () => navigate("/"));
    if (placeholder) return placeholder;
    if (route.kind === "library") {
      return {
        title: "My courses",
        meta: (
          <Button variant="accent" onClick={startNewCourse}>
            New course
          </Button>
        ),
        body: (
          <CourseLibrary
            apiBaseUrl={apiBaseUrl}
            onNewCourse={startNewCourse}
            runs={runsState.status === "ready" ? runsState.runs : []}
          />
        ),
      };
    }
    if (route.kind === "settings") {
      const body = <SettingsPanel apiBaseUrl={apiBaseUrl} />;
      const meta = (
        <Button type="button" onClick={closeNavView}>
          Done
        </Button>
      );
      return { title: "Settings", meta, body };
    }
    if (route.kind === "admin") {
      // Fail closed: until /api/me confirms the admin claim, the portal stays behind the notice
      // (the API enforces admin on every call regardless — this is presentation, not security).
      if (!isAdmin) {
        return {
          title: "Admin Portal",
          meta: null,
          body: (
            <CanvasNotice
              eyebrow="Restricted"
              title="Admin access required"
              body="This page is only available to workspace administrators."
              actionLabel="Go home"
              onAction={() => navigate("/")}
            />
          ),
        };
      }
      const body = <AdminPortalPanel apiBaseUrl={apiBaseUrl} />;
      const meta = (
        <Button type="button" onClick={closeNavView}>
          Done
        </Button>
      );
      return { title: "Admin Portal", meta, body };
    }
    // This tab's live build canvases — rendered on the home route until the stream learns its
    // course id (the handoff effect then moves the URL), and on the routed course thereafter.
    const buildStreamingCanvas = (stream: Extract<typeof state, { status: "streaming" }>) => {
      const { runId, reconnecting } = stream;
      return {
        title: stream.topic,
        meta: (
          <>
            {/* Reconnecting = the live feed dropped but the build is still running server-side; the
                timeline keeps advancing from the durable log, so the label stays "in progress". */}
            <StatusDot label={reconnecting ? "reconnecting" : "building"} tone="accent" live />
            <Button onClick={() => termination.request(runId)}>Terminate</Button>
          </>
        ),
        body: (
          <>
            {/* The tab-open contract for a device build now rides the Draft banner's compact
                compute select (its hint while "This device" is chosen) — no separate band. */}
            {!stream.servedByThisDevice && <KeylessProvisioningBanner status={keylessReadiness} />}
            <ExplainProvider apiBaseUrl={apiBaseUrl} available={canExplain}>
              <BuildControlRoom
                topic={stream.topic}
                events={stream.events}
                agentEvents={stream.agentEvents}
                stageTimes={stream.stageTimes}
              />
            </ExplainProvider>
          </>
        ),
      };
    };
    // A fresh build finished, but its videos are still rendering async: hold the build canvas on the
    // videos phase (the completed timeline + a polled "N of M" panel) rather than flipping to the
    // course with empty slots. "Open course" leaves early; the canvas advances once videos settle.
    const buildVideosFinishingCanvas = () => {
      // showVideosFinishing implies a ready stream; the status check re-proves it to the compiler.
      if (!showVideosFinishing || state.status !== "ready") return null;
      return {
        title: state.course.topic,
        meta: <StatusDot label="finishing videos" tone="accent" live />,
        body: (
          <>
            {state.runId && (
              <ExplainProvider apiBaseUrl={apiBaseUrl} available={canExplain}>
                <BuildReplay
                  apiBaseUrl={apiBaseUrl}
                  runId={state.runId}
                  topic={state.course.topic}
                />
              </ExplainProvider>
            )}
            <VideosGeneratingPanel
              progress={videoProgress}
              onOpenCourse={() => setVideosOpenedEarly(true)}
            />
          </>
        ),
      };
    };

    if (route.kind === "course") {
      // This tab's own stream owns the canvas while it's building/finishing the routed course.
      if (liveMatchesRoute) {
        if (state.status === "streaming") return buildStreamingCanvas(state);
        const videos = buildVideosFinishingCanvas();
        if (videos) return videos;
        if (state.status === "ready")
          return buildReadyCanvas(state.course, resetBuild, state.runId);
      }
      if (opened.state.status === "loading") {
        return { title: opened.state.topic, meta: null, body: <GraphSkeleton /> };
      }
      if (opened.state.status === "building") {
        const { topic, runId } = opened.state;
        const cancelling = cancellation.cancellingRunId === runId;
        return {
          title: topic,
          meta: (
            <>
              <StatusDot label="building" tone="accent" live />
              {runId && (
                <Button
                  variant="secondary"
                  onClick={() => cancellation.cancel(runId)}
                  disabled={cancelling}
                  aria-busy={cancelling}
                >
                  {cancelling ? "Cancelling…" : "Cancel build"}
                </Button>
              )}
            </>
          ),
          // A running run is reattachable: poll its live event log into the build timeline rather
          // than a static placeholder (the canvas auto-advances to the course when the run finishes
          // — see useOpenedRun's recheck poll). Fall back to the placeholder only when the run
          // carries no run_id (defensive — a running run always has one).
          body: (
            <>
              <KeylessProvisioningBanner status={keylessReadiness} />
              {runId ? (
                <ExplainProvider apiBaseUrl={apiBaseUrl} available={canExplain}>
                  <LiveBuildReplay apiBaseUrl={apiBaseUrl} runId={runId} topic={topic} />
                </ExplainProvider>
              ) : (
                <BuildingState
                  onRecheck={opened.recheck}
                  onCancel={() => cancellation.cancel(runId)}
                  cancelling={cancelling}
                />
              )}
            </>
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
      // Closed: the URL names a course the sync effect hasn't resolved yet (run history loading).
      return { title: "Loading course…", meta: null, body: <GraphSkeleton /> };
    }

    // Home (/): the learner's dashboard. The composer moved to /new — a live build streams there
    // until it hands its URL off to the built course.
    if (route.kind === "home") {
      return {
        title: "Home",
        meta: null,
        body: (
          <HomeDashboard
            apiBaseUrl={apiBaseUrl}
            userEmail={user?.email ?? null}
            runs={runsState.status === "ready" ? runsState.runs : []}
            onNewCourse={startNewCourse}
            onResumeLesson={openCourseLesson}
            onViewCourse={openCourseOverview}
          />
        ),
      };
    }

    // The composer (/new): the idle setup, or this tab's build before its course id is known. Once
    // the build handed its URL off, the composer is idle again — the course lives at its own URL.
    if (state.status === "idle" || handedOff) {
      return {
        title: "New course",
        meta: null,
        body: (
          <IdleCourseSetup
            apiBaseUrl={apiBaseUrl}
            onGenerate={generate}
            onOpenSettings={openSettings}
            runs={runsState.status === "ready" ? runsState.runs : []}
          />
        ),
      };
    }
    if (state.status === "preparing-device") {
      return {
        title: state.topic,
        meta: (
          <>
            <StatusDot label="preparing" tone="accent" live />
            <Button onClick={resetBuild}>Cancel build</Button>
          </>
        ),
        body: <PreparingDeviceState topic={state.topic} progress={state.progress} />,
      };
    }
    if (state.status === "error") {
      const { request, message } = state;
      return {
        title: request.topic,
        meta: null,
        // Retry re-runs the identical build — same depth, level, and trust switch.
        body: <ErrorState message={message} onRetry={() => generate(request)} />,
      };
    }
    // Streaming pre-handoff (course id not yet known), or the one transient frame between the
    // stream finishing and the handoff effect moving the URL.
    if (state.status === "streaming") return buildStreamingCanvas(state);
    return buildVideosFinishingCanvas() ?? buildReadyCanvas(state.course, resetBuild, state.runId);
  })();

  return (
    <>
      <AgentShell
        sidebar={sidebar}
        title={canvas.title}
        meta={canvas.meta}
        banner={
          <DraftModeBanner
            capabilities={capabilities}
            onOpenSettings={settingsOpen ? undefined : openSettings}
          />
        }
        layout={sidebarLayout}
        mobileNavOpen={mobileNavOpen}
        onOpenMobileNav={openMobileNav}
        onCloseMobileNav={closeMobileNav}
      >
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
  // The studio (live API) is gated behind login when Supabase is configured; the offline seed is
  // always open. AuthProvider wraps both so the rail's account control can read the session.
  return (
    <AuthProvider>
      {apiBaseUrl ? (
        // Navigation state lives in the URL for the studio only; the offline seed surface is a
        // single view and stays router-free.
        // useTransitions={false}: the router's location updates must be urgent. Wrapped in
        // startTransition (the default), a navigation that lands in the same flush as other
        // state churn (e.g. a build stream's updates) can be dropped — window.history moves
        // while useLocation never follows, stranding the canvas on the old route.
        <BrowserRouter useTransitions={false}>
          <AuthGate apiBaseUrl={apiBaseUrl}>
            <StudioApp apiBaseUrl={apiBaseUrl} theme={theme} onToggleTheme={toggle} />
          </AuthGate>
        </BrowserRouter>
      ) : (
        <SeedApp theme={theme} onToggleTheme={toggle} />
      )}
    </AuthProvider>
  );
}
