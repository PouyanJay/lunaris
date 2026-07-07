import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { RAIL_MAX_WIDTH, RAIL_MIN_WIDTH, useRailLayout } from "../../hooks/useRailLayout";
import { answersToClarification, recommendedAnswers } from "../../lib/clarification";
import { applyComposerLevel, type ComposerLevel } from "../../lib/composerLevel";
import { fetchBrief } from "../../lib/fetchBrief";
import { CourseLoadError } from "../../lib/loadCourse";
import type { BriefLoadState, Clarification } from "../../types/clarifier";
import type { CourseRun, DiscoveryDepth } from "../../types/course";
import { TopicForm } from "../TopicForm";
import { ComposerOptions } from "./ComposerOptions";
import { ConfigRail } from "./ConfigRail";
import { RecentBuildsTable } from "./RecentBuildsTable";
import styles from "./IdleCourseSetup.module.css";

/** The config rail persists its collapse/width separately from the reader rail. */
const RAIL_STORAGE_KEY = "lunaris.config.rail";

interface IdleCourseSetupProps {
  apiBaseUrl: string;
  /** Build the course: the topic, the learner's confirmed clarification (absent → inference-only),
   *  the chosen search depth, and the "Official sources only" trust switch. */
  onGenerate: (
    topic: string,
    clarification: Clarification | undefined,
    discoveryDepth: DiscoveryDepth,
    officialOnly: boolean,
  ) => void;
  /** Open the operator/admin Settings panel (the rail only points there). */
  onOpenSettings: () => void;
  /** The run history (from the shell's useRuns) — drives the composer's recent-builds table. */
  runs?: CourseRun[];
}

/**
 * The idle "new course" surface: a topic-entry column welded to a persistent, resizable, collapsible
 * course-setup rail. The rail is the editable projection of the brief + build settings (see
 * {@link ConfigRail}); this owns the topic, the chosen depth, and the learner-tier brief lifecycle so
 * the confirmed values thread straight into the build. Replaces the buried Personalize modal: the
 * default path is still one click (Generate), personalization is always one glance away in the rail.
 *
 * Layout mirrors the reader: a two-column grid driven by `useRailLayout` (drag/keyboard resize,
 * collapse to an edge tab on wide screens, a focus-trapped drawer on narrow). A topic edit
 * invalidates any brief read for the previous topic, so a stale clarifier can never build.
 */
export function IdleCourseSetup({
  apiBaseUrl,
  onGenerate,
  onOpenSettings,
  runs = [],
}: IdleCourseSetupProps) {
  const [topic, setTopic] = useState("");
  const [depth, setDepth] = useState<DiscoveryDepth>("standard");
  // The composer's quick options bar: target level (mapped onto the brief's clarification) and the
  // per-build "Official sources only" trust switch. Level "recommended" = today's inferred default.
  const [level, setLevel] = useState<ComposerLevel>("recommended");
  const [officialOnly, setOfficialOnly] = useState(false);
  const [brief, setBrief] = useState<BriefLoadState>({ status: "blank" });
  const briefController = useRef<AbortController | null>(null);

  const rail = useRailLayout(RAIL_STORAGE_KEY);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef<HTMLDivElement>(null);
  const drawerToggleRef = useRef<HTMLButtonElement>(null);

  // Cancel any in-flight brief read on unmount so it can't settle on a gone component.
  useEffect(() => () => briefController.current?.abort(), []);

  // Reading the topic resets any brief that was read for the previous topic — its inference and
  // answers no longer apply, so it must not silently build the new topic with stale answers.
  const handleTopicChange = useCallback((value: string) => {
    setTopic(value);
    briefController.current?.abort();
    setBrief({ status: "blank" });
  }, []);

  const loadBrief = useCallback(() => {
    const trimmed = topic.trim();
    if (!trimmed) return;
    briefController.current?.abort();
    const controller = new AbortController();
    briefController.current = controller;
    setBrief({ status: "loading" });
    fetchBrief(apiBaseUrl, trimmed, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setBrief({ status: "ready", data, answers: recommendedAnswers(data.clarifier) });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message =
          error instanceof CourseLoadError ? error.message : "We couldn't read your goal. Try again.";
        setBrief({ status: "error", message });
      });
  }, [apiBaseUrl, topic]);

  const handleAnswerChange = useCallback((id: string, value: string) => {
    setBrief((prev) =>
      prev.status === "ready" ? { ...prev, answers: { ...prev.answers, [id]: value } } : prev,
    );
  }, []);

  // Build the clarification from the loaded brief (else inference-only), then let the options-bar
  // Level override its target level — mapping the quick control onto the brief, not duplicating it.
  // Depth and the official-only switch always accompany.
  const handleSubmit = useCallback(
    (submitted: string) => {
      const fromBrief =
        brief.status === "ready" ? answersToClarification(brief.answers) : undefined;
      const clarification = applyComposerLevel(fromBrief, level);
      onGenerate(submitted, clarification, depth, officialOnly);
    },
    [brief, level, depth, officialOnly, onGenerate],
  );

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    drawerToggleRef.current?.focus();
  }, []);
  useEscapeKey(drawerOpen, closeDrawer);
  useAutoHideScroll(mainRef);

  return (
    <div
      className={`${styles.layout} ${rail.resizing ? styles.resizing : ""}`}
      style={{ "--rail-width": rail.collapsed ? "0px" : `${rail.width}px` } as CSSProperties}
      data-rail-collapsed={rail.collapsed ? "true" : undefined}
    >
      <div className={`${styles.main} scroller`} ref={mainRef}>
        {/* Narrow-screen affordance: the rail becomes a drawer, opened from here (shown via CSS). */}
        <div className={styles.drawerBar}>
          <button
            ref={drawerToggleRef}
            type="button"
            className={styles.drawerToggle}
            aria-expanded={drawerOpen}
            aria-controls="config-rail"
            onClick={() => setDrawerOpen((open) => !open)}
          >
            Course setup
          </button>
        </div>
        <TopicForm
          value={topic}
          onChange={handleTopicChange}
          onSubmit={handleSubmit}
          options={
            <ComposerOptions
              depth={depth}
              onDepthChange={setDepth}
              level={level}
              onLevelChange={setLevel}
              officialOnly={officialOnly}
              onOfficialOnlyChange={setOfficialOnly}
            />
          }
        />
        <RecentBuildsTable runs={runs} />
      </div>

      {/* Drag handle between the topic column and the rail (wide screens, expanded only). */}
      {!rail.collapsed && (
        <div
          className={styles.splitter}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize course setup"
          aria-valuenow={rail.width}
          aria-valuemin={RAIL_MIN_WIDTH}
          aria-valuemax={RAIL_MAX_WIDTH}
          tabIndex={0}
          onPointerDown={rail.startResize}
          onKeyDown={rail.nudgeWidth}
        />
      )}

      {/* The course-setup rail: a static column on wide screens, a drawer on narrow. One instance —
          the wrapper's class switches presentation. */}
      <div
        id="config-rail"
        className={`${styles.railWrap} ${drawerOpen ? styles.railWrapOpen : ""}`}
      >
        <ConfigRail
          topic={topic}
          brief={brief}
          onLoadBrief={loadBrief}
          onAnswerChange={handleAnswerChange}
          onOpenSettings={onOpenSettings}
          onCollapse={rail.toggleCollapsed}
          onClose={closeDrawer}
        />
      </div>

      {/* When collapsed on wide screens, a slim edge tab brings it back. */}
      {rail.collapsed && (
        <button
          type="button"
          className={styles.railReveal}
          onClick={rail.toggleCollapsed}
          aria-label="Show course setup"
        >
          <span aria-hidden="true">‹</span>
          <span className={styles.railRevealText}>Course setup</span>
        </button>
      )}

      {drawerOpen && (
        <button
          type="button"
          className={styles.scrim}
          aria-label="Close course setup overlay"
          onClick={closeDrawer}
        />
      )}
    </div>
  );
}
