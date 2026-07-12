import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { FOCUSABLE_SELECTOR } from "../../lib/focusable";
import styles from "./CoverLightbox.module.css";

interface CoverLightboxProps {
  /** The signed URL of the full-size cover (2048x1152). */
  imageUrl: string;
  /** The course topic — names the dialog and captions the image. */
  topic: string;
  onClose: () => void;
}

/** A fullscreen view of a course cover on a dimmed backdrop: focus-trapped, Esc / backdrop click to
 *  close, focus restored to the trigger on close (WCAG 2.2). Covers are composed 16:9 artworks that
 *  carry their own typography, so the card thumbnails can't do them justice — this is how a reader
 *  actually looks at one. Mirrors ``VideoLightbox``'s modal contract so both overlays behave
 *  identically. */
export function CoverLightbox({ imageUrl, topic, onClose }: CoverLightboxProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const titleId = useId();

  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => restoreRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || dialogRef.current === null) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
      );
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [onClose]);

  return createPortal(
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={styles.dialog}
      >
        <div className={styles.bar}>
          <p id={titleId} className={styles.title}>
            {topic}
          </p>
          <button ref={closeRef} type="button" className={styles.close} onClick={onClose}>
            Close
          </button>
        </div>
        {/* The cover is decorative next to its own title, but at full size it IS the content — so
            it takes the course topic as its alt text rather than an empty one. */}
        <img className={styles.image} src={imageUrl} alt={topic} />
      </div>
    </div>,
    document.body,
  );
}
