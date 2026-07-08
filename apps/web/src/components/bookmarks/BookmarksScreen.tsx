import { useState } from "react";

import { CanvasNotice } from "../states/CanvasNotice";
import { FilterPills, type FilterPillOption } from "../primitives/FilterPills";
import { ErrorState } from "../states/ErrorState";
import { SourceTrust } from "../primitives/SourceTrust";
import { relativeTime } from "../../lib/relativeTime";
import { useBookmarksApi } from "./BookmarksContext";
import { BookmarkToggle } from "./BookmarkToggle";
import type { Bookmark, BookmarkKind } from "../../lib/bookmarks";
import type { TrustTier } from "../../types/course";
import styles from "./BookmarksScreen.module.css";

type Filter = "all" | BookmarkKind;

const FILTERS: FilterPillOption<Filter>[] = [
  { value: "all", label: "All" },
  { value: "lesson", label: "Lessons" },
  { value: "concept", label: "Concepts" },
  { value: "source", label: "Sources" },
];

const KIND_LABEL: Record<BookmarkKind, string> = {
  lesson: "lessons",
  concept: "concepts",
  source: "sources",
};

interface BookmarksScreenProps {
  /** The empty state's next step — a fresh account has nothing saved but somewhere to go. */
  onBrowseCourses: () => void;
  /** Deep links back to each save's origin. */
  onOpenLesson: (courseId: string, lessonId: string) => void;
  onOpenConcept: (courseId: string, kcId: string) => void;
  /** Fallback when a save carries no lesson pointer (e.g. a rebuilt course). */
  onOpenCourse: (courseId: string) => void;
}

function savedMeta(bookmark: Bookmark): string {
  const saved = `saved ${relativeTime(bookmark.savedAt)}`;
  return bookmark.courseTitle ? `${bookmark.courseTitle} · ${saved}` : saved;
}

function LessonRow({
  bookmark,
  onOpen,
}: {
  bookmark: Bookmark;
  onOpen: (courseId: string, lessonId: string) => void;
}) {
  const label = bookmark.title ?? "Saved lesson";
  return (
    <li className={styles.lessonRow}>
      <BookmarkToggle draft={bookmark} subject={label} />
      <button
        type="button"
        className={styles.lessonBody}
        aria-label={`Open ${label}`}
        onClick={() => onOpen(bookmark.courseId, bookmark.lessonId ?? bookmark.targetId)}
      >
        <span className={styles.lessonTitle}>{label}</span>
        <span className={`${styles.rowMeta} mono`}>{savedMeta(bookmark)}</span>
      </button>
      <svg
        className={styles.chevron}
        viewBox="0 0 24 24"
        width="15"
        height="15"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M9 18l6-6-6-6" />
      </svg>
    </li>
  );
}

function ConceptChip({
  bookmark,
  onOpen,
}: {
  bookmark: Bookmark;
  onOpen: (courseId: string, kcId: string) => void;
}) {
  const label = bookmark.title ?? "Saved concept";
  return (
    <li className={styles.conceptChip}>
      <button
        type="button"
        className={styles.conceptBody}
        aria-label={`Open ${label} on the map`}
        onClick={() => onOpen(bookmark.courseId, bookmark.targetId)}
      >
        <span
          className={styles.tierSwatch}
          style={
            bookmark.conceptTier ? { background: `var(--tier-${bookmark.conceptTier})` } : undefined
          }
          aria-hidden="true"
        />
        <span className={styles.conceptText}>
          <span className={styles.conceptTitle}>{label}</span>
          {bookmark.courseTitle && (
            <span className={`${styles.rowMeta} mono`}>{bookmark.courseTitle}</span>
          )}
        </span>
      </button>
      <BookmarkToggle draft={bookmark} subject={label} />
    </li>
  );
}

function SourceCard({
  bookmark,
  onOpenLesson,
  onOpenCourse,
}: {
  bookmark: Bookmark;
  onOpenLesson: (courseId: string, lessonId: string) => void;
  onOpenCourse: (courseId: string) => void;
}) {
  const name = bookmark.title ?? "Saved source";
  const openLabel = bookmark.lessonId
    ? `Open the lesson citing ${name}`
    : `Open ${bookmark.courseTitle ?? "the course"}`;
  return (
    <li className={styles.sourceCard}>
      {bookmark.snippet && <p className={styles.sourceClaim}>{bookmark.snippet}</p>}
      <div className={styles.sourceFooter}>
        <button
          type="button"
          className={styles.sourceOrigin}
          aria-label={openLabel}
          onClick={() =>
            bookmark.lessonId
              ? onOpenLesson(bookmark.courseId, bookmark.lessonId)
              : onOpenCourse(bookmark.courseId)
          }
        >
          {name}
          {bookmark.courseTitle ? ` · ${bookmark.courseTitle}` : ""}
        </button>
        <div className={styles.sourceActions}>
          {bookmark.trustTier && (
            <SourceTrust
              tier={bookmark.trustTier as TrustTier}
              credibility={bookmark.credibility ?? null}
            />
          )}
          <BookmarkToggle draft={bookmark} subject={name} />
        </div>
      </div>
    </li>
  );
}

/** The loaded canvas: the filter pills over the per-kind sections. A filtered-empty kind says
 *  so; under "All", an empty kind simply doesn't render. */
function LoadedBookmarks({
  bookmarks,
  filter,
  onFilter,
  onOpenLesson,
  onOpenConcept,
  onOpenCourse,
}: {
  bookmarks: Bookmark[];
  filter: Filter;
  onFilter: (filter: Filter) => void;
} & Pick<BookmarksScreenProps, "onOpenLesson" | "onOpenConcept" | "onOpenCourse">) {
  const ofKind = (kind: BookmarkKind) => bookmarks.filter((bookmark) => bookmark.kind === kind);
  const visible = (kind: BookmarkKind) => filter === "all" || filter === kind;
  const section = (kind: BookmarkKind, items: Bookmark[], children: React.ReactNode) => {
    if (!visible(kind)) return null;
    if (items.length === 0) {
      return filter === kind ? (
        <p key={kind} className={styles.filteredEmpty}>
          No saved {KIND_LABEL[kind]} yet.
        </p>
      ) : null;
    }
    return children;
  };

  const lessons = ofKind("lesson");
  const concepts = ofKind("concept");
  const sources = ofKind("source");
  return (
    <>
      <div className={styles.pillsRow}>
        <FilterPills
          options={FILTERS}
          value={filter}
          onChange={onFilter}
          label="Filter bookmarks"
        />
      </div>
      {section(
        "lesson",
        lessons,
        <section key="lesson" className={styles.section} aria-label="Lessons">
          <h2 className={styles.sectionLabel}>Lessons</h2>
          <ul className={styles.lessonList}>
            {lessons.map((bookmark) => (
              <LessonRow key={bookmark.targetId} bookmark={bookmark} onOpen={onOpenLesson} />
            ))}
          </ul>
        </section>,
      )}
      {section(
        "concept",
        concepts,
        <section key="concept" className={styles.section} aria-label="Concepts">
          <h2 className={styles.sectionLabel}>Concepts</h2>
          <ul className={styles.conceptGrid}>
            {concepts.map((bookmark) => (
              <ConceptChip key={bookmark.targetId} bookmark={bookmark} onOpen={onOpenConcept} />
            ))}
          </ul>
        </section>,
      )}
      {section(
        "source",
        sources,
        <section key="source" className={styles.section} aria-label="Sources">
          <h2 className={styles.sectionLabel}>Sources</h2>
          <ul className={styles.sourceList}>
            {sources.map((bookmark) => (
              <SourceCard
                key={bookmark.targetId}
                bookmark={bookmark}
                onOpenLesson={onOpenLesson}
                onOpenCourse={onOpenCourse}
              />
            ))}
          </ul>
        </section>,
      )}
    </>
  );
}

/** The Bookmarks canvas per the Unified design: filter pills over three hairline sections —
 *  lesson rows, concept chips (tier swatch), source cards (claim + trust grade) — each
 *  deep-linking to its origin. Reads the SAME provider instance the save affordances write. */
export function BookmarksScreen({
  onBrowseCourses,
  onOpenLesson,
  onOpenConcept,
  onOpenCourse,
}: BookmarksScreenProps) {
  const { state, reload } = useBookmarksApi();
  const [filter, setFilter] = useState<Filter>("all");

  const body = (() => {
    if (state.status === "loading") {
      return (
        <div className={styles.skeleton} aria-busy="true" aria-label="Loading bookmarks">
          <div className={styles.skeletonPills}>
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className={styles.skeletonPill} />
            ))}
          </div>
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className={styles.skeletonRow} />
          ))}
        </div>
      );
    }
    if (state.status === "error") {
      return <ErrorState eyebrow="Bookmarks" message={state.message} onRetry={reload} />;
    }
    if (state.bookmarks.length === 0) {
      return (
        <CanvasNotice
          eyebrow="Nothing saved"
          title="No bookmarks yet"
          body="Save a lesson from the reader, a concept from the map, or a source from its claim — everything you keep lands here."
          actionLabel="Browse my courses"
          onAction={onBrowseCourses}
        />
      );
    }

    return (
      <LoadedBookmarks
        bookmarks={state.bookmarks}
        filter={filter}
        onFilter={setFilter}
        onOpenLesson={onOpenLesson}
        onOpenConcept={onOpenConcept}
        onOpenCourse={onOpenCourse}
      />
    );
  })();

  return (
    <div className={styles.canvas}>
      <div className={styles.inner}>
        <p className={styles.subline}>Lessons, concepts, and sources you saved to return to.</p>
        {body}
      </div>
    </div>
  );
}
