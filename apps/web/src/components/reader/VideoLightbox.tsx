import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { youTubeEmbed } from "./youtube";
import styles from "./VideoLightbox.module.css";

interface VideoLightboxProps {
  videoId: string;
  title: string;
  onClose: () => void;
}

const FOCUSABLE = 'button:not([disabled]), iframe, [href], [tabindex]:not([tabindex="-1"])';

/** A fullscreen modal that plays a YouTube video on a dimmed backdrop: focus-trapped, Esc / backdrop
 *  click to close, focus restored to the trigger on close (WCAG 2.2). The iframe is created only when
 *  this mounts (on the user's "full screen" click), so no third-party frame loads until then. */
export function VideoLightbox({ videoId, title, onClose }: VideoLightboxProps) {
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
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
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
            {title}
          </p>
          <button ref={closeRef} type="button" className={styles.close} onClick={onClose}>
            Close
          </button>
        </div>
        <div className={styles.frameWrap}>
          <iframe
            className={styles.frame}
            src={youTubeEmbed(videoId, { autoplay: true })}
            title={title}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>
      </div>
    </div>,
    document.body,
  );
}
