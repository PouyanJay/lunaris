import { Button } from "../primitives/Button";
import type { Course } from "../../types/course";
import styles from "./CourseOverview.module.css";

interface CourseOverviewProps {
  course: Course;
  /** Open the reader (resuming where the learner left off is the reader's own job). */
  onContinue: () => void;
  /** Jump to the prerequisite-graph explorer. */
  onViewMap: () => void;
}

/** The course's landing tab: what this course is and where to go next. This shell carries the
 *  counts + the two CTAs; the designed hero and per-lesson rows land with the Overview content
 *  task. */
export function CourseOverview({ course, onContinue, onViewMap }: CourseOverviewProps) {
  const lessonTotal = course.modules.reduce((sum, module) => sum + module.lessons.length, 0);
  const conceptTotal = course.graph.nodes.length;
  return (
    <div className={styles.canvas}>
      <div className={styles.intro}>
        <p className={styles.counts}>
          {lessonTotal} {lessonTotal === 1 ? "lesson" : "lessons"} · {conceptTotal}{" "}
          {conceptTotal === 1 ? "concept" : "concepts"}
        </p>
        <div className={styles.actions}>
          <Button variant="accent" onClick={onContinue}>
            Continue learning
          </Button>
          <Button onClick={onViewMap}>View the map</Button>
        </div>
      </div>
    </div>
  );
}
