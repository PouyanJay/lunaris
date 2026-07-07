import type { Course, Lesson, Module } from "../types/course";

/** One lesson in course-wide reading order with its owning module and position facts. */
export interface FlatLesson {
  lesson: Lesson;
  module: Module;
  /** 0-based position across the whole course. */
  index: number;
  /** Module metadata (objectives, assessment) rides on these boundaries by convention. */
  isFirstInModule: boolean;
  isLastInModule: boolean;
}

/** Flatten a course into reading order — THE ordering every lesson surface shares (the reader's
 *  outline, the Overview's rows). Modules with no authored lessons are skipped. The
 *  "module metadata rides on the module's first/last lesson" convention is expressed here once
 *  via the boundary flags. */
export function flattenLessons(course: Course): FlatLesson[] {
  const flat: FlatLesson[] = [];
  for (const module of course.modules) {
    module.lessons.forEach((lesson, lessonIndex) => {
      flat.push({
        lesson,
        module,
        index: flat.length,
        isFirstInModule: lessonIndex === 0,
        isLastInModule: lessonIndex === module.lessons.length - 1,
      });
    });
  }
  return flat;
}
