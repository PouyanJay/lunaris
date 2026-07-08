import { flattenLessons } from "./flattenLessons";
import type { Course, CourseSummary } from "../types/course";

/** One openable thing the palette can land on. */
export interface SearchEntry {
  kind: "course" | "lesson" | "concept";
  courseId: string;
  courseTitle: string;
  /** courseId | lessonId | kcId — what the deep link needs. */
  targetId: string;
  /** What the palette row shows (topic / "Lesson N · Module" / KC label). */
  label: string;
}

export interface SearchResults {
  courses: SearchEntry[];
  lessons: SearchEntry[];
  concepts: SearchEntry[];
}

const GROUP_LIMIT = 5;

/** A course row, available immediately from the library summaries. */
export function courseEntry(summary: CourseSummary): SearchEntry {
  return {
    kind: "course",
    courseId: summary.id,
    courseTitle: summary.topic,
    targetId: summary.id,
    label: summary.topic,
  };
}

/** A course's lesson + concept rows — needs the full payload (lessons carry no titles; the label
 *  is the reader's own "Lesson N · Module" numbering; concepts search over the KC labels). */
export function indexCourse(course: Course): SearchEntry[] {
  const lessons = flattenLessons(course).map<SearchEntry>(({ lesson, module, index }) => ({
    kind: "lesson",
    courseId: course.id,
    courseTitle: course.topic,
    targetId: lesson.id,
    label: `Lesson ${index + 1} · ${module.title}`,
  }));
  const concepts = course.graph.nodes.map<SearchEntry>((node) => ({
    kind: "concept",
    courseId: course.id,
    courseTitle: course.topic,
    targetId: node.id,
    label: node.label,
  }));
  return [...lessons, ...concepts];
}

/** Rank: prefix beats word-start beats substring; non-matches drop. Case-insensitive. */
function score(label: string, query: string): number | null {
  const haystack = label.toLowerCase();
  const position = haystack.indexOf(query);
  if (position < 0) return null;
  if (position === 0) return 0;
  if (/[\s·(-]/.test(haystack[position - 1] ?? "")) return 1;
  return 2;
}

/** Filter + rank the index for a query, capped per group (the palette shows the best few, never
 *  a scrolling dump). An empty query returns the first courses only — a browsable starting
 *  point, not a fake "everything matches". */
export function searchEntries(entries: SearchEntry[], query: string): SearchResults {
  const needle = query.trim().toLowerCase();
  const groups: SearchResults = { courses: [], lessons: [], concepts: [] };
  const bucket = (entry: SearchEntry) =>
    entry.kind === "course" ? groups.courses : entry.kind === "lesson" ? groups.lessons : groups.concepts;

  if (needle === "") {
    for (const entry of entries) {
      if (entry.kind === "course" && groups.courses.length < GROUP_LIMIT) {
        groups.courses.push(entry);
      }
    }
    return groups;
  }

  const scored = entries
    .map((entry) => ({ entry, rank: score(entry.label, needle) }))
    .filter((item): item is { entry: SearchEntry; rank: number } => item.rank !== null)
    .sort((a, b) => a.rank - b.rank || a.entry.label.localeCompare(b.entry.label));
  for (const { entry } of scored) {
    const group = bucket(entry);
    if (group.length < GROUP_LIMIT) group.push(entry);
  }
  return groups;
}
