import { useEffect, useState } from "react";

import { useCoursePublish } from "../../hooks/useCoursePublish";
import { clearLibraryCache } from "../../hooks/libraryCache";
import type { Course, CourseStatus } from "../../types/course";
import { StatusDot, type StatusTone } from "../primitives/StatusDot";
import styles from "./CourseStatusMeta.module.css";
import { ReviewDrawer } from "./ReviewDrawer";

/** The build-lifecycle statuses shown live (a pulsing dot) while a course is being built. */
const RUNNING: CourseStatus[] = ["diagnosing", "mapping", "sequencing", "authoring", "verifying"];

function statusTone(status: CourseStatus): { tone: StatusTone; live: boolean } {
  if (status === "published") return { tone: "success", live: false };
  if (status === "review") return { tone: "warning", live: false };
  if (RUNNING.includes(status)) return { tone: "accent", live: true };
  return { tone: "neutral", live: false };
}

interface CourseStatusMetaProps {
  course: Course;
  /** Origin for the publish call; absent = offline, so the REVIEW pill stays non-interactive. */
  apiBaseUrl?: string | undefined;
  /** Called with the now-published course after a successful approve (e.g. reload the view). */
  onPublished?: ((course: Course) => void) | undefined;
}

/** The course canvas's status pill (REVIEW / PUBLISHED / building…). When the course is held in
 *  `review` and the live API is reachable, the REVIEW pill becomes the trigger for the
 *  review-and-publish drawer (course-review-publish): the owner sees the publish gates and can
 *  approve (→ published) or keep it in review. Offline or in any other status it's a plain,
 *  non-interactive status dot. */
export function CourseStatusMeta({ course, apiBaseUrl, onPublished }: CourseStatusMetaProps) {
  const { tone, live } = statusTone(course.status);
  const [open, setOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const { isPublishing, error, publish, reset } = useCoursePublish(
    apiBaseUrl ?? "",
    (published) => {
      // Publishing is verification-gated, so the flow is never optimistic: the drawer closes only
      // on the confirmed result. Announce it (the pill turns green PUBLISHED visually) and drop the
      // library cache so the grid's REVIEW badge clears on its next read.
      setOpen(false);
      setAnnouncement("Course published. The disclosed caveats stay visible to learners.");
      clearLibraryCache();
      onPublished?.(published);
    },
  );

  // Let the polite announcement clear itself so it isn't re-read on an unrelated re-render.
  useEffect(() => {
    if (!announcement) return;
    const timer = setTimeout(() => setAnnouncement(""), 5000);
    return () => clearTimeout(timer);
  }, [announcement]);

  // Always mounted, outside the status branch below, so the live region is registered before the
  // status flips and the success message is actually announced.
  const liveRegion = (
    <span className="sr-only" role="status" aria-live="polite">
      {announcement}
    </span>
  );
  const dot = <StatusDot label={course.status} tone={tone} live={live} />;
  if (course.status !== "review" || !apiBaseUrl) {
    return (
      <>
        {dot}
        {liveRegion}
      </>
    );
  }

  const close = () => {
    if (isPublishing) return;
    setOpen(false);
    reset();
  };
  return (
    <>
      <button
        type="button"
        className={styles.reviewTrigger}
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="Review and publish this course"
      >
        {dot}
      </button>
      <ReviewDrawer
        open={open}
        course={course}
        pending={isPublishing}
        errorMessage={error}
        onApprove={() => publish(course.id)}
        onClose={close}
      />
      {liveRegion}
    </>
  );
}
