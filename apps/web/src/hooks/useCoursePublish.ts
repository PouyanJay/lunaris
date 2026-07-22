import { useCallback, useState } from "react";

import { publishCourse } from "../lib/loadCourse";
import type { Course } from "../types/course";

export interface CoursePublish {
  isPublishing: boolean;
  /** A human message when the publish failed (e.g. 409 still building); the drawer stays open. */
  error: string | null;
  /** Approve + publish a course by id; on success runs `onPublished` with the updated course. */
  publish: (courseId: string) => Promise<void>;
  /** Clear a stale error (e.g. when the drawer closes). */
  reset: () => void;
}

/** The approve-and-publish workflow for a review-held course (course-review-publish). On success it
 *  hands the now-published course to `onPublished` (e.g. reload the course view); on failure the
 *  message is retained so the drawer can show a recoverable error. Owner override — the server flips
 *  status without re-running the gates. */
export function useCoursePublish(
  apiBaseUrl: string,
  onPublished?: (course: Course) => void,
): CoursePublish {
  const [isPublishing, setIsPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const publish = useCallback(
    async (courseId: string) => {
      setIsPublishing(true);
      setError(null);
      try {
        const course = await publishCourse(apiBaseUrl, courseId);
        onPublished?.(course);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Couldn’t publish this course.");
      } finally {
        setIsPublishing(false);
      }
    },
    [apiBaseUrl, onPublished],
  );

  const reset = useCallback(() => setError(null), []);

  return { isPublishing, error, publish, reset };
}
