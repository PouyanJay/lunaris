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
import { LessonObjectives } from "./LessonObjectives";
import { ReaderOutline, type OutlineGroup } from "./ReaderOutline";
import styles from "./CourseReader.module.css";

/** Merrill's First Principles phases, in teaching order, with their reader labels and a plain-language
 *  cue so a learner understands what each phase is for. */
const PHASES: { key: keyof MerrillSegments; label: string; cue: string }[] = [
  { key: "activate", label: "Activate", cue: "Connect to what you already know" },
  { key: "demonstrate", label: "Demonstrate", cue: "See the idea worked through" },
  { key: "apply", label: "Apply", cue: "Practise it yourself" },
  { key: "integrate", label: "Integrate", cue: "Make it your own" },
];

/** A lesson in course-wide reading order, carrying its owning module's title for context (lessons
 *  have no title of their own in the schema) and a display label. Module-level objectives and
 *  assessment are attached to the module's first / last lesson respectively, so each shows once. */
interface ReaderLesson {
  lesson: Lesson;
  moduleTitle: string;
  label: string;
  objectives: Objective[];
  assessment: AssessmentItem[];
}

/** Flatten the course into an ordered lesson list and the matching outline groups in one pass.
 *  Modules with no authored lessons are skipped — they have nothing to read. */
function buildReaderModel(course: Course): { lessons: ReaderLesson[]; groups: OutlineGroup[] } {
  const lessons: ReaderLesson[] = [];
  const groups: OutlineGroup[] = [];
  for (const module of course.modules) {
    if (module.lessons.length === 0) continue;
    const items: OutlineGroup["items"] = [];
    const last = module.lessons.length - 1;
    module.lessons.forEach((lesson, lessonIndex) => {
      const index = lessons.length;
      const label = `Lesson ${index + 1}`;
      lessons.push({
        lesson,
        moduleTitle: module.title,
        label,
        objectives: lessonIndex === 0 ? module.objectives : [],
        assessment: lessonIndex === last ? module.assessment.items : [],
      });
      items.push({ index, label });
    });
    groups.push({ moduleId: module.id, moduleTitle: module.title, items });
  }
  return { lessons, groups };
}

interface CourseReaderProps {
  course: Course;
}

/** The lesson reader (Learn view): a persistent course outline beside a single focused lesson, with
 *  Prev/Next navigation and a position indicator. Renders the focused lesson's four Merrill phases.
 *  Claims/provenance and the branded visual renderer land in later slices. */
export function CourseReader({ course }: CourseReaderProps) {
  const { lessons, groups } = useMemo(() => buildReaderModel(course), [course]);
  const [activeIndex, setActiveIndex] = useState(0);
  const paneRef = useRef<HTMLDivElement>(null);

  // Reset to the first lesson when a different course is opened.
  useEffect(() => setActiveIndex(0), [course]);
  // Return to the top of the reading pane whenever the focused lesson changes. (scrollTo is
  // optional-chained — jsdom doesn't implement it, and a missing scroll is harmless.)
  useEffect(() => paneRef.current?.scrollTo?.({ top: 0 }), [activeIndex]);

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

  return (
    <div className={styles.reader}>
      <ReaderOutline groups={groups} activeIndex={safeIndex} onSelect={setActiveIndex} />
      <div className={styles.pane} ref={paneRef} role="region" aria-label="Lesson reader" tabIndex={0}>
        <article className={styles.page}>
          <header className={styles.lessonHead}>
            <div className={styles.lessonHeading}>
              <p className="eyebrow">{current.moduleTitle}</p>
              <h2 className={styles.lessonTitle}>{current.label}</h2>
            </div>
            <p className={`${styles.progress} mono`}>
              Lesson {safeIndex + 1} of {total}
            </p>
          </header>

          {current.objectives.length > 0 && <LessonObjectives objectives={current.objectives} />}

          {PHASES.map(({ key, label, cue }) => (
            <section key={key} className={styles.phase} aria-label={label}>
              <div className={styles.phaseHead}>
                <h3 className={styles.phaseLabel}>{label}</h3>
                <p className={styles.phaseCue}>{cue}</p>
              </div>
              <p className={styles.prose}>{current.lesson.segments[key].prose}</p>
            </section>
          ))}

          {current.assessment.length > 0 && <LessonAssessment items={current.assessment} />}

          <footer className={styles.nav}>
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
          </footer>
        </article>
      </div>
    </div>
  );
}
