import { useEffect, useRef, useState } from "react";
import { fetchCourseSummaries } from "../../lib/library";
import { prepareCourseGraph, type ConceptGraph } from "../../lib/liveGraph";

interface CourseChoice {
  courseId: string;
  title: string;
}
type LibraryState =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; courses: CourseChoice[] };
/** Owns explicit preparation for one source-entry mount; source changes cancel stale work. */
export function useCoursePreparation(
  apiBaseUrl: string,
  initialCourseId: string,
  onPrepared: (graph: ConceptGraph) => void,
) {
  const [library, setLibrary] = useState<LibraryState>({ status: "loading" });
  const [libraryAttempt, setLibraryAttempt] = useState(0);
  const [courseId, setCourseId] = useState(initialCourseId);
  const [graph, setGraph] = useState<ConceptGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setLibrary({ status: "loading" });
    fetchCourseSummaries(apiBaseUrl, controller.signal)
      .then((courses) => {
        if (controller.signal.aborted) return;
        if (
          !Array.isArray(courses) ||
          courses.some(
            (course) =>
              !course || typeof course.id !== "string" || typeof course.topic !== "string",
          )
        )
          throw new Error("Invalid course library");
        setLibrary({
          status: "ready",
          courses: courses
            .filter((course) => course.courseStatus === "published")
            .map((course) => ({ courseId: course.id, title: course.topic })),
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) setLibrary({ status: "failed" });
      });
    return () => controller.abort();
  }, [apiBaseUrl, libraryAttempt]);
  useEffect(() => () => request.current?.abort(), []);

  function select(id: string) {
    request.current?.abort();
    request.current = null;
    setCourseId(id);
    setGraph(null);
    setError(null);
    setBusy(false);
  }
  async function prepare(id: string) {
    if (request.current && !request.current.signal.aborted) return;
    const course =
      library.status === "ready" ? library.courses.find((item) => item.courseId === id) : null;
    if (!course) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError(null);
    setGraph(null);
    try {
      const result = await prepareCourseGraph(
        apiBaseUrl,
        course.courseId,
        course.title,
        controller.signal,
      );
      if (controller.signal.aborted || request.current !== controller) return;
      setGraph(result);
      onPrepared(result);
    } catch {
      if (!controller.signal.aborted)
        setError(
          "Could not prepare this course. Check that it is still published, then try again.",
        );
    } finally {
      if (request.current === controller) {
        request.current = null;
        setBusy(false);
      }
    }
  }
  return {
    library,
    courseId,
    graph,
    error,
    busy,
    select,
    prepare,
    reload: () => setLibraryAttempt((value) => value + 1),
  };
}
