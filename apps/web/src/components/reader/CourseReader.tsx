import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { useMediaQuery } from "../../hooks/useMediaQuery";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useCourseProgress } from "../../hooks/useCourseProgress";
import { useStudyHeartbeat } from "../../hooks/useStudyHeartbeat";
import { useActivity } from "../../hooks/useActivity";
import { useLessonVideo } from "../../hooks/useLessonVideo";
import { RAIL_MAX_WIDTH, RAIL_MIN_WIDTH, useRailLayout } from "../../hooks/useRailLayout";
import type { AssessmentItem, Course, Lesson, Objective, Resource } from "../../types/course";
import { Button } from "../primitives/Button";
import { SegmentedControl, type Segment } from "../primitives/SegmentedControl";
import { LearnMode } from "./LearnMode";
import { TrailBand } from "./TrailBand";
import { WatchSurface } from "./WatchSurface";
import { deriveEffectiveMode, useLearnMode, type ReaderMode } from "./useLearnMode";
import { AnnotationRail } from "./AnnotationRail";
import { BookmarkToggle } from "../bookmarks/BookmarkToggle";
import { Callout } from "./Callout";
import { buildAnnotations, type PhaseRef } from "./annotations";
import { BuildProvenance } from "./BuildProvenance";
import { LessonVideoHero } from "./LessonVideoHero";
import { ReaderOutline, type OutlineGroup } from "./ReaderOutline";
import { ScopeBand } from "./ScopeBand";
import { flattenLessons } from "../../lib/flattenLessons";
import { lessonStateFor } from "../../lib/lessonState";
import { buildGlossaryIndex } from "../../lib/glossaryIndex";
import { deriveTldr } from "../../lib/lessonTldr";
import { buildSectionEntries } from "./readerSections";
import styles from "./CourseReader.module.css";

/** Below this the annotation rail renders as an off-canvas drawer — must match the
 *  `@media (max-width: 1100px)` block in CourseReader.module.css. */
const RAIL_DRAWER_QUERY = "(max-width: 1100px)";

// The mode preference key rides along for tests and callers that pin the mode.
export { READER_MODE_KEY } from "./useLearnMode";

/** The teaching phases (Merrill's First Principles, in order), relabelled to the lesson ARC the
 *  course is designed around (P7.3) so the learner reads a coherent rhythm — strategies → worked
 *  example → practice → transfer — bracketed by the "expects" and "self-check" bookends. */
const PHASES: (PhaseRef & { cue: string })[] = [
  { key: "activate", label: "Warm-up", cue: "Reconnect with what you already know" },
  {
    key: "demonstrate",
    label: "Strategies & worked example",
    cue: "See the approach worked through",
  },
  { key: "apply", label: "Practice", cue: "Try it yourself" },
  { key: "integrate", label: "Make it your own", cue: "Transfer it to your own context" },
];

/** A lesson in course-wide reading order, carrying its owning module's title for context (lessons
 *  have no title of their own in the schema) and a display label. The module's assessment is
 *  attached to its last lesson so it shows once (as the Learn arc's closing step). */
interface ReaderLesson {
  lesson: Lesson;
  /** The owning module's id — the key objective progress is stored under. */
  moduleId: string;
  moduleTitle: string;
  /** The researched competency the owning module builds toward (P7.3), shown so the learner sees
   *  what the lesson earns; null on the no-research path. */
  competency: string | null;
  label: string;
  /** The owning module's full objective list — feeds the lesson's TL;DR takeaways (docked in Watch)
   *  and the Try First challenge evidence (Learn). Carried on EVERY lesson of the module. */
  moduleObjectives: Objective[];
  assessment: AssessmentItem[];
}

interface ReaderModel {
  lessons: ReaderLesson[];
  groups: OutlineGroup[];
  /** Each module KC → the lesson index that opens its module, for Map → lesson drill-in. */
  kcToLessonIndex: Map<string, number>;
}

/** Build the reader's model over the shared course-order flattening: the ordered lesson list,
 *  outline groups, and a KC→lesson index. Modules with no authored lessons never appear — they
 *  have nothing to read. */
function buildReaderModel(course: Course): ReaderModel {
  const lessons: ReaderLesson[] = [];
  const groups: OutlineGroup[] = [];
  const kcToLessonIndex = new Map<string, number>();
  for (const flat of flattenLessons(course)) {
    const label = `Lesson ${flat.index + 1}`;
    lessons.push({
      lesson: flat.lesson,
      moduleId: flat.module.id,
      moduleTitle: flat.module.title,
      competency: flat.module.competency,
      label,
      moduleObjectives: flat.module.objectives,
      assessment: flat.isLastInModule ? flat.module.assessment.items : [],
    });
    if (flat.isFirstInModule) {
      for (const kc of flat.module.kcs) {
        if (!kcToLessonIndex.has(kc)) kcToLessonIndex.set(kc, flat.index);
      }
      groups.push({ moduleId: flat.module.id, moduleTitle: flat.module.title, items: [] });
    }
    groups[groups.length - 1]!.items.push({ index: flat.index, lessonId: flat.lesson.id, label });
  }
  return { lessons, groups, kcToLessonIndex };
}

/** The lesson's curated resources across every teaching phase, deduped by URL — the Watch surface
 *  docks them under the video as lesson-level aids (Learn mode surfaces them per phase, as steps).
 *  Phase order (activate → integrate) is preserved so the dock reads in teaching order. */
function lessonResourcesOf(lesson: Lesson): Resource[] {
  const seen = new Set<string>();
  const collected: Resource[] = [];
  for (const segment of Object.values(lesson.segments)) {
    for (const resource of segment.resources ?? []) {
      if (!seen.has(resource.url)) {
        seen.add(resource.url);
        collected.push(resource);
      }
    }
  }
  return collected;
}

/** A drill-in into the reader: focus the lesson covering a concept (the Map's KC → lesson
 *  resolution — the one target a URL can't name directly). `seq` increments per request so the
 *  same concept can be re-requested after the learner has navigated away. Lesson-id deep links
 *  are URLs (P6). */
export interface LessonFocusRequest {
  kc: string;
  seq: number;
}

interface CourseReaderProps {
  course: Course;
  /** The lesson the URL addresses (P6 lesson-in-URL). With `onNavigateLesson` present the URL is
   *  the source of truth for the reading position; the reader derives its focused lesson from it
   *  and canonicalises a bare or stale reader URL to the focused lesson (replace). */
  activeLessonId?: string | undefined;
  /** Navigate to a lesson's URL — every lesson change (rail, prev/next, drill-in) goes through
   *  this so the URL always names the reading position. Absent (offline sample / standalone)
   *  the reader keeps the position as internal state. */
  onNavigateLesson?: ((lessonId: string, options?: { replace?: boolean }) => void) | undefined;
  focusRequest?: LessonFocusRequest | null;
  /** Re-author the focused lesson with the agent, returning the updated course. Absent => the
   *  regenerate action is hidden (e.g. offline). */
  onRegenerate?: ((lessonId: string) => Promise<Course>) | undefined;
  /** The API origin for per-lesson video generation. Absent (offline sample course) => the
   *  video hero slot is not rendered. */
  apiBaseUrl?: string | undefined;
  /** Leave the reader for the course's Overview tab — on the first lesson the back affordance
   *  leads out rather than sitting disabled. Absent (offline sample) hides it. */
  onExitToOverview?: (() => void) | undefined;
}

/** The lesson reader (Lessons view): a persistent course outline, the focused lesson's surface, and
 *  a parallel "Sources & checks" rail that lifts the verifier's claims out of the lesson (req 1). One
 *  control switches the surface between **Learn** (Focus Flow — the lesson's arc walked one guided
 *  step at a time: expects, each teaching phase's prose/visuals/resources, self-check, assessment) and
 *  **Watch** (Cinema — the lesson's explainer video, generated on demand where none exists yet).
 *  Selecting a rail entry highlights it. On narrow screens the rail collapses behind a "Sources &
 *  checks" toggle that opens it as a drawer. */
export function CourseReader({
  course,
  activeLessonId,
  onNavigateLesson,
  focusRequest,
  onRegenerate,
  apiBaseUrl,
  onExitToOverview,
}: CourseReaderProps) {
  // A successful regenerate swaps in the updated course locally until a different course is opened.
  const [regeneratedCourse, setRegeneratedCourse] = useState<Course | null>(null);
  const active = regeneratedCourse ?? course;
  const { lessons, groups, kcToLessonIndex } = useMemo(() => buildReaderModel(active), [active]);
  const citations = useMemo(
    () => new Map(active.provenance.map((citation) => [citation.id, citation])),
    [active.provenance],
  );
  // Course glossary (Field Guide): KC definitions from the graph + authored :term directives,
  // auto-marked into every phase's prose. Memoised — the index is course-wide and stable.
  const glossary = useMemo(() => buildGlossaryIndex(active), [active]);
  const [activeIndex, setActiveIndex] = useState(0);
  // A lesson navigation we've requested but whose URL hasn't come back around yet. The
  // canonicalise effect must stand down while one is in flight — its replace would otherwise
  // overwrite the requested navigation (both fire in the same commit, before the URL updates).
  const pendingLessonNav = useRef<string | null>(null);
  // Every lesson change goes through one door: a routed reader navigates (the URL is the source
  // of truth for the reading position), a standalone reader sets internal state.
  const goToLesson = useCallback(
    (index: number) => {
      const target = lessons[index];
      if (!target) return;
      if (onNavigateLesson) {
        pendingLessonNav.current = target.lesson.id;
        onNavigateLesson(target.lesson.id);
      } else {
        setActiveIndex(index);
      }
    },
    [lessons, onNavigateLesson],
  );
  // The learner's marks on this course (best-effort; null offline / while loading). Offline
  // (no apiBaseUrl) skips the fetch entirely by keying on an empty origin.
  const { progress, markObjective, markLesson, markOpened } = useCourseProgress(
    apiBaseUrl ?? "",
    course.id,
  );
  // Study-minutes heartbeat: an open, visible reader is "studying" (paused while backgrounded).
  useStudyHeartbeat(apiBaseUrl ?? "", true);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeClaimId, setActiveClaimId] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  // The course outline is a static left column on desktop; on phones it opens as a left drawer.
  const [outlineOpen, setOutlineOpen] = useState(false);
  const rail = useRailLayout();
  // One labelled Sources & checks control drives the rail everywhere (P6): below the rail
  // breakpoint it opens the drawer; on wide screens it collapses/restores the column.
  const railDrawer = useMediaQuery(RAIL_DRAWER_QUERY);
  const railVisible = railDrawer ? railOpen : !rail.collapsed;
  const toggleRail = railDrawer ? () => setRailOpen((open) => !open) : rail.toggleCollapsed;
  const paneRef = useRef<HTMLDivElement>(null);
  const railToggleRef = useRef<HTMLButtonElement>(null);
  const outlineToggleRef = useRef<HTMLButtonElement>(null);
  const handledFocusSeq = useRef(0);
  const reduceMotion = usePrefersReducedMotion();

  // Reset to the first lesson and drop any regenerate override when a DIFFERENT course is
  // opened. Guarded by a previous-course ref: StrictMode replays effects on mount, and an
  // unguarded reset would zero the index after the focus effect already consumed a drill-in
  // request (Continue/row clicks landed on lesson 1 in dev, but not in tests).
  const lastCourse = useRef(course);
  useEffect(() => {
    if (lastCourse.current === course) return;
    lastCourse.current = course;
    setActiveIndex(0);
    setRegeneratedCourse(null);
    pendingLessonNav.current = null;
  }, [course]);
  // Honour a drill-in once per request: jump to the lesson covering the requested concept (Map).
  // The seq ref gates re-firing, so a course switch (which changes the lookup structures) won't
  // re-focus. -1 (concept not in this course) leaves the position alone.
  useEffect(() => {
    if (!focusRequest || focusRequest.seq === handledFocusSeq.current) return;
    handledFocusSeq.current = focusRequest.seq;
    const index = kcToLessonIndex.get(focusRequest.kc) ?? -1;
    if (index >= 0) goToLesson(index);
  }, [focusRequest, kcToLessonIndex, goToLesson]);

  const total = lessons.length;
  // Routed (onNavigateLesson present): the URL names the reading position — derive the focused
  // lesson from it; an absent or unknown segment falls back to the first lesson and the
  // canonicalise effect below repairs the URL. Standalone: internal state, with a defensive clamp
  // for the single render between switching to a shorter course and the reset-on-course effect.
  const routedIndex = activeLessonId
    ? lessons.findIndex(({ lesson }) => lesson.id === activeLessonId)
    : -1;
  const safeIndex = onNavigateLesson
    ? Math.max(0, routedIndex)
    : Math.min(activeIndex, Math.max(0, total - 1));
  const current = lessons[safeIndex];

  // On a lesson change: return to the top of the reading pane (scrollTo is optional-chained — jsdom
  // doesn't implement it), clear any stale regenerate error, and drop the cross-highlight selection.
  useEffect(() => {
    paneRef.current?.scrollTo?.({ top: 0 });
    setError(null);
    setActiveClaimId(null);
  }, [safeIndex]);

  // First open of a lesson marks it in_progress — but never regresses a lesson already marked
  // (a revisited done lesson stays done). Waits for the snapshot so reloads don't re-mark.
  const currentLessonId = current?.lesson.id;
  useEffect(() => {
    if (!progress || !currentLessonId) return;
    const known = progress.lessons.some((mark) => mark.lessonId === currentLessonId);
    if (!known) markLesson(currentLessonId, "in_progress");
  }, [progress, currentLessonId, markLesson]);

  // Canonicalise the reader URL (routed only): a bare /lessons or a stale lesson segment is
  // replaced with the focused lesson's URL, so every reading position is addressable and
  // back/forward walk lessons. Replace, not push — repairing the URL is not a navigation step.
  useEffect(() => {
    if (!onNavigateLesson || !currentLessonId) return;
    // A requested navigation has landed once the URL names its target — resume canonicalising.
    if (pendingLessonNav.current === activeLessonId) pendingLessonNav.current = null;
    if (pendingLessonNav.current !== null) return;
    if (activeLessonId !== currentLessonId) onNavigateLesson(currentLessonId, { replace: true });
  }, [onNavigateLesson, activeLessonId, currentLessonId]);

  // Every lesson view refreshes the course's open-recency + reading position (the library's
  // last-opened sort, and where the Continue CTA resumes). Unlike the in_progress mark above,
  // this fires on every visit — recency must move even on a re-read.
  useEffect(() => {
    if (currentLessonId) markOpened(currentLessonId);
  }, [currentLessonId, markOpened]);

  const annotations = useMemo(
    () => (current ? buildAnnotations(current.lesson.segments, PHASES, citations) : []),
    [current, citations],
  );
  // Focus Flow: the Learn/Watch preference, step position, and step-derived structures.
  const { preference, selectMode, stepIndex, setStepIndex, steps, sectionProgress, firstStepOf } =
    useLearnMode({
      lesson: current?.lesson ?? null,
      lessonId: currentLessonId ?? null,
      phases: PHASES,
      assessment: current?.assessment ?? [],
    });
  // The focused lesson's video — one `useLessonVideo` owned HERE (not inside the hero) so a ready,
  // chaptered video can light up the Watch mode regardless of the current reading mode. Idle and
  // unfetched for a lesson the build shipped no video for, or offline (no apiBaseUrl).
  const lessonVideo = useLessonVideo(
    apiBaseUrl ?? "",
    active.id,
    current?.lesson.id ?? "",
    undefined,
    apiBaseUrl ? (current?.lesson.video ?? null) : null,
  );
  // Cinema (Watch): the mode is always offered online (Watch is where a video is generated when the
  // lesson has none yet); `watchAvailable` is narrower — a ready video that carries a navigable
  // chapter outline, which drives the front-door default. The effective mode folds that in: an unset
  // preference opens in Watch when such a video exists (else Learn); a stored `watch` sticks even on a
  // video-less lesson (Watch then shows the generate affordance); an explicit Learn choice always
  // wins; offline (Watch not offered) resolves to Learn.
  const watchOffered = Boolean(apiBaseUrl);
  const watchAvailable =
    lessonVideo.state.phase === "ready" && lessonVideo.state.chapters.length > 0;
  const effectiveMode = deriveEffectiveMode(preference, watchAvailable, watchOffered);
  // The mode toggle: Learn always, Watch whenever a video is reachable (online).
  const modeSegments: Segment<ReaderMode>[] = [
    { value: "learn", label: "Learn" },
    ...(watchOffered ? [{ value: "watch" as const, label: "Watch" }] : []),
  ];
  // The learner's activity snapshot (streak / event feed) — the Trail band's motivation source.
  // Fetched only in Learn mode (where the band shows) and online; Watch / offline settle without a
  // fetch. Reloaded on lesson completion so it reflects the just-earned event.
  const { state: activity, reload: reloadActivity } = useActivity(
    apiBaseUrl ?? "",
    effectiveMode === "learn",
  );
  // Complete the lesson: mark done and advance. Learn's final Continue and Watch's footer Next both
  // call it.
  const completeLesson = useCallback(() => {
    if (progress && currentLessonId) markLesson(currentLessonId, "done");
    // The done mark emits a `completed` event server-side (P9); refresh the Trail band so it
    // reflects the just-earned streak. Best-effort — a stale snapshot is harmless.
    reloadActivity();
    if (safeIndex < total - 1) goToLesson(safeIndex + 1);
  }, [progress, currentLessonId, markLesson, reloadActivity, safeIndex, total, goToLesson]);
  // Jump to a section chosen in the outline — a step jump in Learn mode — and close the phone
  // outline drawer so the destination isn't hidden behind it. (Watch has no in-page sections.)
  const selectSection = useCallback(
    (id: string) => {
      if (effectiveMode === "learn") {
        const target = firstStepOf(id);
        if (target !== undefined) setStepIndex(target);
      }
      setOutlineOpen(false);
    },
    [effectiveMode, firstStepOf, setStepIndex],
  );

  // The narrow-screen drawer: Esc closes it and returns focus to the toggle.
  const closeRail = useCallback(() => {
    setRailOpen(false);
    railToggleRef.current?.focus();
  }, []);
  useEscapeKey(railOpen, closeRail);

  // The phone outline drawer: Esc closes it and returns focus to its toggle; selecting a lesson
  // closes it so the chosen lesson isn't hidden behind the drawer.
  const closeOutline = useCallback(() => {
    setOutlineOpen(false);
    outlineToggleRef.current?.focus();
  }, []);
  useEscapeKey(outlineOpen, closeOutline);
  const selectLesson = useCallback(
    (index: number) => {
      goToLesson(index);
      setOutlineOpen(false);
    },
    [goToLesson],
  );
  // Lock body scroll while the outline drawer is open (phones), so the lesson behind the scrim
  // doesn't scroll under it — mirrors the shell's nav-drawer behavior.
  useEffect(() => {
    if (!outlineOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [outlineOpen]);
  // The reading column gets thin, auto-hiding scrollbars (fade in while scrolling, out when idle).
  useAutoHideScroll(paneRef);

  if (!current) {
    return (
      <div className={styles.empty} role="status">
        No lessons yet — this course hasn’t been authored.
      </div>
    );
  }

  const focusedLessonId = current.lesson.id;
  // The arc bookends, defaulted for courses built before P7.3 (no arc) — read once, used in both
  // the render guard and the list below.
  const expects = current.lesson.expects ?? [];
  const selfCheck = current.lesson.selfCheck ?? [];
  // The lesson's key takeaways, de-scaffolded from its module's objectives — docked beneath the
  // Watch video. An objective-less module (no-research path) yields none (the dock is omitted).
  const tldr = deriveTldr(current.moduleObjectives);
  const lessonResources = lessonResourcesOf(current.lesson);
  // Which of the module's objectives are marked understood — feeds the Try First challenge evidence
  // (Learn). Undefined offline.
  const understoodObjectives = progress
    ? new Set(
        progress.objectives
          .filter((mark) => mark.moduleId === current.moduleId)
          .map((mark) => mark.objectiveIndex),
      )
    : undefined;
  // Try First: a self-graded "I got it" on a challenge evidences the objective it assesses,
  // through the existing objective-understood channel (AD2). The challenge's own assessment
  // items live on the module (shown once, on its last lesson); its objectives are module-wide.
  const challengeContext = {
    objectives: current.moduleObjectives,
    understoodObjectives: understoodObjectives ?? new Set<number>(),
    onEvidenceObjective: progress
      ? (index: number, understood: boolean) => markObjective(current.moduleId, index, understood)
      : undefined,
  };
  // The focused lesson's sections for the outline's nested level — read-state from the Learn step
  // position (Watch has no in-page sections; the level simply reflects the last Learn position).
  const sectionEntries = buildSectionEntries({
    expects,
    selfCheck,
    assessmentCount: current.assessment.length,
    phases: PHASES,
    activeSection: sectionProgress.activeSection,
    passedSections: sectionProgress.passedSections,
  });
  const regenerate = async () => {
    if (!onRegenerate) return;
    setPending(true);
    setError(null);
    try {
      setRegeneratedCourse(await onRegenerate(focusedLessonId));
    } catch {
      setError("Couldn’t regenerate this lesson. Try again.");
    } finally {
      setPending(false);
    }
  };

  return (
    <div
      className={`${styles.reader} ${rail.resizing ? styles.resizing : ""}`}
      style={{ "--rail-width": rail.collapsed ? "0px" : `${rail.width}px` } as CSSProperties}
      data-rail-collapsed={rail.collapsed ? "true" : undefined}
    >
      <ReaderOutline
        groups={groups}
        activeIndex={safeIndex}
        onSelect={selectLesson}
        stateFor={progress ? (lessonId) => lessonStateFor(progress, lessonId) : undefined}
        sections={sectionEntries}
        onSelectSection={selectSection}
        className={`${styles.outlineDrawer} ${outlineOpen ? styles.outlineDrawerOpen : ""}`.trim()}
      />
      <div
        className={`${styles.pane} scroller`}
        ref={paneRef}
        role="region"
        aria-label="Lesson reader"
        tabIndex={0}
      >
        <article className={styles.page}>
          {/* Phone-only reader bar: opens the lesson outline (a drawer on small screens) and shows
              the reading position. Hidden on desktop where the outline is a static column. */}
          <div className={styles.readerBar}>
            <button
              ref={outlineToggleRef}
              type="button"
              className={styles.outlineToggle}
              aria-expanded={outlineOpen}
              aria-controls="reader-outline"
              onClick={() => setOutlineOpen(true)}
            >
              <ListIcon />
              Lessons
            </button>
            <span className={`${styles.barProgress} mono`}>
              {safeIndex + 1} / {total}
            </span>
          </div>
          {/* Honesty caveat (CQ Phase 1.6): an ungrounded research-needing course says so. */}
          {course.scopeNote && <Callout variant="warning">{course.scopeNote}</Callout>}
          {/* Scope-realism band (CQ Phase 3.1): the effort/does-n't framing, shown once at entry.
              (The course trailer + topic-overview videos live on the Overview tab, below this band —
              see CourseOverview — not in the reading column.) */}
          {safeIndex === 0 && course.scope && <ScopeBand scope={course.scope} />}
          {/* Per-course build tag (keyless-fallbacks T5): the persistent record of which keyless
              fallbacks produced this course, shown once at entry. Renders nothing for a fully-live
              build, and unlike the live badge never flips — it only changes on rebuild. */}
          {safeIndex === 0 && course.buildCapabilities && (
            <BuildProvenance buildCapabilities={course.buildCapabilities} />
          )}
          <header className={styles.lessonHead}>
            <div className={styles.lessonHeading}>
              <p className="eyebrow">{current.moduleTitle}</p>
              <h2 className={styles.lessonTitle}>{current.label}</h2>
              {current.competency && (
                <p className={styles.competency}>
                  Builds toward <span className={styles.competencyName}>{current.competency}</span>
                </p>
              )}
            </div>
            <div className={styles.headMeta}>
              <p className={`${styles.progress} mono`}>
                Lesson {safeIndex + 1} of {total}
              </p>
              {/* Focus Flow: guided steps (Learn) vs the video (Watch) — one control. Watch is
                  offered wherever a video is reachable (online), generating one on demand if none
                  exists yet. */}
              <SegmentedControl
                segments={modeSegments}
                value={effectiveMode}
                onChange={selectMode}
                label="Reading mode"
              />
              <BookmarkToggle
                subject={`${current.label} · ${current.moduleTitle}`}
                draft={{
                  kind: "lesson",
                  courseId: course.id,
                  targetId: current.lesson.id,
                  courseTitle: course.topic,
                  title: `${current.label} · ${current.moduleTitle}`,
                  lessonId: current.lesson.id,
                }}
              />
              {annotations.length > 0 && (
                <button
                  ref={railToggleRef}
                  type="button"
                  className={styles.railToggle}
                  aria-expanded={railVisible}
                  data-open={railVisible || undefined}
                  aria-controls="annotation-rail"
                  aria-label={`Sources & checks, ${annotations.length}`}
                  onClick={toggleRail}
                >
                  {/* On phones the words collapse to this verification glyph (see CSS); the count
                      stays as the at-a-glance signal. */}
                  <svg
                    className={styles.railToggleIcon}
                    viewBox="0 0 24 24"
                    width="16"
                    height="16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 3l7 3v5c0 4.4-3 7.6-7 9-4-1.4-7-4.6-7-9V6l7-3z" />
                    <path d="M9 12l2 2 4-4" />
                  </svg>
                  <span className={styles.railToggleLabel}>Sources &amp; checks</span>{" "}
                  <span className={`mono ${styles.railCount}`}>{annotations.length}</span>
                </button>
              )}
            </div>
          </header>

          {/* Focus Flow (Learn): the guided step surface — every piece of the lesson (expects, each
              phase's prose/visuals/resources, self-check, assessment) walked one idea at a time. */}
          {effectiveMode === "learn" && (
            <LearnMode
              steps={steps}
              index={stepIndex}
              onNavigate={setStepIndex}
              onComplete={completeLesson}
              completeLabel={safeIndex >= total - 1 ? "Finish course" : "Next lesson"}
              glossary={glossary}
              challenge={challengeContext}
            />
          )}

          {/* Trail (phase 4): the motivation band — streak, minutes studied today, course
              position. A Learn-mode layer, and only where activity is reachable (best-effort). */}
          {effectiveMode === "learn" && apiBaseUrl && (
            <TrailBand activity={activity} lessonNumber={safeIndex + 1} lessonTotal={total} />
          )}

          {/* Cinema (Watch): the lesson's video front door. A ready chaptered video is the full
              Watch surface — the transcript-synced player with navigable chapters and per-chapter
              resources on the right, key takeaways docked beneath. Otherwise the hero carries the
              lesson's video lifecycle: generate it on demand (idle), progress while it builds, retry
              on failure, or the plain player for a pre-Cinema (un-chaptered) video. Watch is only
              reachable online, so `apiBaseUrl` is present here. */}
          {effectiveMode === "watch" &&
            (lessonVideo.state.phase === "ready" && lessonVideo.state.chapters.length > 0 ? (
              <WatchSurface
                videoUrl={lessonVideo.state.videoUrl}
                posterUrl={lessonVideo.state.posterUrl}
                captionsUrl={lessonVideo.state.captionsUrl}
                chapters={lessonVideo.state.chapters}
                transcript={lessonVideo.state.transcript}
                label={`${current.moduleTitle} — lesson video`}
                takeaways={tldr}
                resources={lessonResources}
              />
            ) : (
              <LessonVideoHero
                state={lessonVideo.state}
                generate={lessonVideo.generate}
                regenerate={lessonVideo.regenerate}
                stop={lessonVideo.stop}
                refresh={lessonVideo.refresh}
                video={current.lesson.video ?? null}
                title={current.moduleTitle}
              />
            ))}

          <footer className={styles.nav}>
            {onRegenerate ? (
              <Button onClick={regenerate} disabled={pending} aria-busy={pending}>
                {pending ? "Regenerating…" : "Regenerate lesson"}
              </Button>
            ) : (
              <span />
            )}
            {/* Lesson prev/next lives in the step surface's Continue in Learn mode — the footer pair
                would be a second "Next lesson" saying the same thing. Watch has no such control, so
                the footer carries lesson paging (and the Overview exit) there. */}
            {effectiveMode !== "watch" ? (
              <span />
            ) : (
              <div className={styles.navButtons}>
                {safeIndex === 0 && onExitToOverview ? (
                  // The design's prev-label rule: from lesson 1 the way back is the Overview, not
                  // a dead disabled button.
                  <Button aria-label="Back to overview" onClick={onExitToOverview}>
                    <ChevronLeftIcon />
                    Overview
                  </Button>
                ) : (
                  <Button
                    aria-label="Previous lesson"
                    disabled={safeIndex === 0}
                    onClick={() => goToLesson(Math.max(0, safeIndex - 1))}
                  >
                    <ChevronLeftIcon />
                    Previous
                  </Button>
                )}
                {safeIndex >= total - 1 ? (
                  <Button
                    variant="accent"
                    aria-label="Finish course"
                    disabled={!progress}
                    onClick={completeLesson}
                  >
                    Finish course
                  </Button>
                ) : (
                  <Button variant="accent" aria-label="Next lesson" onClick={completeLesson}>
                    Next lesson
                  </Button>
                )}
              </div>
            )}
          </footer>
          {error && (
            <p className={styles.regenError} role="alert">
              {error}
            </p>
          )}
        </article>
      </div>

      {/* Drag handle between the reading column and the rail (wide screens, expanded only). Resizes
          --rail-width 1:1 on pointer drag and via Arrow/Home/End when focused. */}
      {!rail.collapsed && annotations.length > 0 && (
        <div
          className={styles.splitter}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize sources and checks"
          aria-valuenow={rail.width}
          aria-valuemin={RAIL_MIN_WIDTH}
          aria-valuemax={RAIL_MAX_WIDTH}
          tabIndex={0}
          onPointerDown={rail.startResize}
          onKeyDown={rail.nudgeWidth}
        />
      )}

      {/* The annotation rail: a static third column on wide screens, a toggled drawer on narrow.
          One instance (no duplication) — the wrapper's class switches presentation. */}
      <div
        id="annotation-rail"
        className={`${styles.railWrap} ${railOpen ? styles.railWrapOpen : ""}`}
      >
        <AnnotationRail
          annotations={annotations}
          activeClaimId={activeClaimId}
          onSelect={setActiveClaimId}
          onClose={() => setRailOpen(false)}
          onCollapse={rail.toggleCollapsed}
          reduceMotion={reduceMotion}
          sourceContext={{
            courseId: course.id,
            courseTitle: course.topic,
            lessonId: currentLessonId ?? null,
          }}
        />
      </div>

      {/* When collapsed on wide screens, a slim edge tab brings the rail back. */}
      {rail.collapsed && annotations.length > 0 && (
        <button
          type="button"
          className={styles.railReveal}
          onClick={rail.toggleCollapsed}
          aria-label="Show sources and checks"
        >
          <span aria-hidden="true">‹</span>
          <span className={styles.railRevealText}>Sources &amp; checks</span>
        </button>
      )}
      {railOpen && (
        <button
          type="button"
          className={styles.scrim}
          aria-label="Close sources and checks"
          onClick={() => setRailOpen(false)}
        />
      )}
      {/* Phone outline drawer scrim — only shown at the phone breakpoint (CSS), dims behind the
          off-canvas lesson list. */}
      {outlineOpen && (
        <button
          type="button"
          className={styles.outlineScrim}
          aria-label="Close lessons"
          onClick={closeOutline}
        />
      )}
    </div>
  );
}

function ChevronLeftIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M15 18l-6-6 6-6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ListIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M8 6.5h12M8 12h12M8 17.5h12M4 6.5h.01M4 12h.01M4 17.5h.01"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}
