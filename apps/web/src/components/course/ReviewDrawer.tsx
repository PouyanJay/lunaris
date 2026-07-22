import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

import { FOCUSABLE_SELECTOR } from "../../lib/focusable";
import type { Course, ReviewGate, ReviewGateStatus } from "../../types/course";
import { Button } from "../primitives/Button";
import styles from "./ReviewDrawer.module.css";

interface ReviewDrawerProps {
  open: boolean;
  course: Course;
  /** Approve is in flight — buttons disable, primary shows a pending label. */
  pending: boolean;
  /** A human message when the publish failed; the drawer stays open carrying it. */
  errorMessage: string | null;
  /** Approve & publish the course. */
  onApprove: () => void;
  /** Dismiss the drawer without publishing ("Keep in review", Esc, or scrim). */
  onClose: () => void;
}

/** The chip wording + tone class per gate verdict. */
const GATE_META: Record<ReviewGateStatus, { chip: string; className: string }> = {
  passed: { chip: "Passed", className: styles.gatePass! },
  warning: { chip: "Needs work", className: styles.gateWarn! },
  caveat: { chip: "Caveat", className: styles.gateCaution! },
};

function GateRow({ gate }: { gate: ReviewGate }) {
  const meta = GATE_META[gate.status];
  return (
    <li className={`${styles.gate} ${meta.className}`}>
      <div className={styles.gateHead}>
        <span className={styles.gateName}>{gate.label}</span>
        <span className={styles.gateChip}>{meta.chip}</span>
      </div>
      <p className={styles.gateDetail}>{gate.detail}</p>
    </li>
  );
}

/** The review-and-publish drawer (course-review-publish, Option D): a right-hand slide-over, over a
 *  scrim, listing the publish gates that held a course in review. "Approve & publish" flips it to
 *  published (owner override — the gates don't block); "Keep in review" just closes. Focus-trapped,
 *  Esc / scrim to close, focus restored to the trigger on close, tokens only. */
export function ReviewDrawer({
  open,
  course,
  pending,
  errorMessage,
  onApprove,
  onClose,
}: ReviewDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const descId = useId();
  const gates = course.reviewGates ?? [];

  // Move focus into the drawer on open (the close button — never the destructive-adjacent primary,
  // so an accidental Enter can't publish); restore it to the trigger on close.
  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => restoreRef.current?.focus();
  }, [open]);

  // Esc closes; Tab is trapped within the drawer (capture phase so it wins over page shortcuts).
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || drawerRef.current === null) return;
      const focusable = Array.from(
        drawerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
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
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !pending) onClose();
      }}
    >
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className={styles.drawer}
      >
        <header className={styles.head}>
          <h2 id={titleId} className={styles.title}>
            Review &amp; publish
          </h2>
          <button
            ref={closeRef}
            type="button"
            className={styles.close}
            onClick={onClose}
            disabled={pending}
            aria-label="Close review panel"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className={styles.body}>
          <p className={styles.topic}>{course.topic}</p>
          <p id={descId} className={styles.lede}>
            {gates.length > 0
              ? "You’re the owner — you can publish anyway. Every caveat below stays visible to learners."
              : "No blocking gates were recorded. You can publish now; any caveats stay visible to learners."}
          </p>

          {gates.length > 0 && (
            <ul className={styles.gates}>
              {gates.map((gate) => (
                <GateRow key={gate.key} gate={gate} />
              ))}
            </ul>
          )}

          {errorMessage !== null && (
            <p className={styles.error} role="alert">
              {errorMessage}
            </p>
          )}
        </div>

        <footer className={styles.actions}>
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Keep in review
          </Button>
          <Button variant="accent" onClick={onApprove} disabled={pending} aria-busy={pending}>
            {pending ? "Publishing…" : "Approve & publish"}
          </Button>
        </footer>
      </aside>
    </div>,
    document.body,
  );
}
