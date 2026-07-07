import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { useAutoHideScroll } from "../../hooks/useAutoHideScroll";
import { useEscapeKey } from "../../hooks/useEscapeKey";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { RAIL_MAX_WIDTH, RAIL_MIN_WIDTH, useRailLayout } from "../../hooks/useRailLayout";
import type { AssessmentItem, Course, Lesson, Objective } from "../../types/course";
import { Button } from "../primitives/Button";
import { AnnotationRail } from "./AnnotationRail";
import { Callout } from "./Callout";
import { buildAnnotations, type PhaseRef, phraseMarksFor } from "./annotations";
import { BuildProvenance } from "./BuildProvenance";
import { LessonAssessment } from "./LessonAssessment";
import { LessonVideoHero } from "./LessonVideoHero";
import { OverviewSection } from "./OverviewSection";
import { LessonObjectives } from "./LessonObjectives";
import { useCourseProgress } from "../../hooks/useCourseProgress";
import { LessonProse } from "./LessonProse";
import { LessonResources } from "./LessonResources";
import { LessonScaffold } from "./LessonScaffold";
import { ReaderOutline, type OutlineGroup } from "./ReaderOutline";
import { ScopeBand } from "./ScopeBand";
import { scrollIntoViewSafe } from "./scrollIntoViewSafe";
import { VisualRenderer } from "./visuals/VisualRenderer";
import styles from "./CourseReader.module.css";

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
 *  have no title of their own in the schema) and a display label. Module-level objectives and
 *  assessment are attached to the module's first / last lesson respectively, so each shows once. */
interface ReaderLesson {
  lesson: Lesson;
  /** The owning module's id — the key objective progress is stored under. */
  moduleId: string;
  moduleTitle: string;
  /** The researched competency the owning module builds toward (P7.3), shown so the learner sees
   *  what the lesson earns; null on the no-research path. */
  competency: string | null;
  label: string;
  objectives: Objective[];
  assessment: AssessmentItem[];
}

interface ReaderModel {
  lessons: ReaderLesson[];
  groups: OutlineGroup[];
  /** Each module KC → the lesson index that opens its module, for Map → Learn drill-in. */
  kcToLessonIndex: Map<string, number>;
}

/** Flatten the course into an ordered lesson list, outline groups, and a KC→lesson index in one
 *  pass. Modules with no authored lessons are skipped — they have nothing to read. */
function buildReaderModel(course: Course): ReaderModel {
  const lessons: ReaderLesson[] = [];
  const groups: OutlineGroup[] = [];
  const kcToLessonIndex = new Map<string, number>();
  for (const module of course.modules) {
    if (module.lessons.length === 0) continue;
    const items: OutlineGroup["items"] = [];
    const last = module.lessons.length - 1;
    const moduleStartIndex = lessons.length;
    module.lessons.forEach((lesson, lessonIndex) => {
      const index = lessons.length;
      const label = `Lesson ${index + 1}`;
      lessons.push({
        lesson,
        moduleId: module.id,
        moduleTitle: module.title,
        competency: module.competency,
        label,
        objectives: lessonIndex === 0 ? module.objectives : [],
        assessment: lessonIndex === last ? module.assessment.items : [],
      });
      items.push({ index, label });
    });
    for (const kc of module.kcs) {
      if (!kcToLessonIndex.has(kc)) kcToLessonIndex.set(kc, moduleStartIndex);
    }
    groups.push({ moduleId: module.id, moduleTitle: module.title, items });
  }
  return { lessons, groups, kcToLessonIndex };
}

/** A Map → Learn drill-in: focus the lesson covering `kc`. `seq` increments per request so the same
 *  concept can be re-requested after the learner has navigated away. */
export interface LessonFocusRequest {
  kc: string;
  seq: number;
}

interface CourseReaderProps {
  course: Course;
  focusRequest?: LessonFocusRequest | null;
  /** Re-author the focused lesson with the agent, returning the updated course. Absent => the
   *  regenerate action is hidden (e.g. offline). */
  onRegenerate?: ((lessonId: string) => Promise<Course>) | undefined;
  /** The API origin for per-lesson video generation. Absent (offline sample course) => the
   *  video hero slot is not rendered. */
  apiBaseUrl?: string | undefined;
}

/** The lesson reader (Learn view): a persistent course outline, a clean reading column, and a
 *  parallel "Sources & checks" rail that lifts the verifier's claims out of the prose (req 1). The
 *  reading column renders the focused lesson as its arc (P7.3) — competency, the "expects" bookend,
 *  the teaching phases, objectives, branded visuals, curated resources, and the closing self-check.
 *  Selecting a rail entry highlights the place it refers to in the prose (its matched sentence, or
 *  its phase); a prose cross-link highlights the rail entry. On narrow screens the rail collapses
 *  behind a "Sources & checks" toggle that opens it as a drawer. */
export function CourseReader({
  course,
  focusRequest,
  onRegenerate,
  apiBaseUrl,
}: CourseReaderProps) {
  // A successful regenerate swaps in the updated course locally until a different course is opened.
  const [regeneratedCourse, setRegeneratedCourse] = useState<Course | null>(null);
  const active = regeneratedCourse ?? course;
  const { lessons, groups, kcToLessonIndex } = useMemo(() => buildReaderModel(active), [active]);
  const citations = useMemo(
    () => new Map(active.provenance.map((citation) => [citation.id, citation])),
    [active.provenance],
  );
  const [activeIndex, setActiveIndex] = useState(0);
  // The learner's marks on this course (best-effort; null offline / while loading). Offline
  // (no apiBaseUrl) skips the fetch entirely by keying on an empty origin.
  const { progress } = useCourseProgress(apiBaseUrl ?? "", course.id);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeClaimId, setActiveClaimId] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(false);
  // The course outline is a static left column on desktop; on phones it opens as a left drawer.
  const [outlineOpen, setOutlineOpen] = useState(false);
  const rail = useRailLayout();
  const paneRef = useRef<HTMLDivElement>(null);
  const railToggleRef = useRef<HTMLButtonElement>(null);
  const outlineToggleRef = useRef<HTMLButtonElement>(null);
  const handledFocusSeq = useRef(0);
  const reduceMotion = usePrefersReducedMotion();

  // Reset to the first lesson and drop any regenerate override when a different course is opened.
  useEffect(() => {
    setActiveIndex(0);
    setRegeneratedCourse(null);
  }, [course]);
  // On a lesson change: return to the top of the reading pane (scrollTo is optional-chained — jsdom
  // doesn't implement it), clear any stale regenerate error, and drop the cross-highlight selection.
  useEffect(() => {
    paneRef.current?.scrollTo?.({ top: 0 });
    setError(null);
    setActiveClaimId(null);
  }, [activeIndex]);

  // Honour a Map drill-in once per request: jump to the lesson covering the requested concept. The
  // seq ref gates re-firing, so a course switch (which changes kcToLessonIndex) won't re-focus.
  useEffect(() => {
    if (!focusRequest || focusRequest.seq === handledFocusSeq.current) return;
    handledFocusSeq.current = focusRequest.seq;
    const index = kcToLessonIndex.get(focusRequest.kc);
    if (index !== undefined) setActiveIndex(index);
  }, [focusRequest, kcToLessonIndex]);

  const total = lessons.length;
  // Defensive clamp for the single render between switching to a shorter course and the
  // reset-on-course effect firing — keeps the focused index in range so `current` stays defined.
  const safeIndex = Math.min(activeIndex, Math.max(0, total - 1));
  const current = lessons[safeIndex];

  const annotations = useMemo(
    () => (current ? buildAnnotations(current.lesson.segments, PHASES, citations) : []),
    [current, citations],
  );
  // Per-phase cross-link marks, memoised (stable across an activeClaimId change) so selecting a
  // claim never re-parses a phase's Markdown — the prose's stateful children stay mounted.
  const marksByPhase = useMemo(() => {
    const byPhase = new Map<string, ReturnType<typeof phraseMarksFor>>();
    if (current) {
      for (const phase of PHASES) {
        byPhase.set(
          phase.key,
          phraseMarksFor(annotations, phase.key, current.lesson.segments[phase.key].prose),
        );
      }
    }
    return byPhase;
  }, [annotations, current]);
  const activeAnnotation =
    annotations.find((annotation) => annotation.id === activeClaimId) ?? null;

  // Selecting a claim opens the rail (so a prose marker reveals its entry on narrow screens) and
  // highlights it; stable so it doesn't churn the memoised prose.
  const selectClaim = useCallback((id: string) => {
    setActiveClaimId(id);
    setRailOpen(true);
  }, []);

  // Selecting a claim (from the rail or a prose cross-link) brings the place it refers to into view:
  // its matched sentence when there is one, else its whole phase (the best-effort fallback).
  useEffect(() => {
    if (!activeAnnotation) return;
    const pane = paneRef.current;
    if (!pane) return;
    const target =
      activeAnnotation.matchedSentence !== null
        ? pane.querySelector(`[data-claim-id="${activeAnnotation.id}"]`)
        : pane.querySelector(`[data-phase="${activeAnnotation.phaseKey}"]`);
    scrollIntoViewSafe(target, reduceMotion);
  }, [activeAnnotation, reduceMotion]);

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
  const selectLesson = useCallback((index: number) => {
    setActiveIndex(index);
    setOutlineOpen(false);
  }, []);
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
          {/* The course opens with video (explainer-video V5): the trailer + topic intro, pinned at
              the top of the course (entry only). Absent on a pre-V5 / video-off course. */}
          {safeIndex === 0 && apiBaseUrl && course.videos && (
            <OverviewSection videos={course.videos} apiBaseUrl={apiBaseUrl} courseId={course.id} />
          )}
          {/* Scope-realism band (CQ Phase 3.1): the effort/does-n't framing, shown once at entry. */}
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
              {annotations.length > 0 && (
                <button
                  ref={railToggleRef}
                  type="button"
                  className={styles.railToggle}
                  aria-expanded={railOpen}
                  aria-controls="annotation-rail"
                  aria-label={`Sources & checks, ${annotations.length}`}
                  onClick={() => setRailOpen((open) => !open)}
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

          {/* The lesson's headline artifact (explainer-video V0): generate → watch, in place. */}
          {apiBaseUrl && (
            <LessonVideoHero
              apiBaseUrl={apiBaseUrl}
              courseId={active.id}
              lessonId={current.lesson.id}
              video={current.lesson.video ?? null}
            />
          )}

          {current.objectives.length > 0 && (
            <LessonObjectives
              objectives={current.objectives}
              understoodIndexes={
                progress
                  ? new Set(
                      progress.objectives
                        .filter((mark) => mark.moduleId === current.moduleId)
                        .map((mark) => mark.objectiveIndex),
                    )
                  : undefined
              }
            />
          )}

          {/* The arc opens by stating what the lesson assumes the learner already brings (P7.3);
              omitted for courses built before P7.3 (empty expects). */}
          {expects.length > 0 && (
            <LessonScaffold
              title="What this lesson expects"
              cue="What to be comfortable with before you start"
              items={expects}
            />
          )}

          {PHASES.map(({ key, label, cue }) => {
            const segment = current.lesson.segments[key];
            const phaseHighlighted =
              activeAnnotation?.phaseKey === key && activeAnnotation.matchedSentence === null;
            return (
              <section
                key={key}
                className={`${styles.phase} ${phaseHighlighted ? styles.phaseActive : ""}`}
                aria-label={label}
                data-phase={key}
                data-active={phaseHighlighted ? "true" : undefined}
              >
                <div className={styles.phaseHead}>
                  <p className="eyebrow">{cue}</p>
                  <h3 className={styles.phaseLabel}>{label}</h3>
                </div>
                <LessonProse
                  prose={segment.prose}
                  marks={marksByPhase.get(key) ?? []}
                  activeClaimId={activeClaimId}
                  onSelectClaim={selectClaim}
                />
                {/* Index keys are safe: a segment's visuals are a fixed, non-reordered array. */}
                {segment.visuals.map((visual, visualIndex) => (
                  <VisualRenderer key={visualIndex} visual={visual} />
                ))}
                {/* Curated external aids for this phase (P7.4); guarded with ?? [] so a course built
                    before P7.4 (no resources) renders nothing here. */}
                {(segment.resources ?? []).length > 0 && (
                  <LessonResources resources={segment.resources} />
                )}
              </section>
            );
          })}

          {/* The arc closes with a self-check the learner runs to confirm the competency (P7.3). */}
          {selfCheck.length > 0 && (
            <LessonScaffold
              title="Self-check"
              cue="Confirm you’ve got it before moving on"
              items={selfCheck}
            />
          )}

          {current.assessment.length > 0 && <LessonAssessment items={current.assessment} />}

          <footer className={styles.nav}>
            {onRegenerate ? (
              <Button onClick={regenerate} disabled={pending} aria-busy={pending}>
                {pending ? "Regenerating…" : "Regenerate lesson"}
              </Button>
            ) : (
              <span />
            )}
            <div className={styles.navButtons}>
              <Button
                aria-label="Previous lesson"
                disabled={safeIndex === 0}
                onClick={() => setActiveIndex((index) => Math.max(0, index - 1))}
              >
                Prev
              </Button>
              <Button
                aria-label="Next lesson"
                disabled={safeIndex >= total - 1}
                onClick={() => setActiveIndex((index) => Math.min(total - 1, index + 1))}
              >
                Next
              </Button>
            </div>
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
