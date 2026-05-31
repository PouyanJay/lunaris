import type { Course, Lesson, MerrillSegments } from "../../types/course";
import styles from "./CourseReader.module.css";

/** Merrill's First Principles phases, in teaching order, with their reader labels. */
const PHASES: { key: keyof MerrillSegments; label: string }[] = [
  { key: "activate", label: "Activate" },
  { key: "demonstrate", label: "Demonstrate" },
  { key: "apply", label: "Apply" },
  { key: "integrate", label: "Integrate" },
];

// Walking skeleton: the reader always shows the first lesson. Real per-module lesson numbering and
// navigation arrive in T1, which replaces this with a derived label.
const LESSON_LABEL = "Lesson 1";

/** The first authored lesson in topological module order, plus the module that owns it. Lessons
 *  carry no title in the schema, so the reader contextualises them by their module. */
function firstLesson(course: Course): { moduleTitle: string; lesson: Lesson } | null {
  for (const module of course.modules) {
    const lesson = module.lessons[0];
    if (lesson) return { moduleTitle: module.title, lesson };
  }
  return null;
}

interface CourseReaderProps {
  course: Course;
}

/** The lesson reader (Learn view). Walking skeleton: renders the first authored lesson's four
 *  Merrill phases. The course outline (TOC), lesson navigation, claims/provenance, and the branded
 *  visual renderer land in later slices. */
export function CourseReader({ course }: CourseReaderProps) {
  const current = firstLesson(course);

  if (!current) {
    return (
      <div className={styles.empty} role="status">
        No lessons yet — this course hasn’t been authored.
      </div>
    );
  }

  const { moduleTitle, lesson } = current;
  return (
    <section className={styles.reader} aria-label="Lesson reader" tabIndex={0}>
      <article className={styles.page}>
        <header className={styles.lessonHead}>
          <p className="eyebrow">{moduleTitle}</p>
          <h2 className={styles.lessonTitle}>{LESSON_LABEL}</h2>
        </header>
        {PHASES.map(({ key, label }) => (
          <section key={key} className={styles.phase} aria-label={label}>
            <h3 className={styles.phaseLabel}>{label}</h3>
            <p className={styles.prose}>{lesson.segments[key].prose}</p>
          </section>
        ))}
      </article>
    </section>
  );
}
