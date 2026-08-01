import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Button } from "./primitives/Button";
import styles from "./TopicForm.module.css";

interface TopicFormProps {
  /** The controlled topic value (owned by the configurator so the rail can read it). */
  value: string;
  onChange: (value: string) => void;
  /** Build the course, or start the session, for the trimmed non-empty topic. */
  onSubmit: (topic: string) => void;
  /** The heading above the box, split so its operative verb can take the accent. The accent lives
   *  in this component's stylesheet, so callers pass the parts rather than pre-composed markup. */
  heading: { lead: string; accent: string; tail: string };
  /** What submitting promises. Studio compiles a course; Live opens a session. */
  submitLabel: string;
  /** The mode control, docked at the left of the box's action row. Absent when Lunaris is a single
   *  product, which is the parent's call to make, not this component's. */
  modeControl?: ReactNode;
  /** The build settings, docked as a bar inside the foot of the box. */
  options?: ReactNode;
  /** Accents the box's edge while Live is selected, so the whole field carries the mode. */
  live?: boolean;
}

const EXAMPLES = ["How binary search works", "How merge sort works", "How HTTPS works"];

/** The entry point: name a topic, and Lunaris either compiles a course or teaches you a session.
 *
 *  Composed as a recessed field rather than a bordered card, with every control docked inside it,
 *  so the box reads as somewhere to type rather than a panel to read. The settings bar sits in its
 *  foot; the mode control and the action share the row above it. */
export function TopicForm({
  value,
  onChange,
  onSubmit,
  heading,
  submitLabel,
  modeControl,
  options,
  live = false,
}: TopicFormProps) {
  const inputId = useId();
  const errorId = useId();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [error, setError] = useState(false);

  // Validate a non-empty topic, surfacing an inline error + refocus when empty, else submit.
  // Don't pre-disable submit (enterprise-ui forms rule) — submit, then guide the fix.
  function submit(topic: string) {
    const trimmed = topic.trim();
    if (!trimmed) {
      setError(true);
      inputRef.current?.focus();
      return;
    }
    setError(false);
    onSubmit(trimmed);
  }

  // A topic is one line of intent, so Enter submits and Shift+Enter breaks the line. That inverts
  // the usual textarea rule, and deliberately: this is a composer, and the field is multi-line only
  // so a long topic wraps instead of scrolling sideways.
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(value);
    }
  }

  return (
    <div className={styles.center}>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          submit(value);
        }}
      >
        <h2 className={styles.title}>
          {heading.lead}
          <span className={styles.titleAccent}>{heading.accent}</span>
          {heading.tail}
        </h2>

        {/* The field is self-evident from the heading and placeholder; keep the label for screen
            readers only (never placeholder-as-label) rather than showing a redundant "Topic". */}
        <label className="sr-only" htmlFor={inputId}>
          Topic
        </label>

        <div className={styles.box} data-live={live || undefined}>
          <textarea
            id={inputId}
            ref={inputRef}
            className={styles.input}
            rows={3}
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
              if (error) setError(false);
            }}
            onKeyDown={onKeyDown}
            placeholder="Name a topic. For example, how a hash map works…"
            aria-describedby={error ? errorId : undefined}
            aria-invalid={error || undefined}
            spellCheck={false}
            maxLength={200}
            autoFocus
          />

          <div className={styles.dock}>
            {modeControl}
            <span className={styles.spacer} />
            <Button type="submit" variant="accent" aria-label={submitLabel}>
              <span className={styles.submitLabel}>{submitLabel}</span>
              {/* On phones the label collapses to this go-arrow so the field gets the width. */}
              <svg
                className={styles.submitIcon}
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </Button>
          </div>

          {options}
        </div>

        {error && (
          <p id={errorId} className={styles.error} role="alert">
            Enter a topic to continue.
          </p>
        )}

        <div className={styles.examples}>
          <span className="eyebrow">Try</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className={styles.example}
              onClick={() => {
                onChange(example);
                submit(example);
              }}
            >
              {example}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
