import { useEffect, useMemo, useRef, useState } from "react";

import type {
  AssessmentItem,
  Course,
  Lesson,
  MerrillSegments,
  Objective,
} from "../../types/course";
import { Button } from "../primitives/Button";
import { LessonAssessment } from "./LessonAssessment";
import { LessonClaims } from "./LessonClaims";
import { LessonObjectives } from "./LessonObjectives";
import { LessonResources } from "./LessonResources";
import { LessonScaffold } from "./LessonScaffold";
import { ReaderOutline, type OutlineGroup } from "./ReaderOutline";
import { VisualRenderer } from "./visuals/VisualRenderer";
import styles from "./CourseReader.module.css";

/** The teaching phases (Merrill's First Principles, in order), relabelled to the lesson ARC the
 *  course is designed around (P7.3) so the learner reads a coherent rhythm — strategies → worked
 *  example → practice → transfer — bracketed by the "expects" and "self-check" bookends. */
const PHASES: { key: keyof MerrillSegments; label: string; cue: string }[] = [
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
}

/** The lesson reader (Learn view): a persistent course outline beside a single focused lesson, with
 *  Prev/Next navigation, a position indicator, and a per-lesson agent regenerate action. Renders the
 *  focused lesson as its arc (P7.3) — the competency it builds toward, the "what this lesson expects"
 *  bookend, the relabelled teaching phases, objectives, claims/provenance, branded visuals, and the
 *  closing self-check. */
export function CourseReader({ course, focusRequest, onRegenerate }: CourseReaderProps) {
  // A successful regenerate swaps in the updated course locally until a different course is opened.
  const [regeneratedCourse, setRegeneratedCourse] = useState<Course | null>(null);
  const active = regeneratedCourse ?? course;
  const { lessons, groups, kcToLessonIndex } = useMemo(() => buildReaderModel(active), [active]);
  const citations = useMemo(
    () => new Map(active.provenance.map((citation) => [citation.id, citation])),
    [active.provenance],
  );
  const [activeIndex, setActiveIndex] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const paneRef = useRef<HTMLDivElement>(null);
  const handledFocusSeq = useRef(0);

  // Reset to the first lesson and drop any regenerate override when a different course is opened.
  useEffect(() => {
    setActiveIndex(0);
    setRegeneratedCourse(null);
  }, [course]);
  // On a lesson change: return to the top of the reading pane (scrollTo is optional-chained — jsdom
  // doesn't implement it) and clear any stale regenerate error from the previous lesson.
  useEffect(() => {
    paneRef.current?.scrollTo?.({ top: 0 });
    setError(null);
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
    <div className={styles.reader}>
      <ReaderOutline groups={groups} activeIndex={safeIndex} onSelect={setActiveIndex} />
      <div
        className={styles.pane}
        ref={paneRef}
        role="region"
        aria-label="Lesson reader"
        tabIndex={0}
      >
        <article className={styles.page}>
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
            <p className={`${styles.progress} mono`}>
              Lesson {safeIndex + 1} of {total}
            </p>
          </header>

          {current.objectives.length > 0 && <LessonObjectives objectives={current.objectives} />}

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
            return (
              <section key={key} className={styles.phase} aria-label={label}>
                <div className={styles.phaseHead}>
                  <h3 className={styles.phaseLabel}>{label}</h3>
                  <p className={styles.phaseCue}>{cue}</p>
                </div>
                <p className={styles.prose}>{segment.prose}</p>
                {/* Index keys are safe: a segment's visuals are a fixed, non-reordered array. */}
                {segment.visuals.map((visual, visualIndex) => (
                  <VisualRenderer key={visualIndex} visual={visual} />
                ))}
                {segment.claims.length > 0 && (
                  <LessonClaims claims={segment.claims} citations={citations} />
                )}
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
    </div>
  );
}
