import { CanvasNotice } from "../states/CanvasNotice";
import { ErrorState } from "../states/ErrorState";
import { useBookmarks } from "../../hooks/useBookmarks";
import type { Bookmark } from "../../lib/bookmarks";
import styles from "./BookmarksScreen.module.css";

interface BookmarksScreenProps {
  apiBaseUrl: string;
  /** The empty state's next step — a fresh account has nothing saved but somewhere to go. */
  onBrowseCourses: () => void;
}

function rowLine(bookmark: Bookmark): string {
  const label = bookmark.title ?? bookmark.targetId;
  return bookmark.courseTitle ? `${label} — ${bookmark.courseTitle}` : label;
}

/** The Bookmarks canvas: everything the learner saved to return to, from real rows only.
 *  Walking-skeleton form — the designed pills/rows/chips/cards land next. */
export function BookmarksScreen({ apiBaseUrl, onBrowseCourses }: BookmarksScreenProps) {
  const { state, reload } = useBookmarks(apiBaseUrl);

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
      <ul className={styles.plainList}>
        {state.bookmarks.map((bookmark) => (
          <li
            key={`${bookmark.kind}-${bookmark.courseId}-${bookmark.targetId}`}
            className={styles.plainRow}
          >
            {rowLine(bookmark)}
          </li>
        ))}
      </ul>
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
