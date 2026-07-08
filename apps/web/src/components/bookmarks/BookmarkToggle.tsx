import { useBookmarksApi } from "./BookmarksContext";
import type { BookmarkDraft } from "../../lib/bookmarks";
import styles from "./BookmarkToggle.module.css";

interface BookmarkToggleProps {
  /** What a press saves — the natural key + display fields captured at this site. */
  draft: BookmarkDraft;
  /** Human name for the accessible label ("Bookmark <subject>" / "Remove bookmark: <subject>"). */
  subject: string;
  className?: string;
}

/** The save affordance: an icon toggle that fills accent when saved. Renders nothing where
 *  saving is impossible (no provider — offline), and stays disabled until membership is known
 *  (it never guesses saved-ness). */
export function BookmarkToggle({ draft, subject, className }: BookmarkToggleProps) {
  const { enabled, ready, isSaved, toggle } = useBookmarksApi();
  if (!enabled) return null;
  const saved = ready && isSaved(draft);
  return (
    <button
      type="button"
      className={`${styles.toggle} ${className ?? ""}`.trim()}
      aria-pressed={saved}
      aria-label={saved ? `Remove bookmark: ${subject}` : `Bookmark ${subject}`}
      title={saved ? "Remove bookmark" : "Bookmark"}
      disabled={!ready}
      data-saved={saved || undefined}
      onClick={() => toggle(draft)}
    >
      <svg
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill={saved ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M6 3h12v18l-6-4-6 4z" />
      </svg>
    </button>
  );
}
