import { useId, useRef, useState } from "react";

import { Button } from "./primitives/Button";
import styles from "./TopicForm.module.css";

interface TopicFormProps {
  /** The controlled topic value (owned by the configurator so the rail can read it). */
  value: string;
  onChange: (value: string) => void;
  /** Build the course for the trimmed, non-empty topic. */
  onSubmit: (topic: string) => void;
}

const EXAMPLES = ["How binary search works", "How merge sort works", "How HTTPS works"];

/** The idle entry point: name a topic and Lunaris builds a verified course for it. A real <form>
 *  (Enter submits), a labelled input, and example topics for a warm start. Personalization and build
 *  settings live in the always-visible course-setup rail beside this form, so the default path here
 *  is one click. */
export function TopicForm({ value, onChange, onSubmit }: TopicFormProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState(false);

  // Validate a non-empty topic, surfacing an inline error + refocus when empty, else build it.
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

  return (
    <div className={styles.center}>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          submit(value);
        }}
      >
        <span className="eyebrow">Build a course</span>
        <h2 className={styles.title}>
          What do you want to <span className={styles.titleAccent}>learn</span>?
        </h2>
        <p id={hintId} className={styles.hint}>
          Name a topic. Lunaris maps its prerequisites, writes the lessons, and verifies every claim
          &mdash; you&rsquo;ll watch each step run. Tailor it to you in the setup rail.
        </p>

        {/* The field is self-evident from the heading + placeholder; keep the label for screen
            readers only (never placeholder-as-label) rather than showing a redundant "Topic". */}
        <label className="sr-only" htmlFor={inputId}>
          Topic
        </label>
        <div className={styles.field}>
          <input
            id={inputId}
            ref={inputRef}
            className={styles.input}
            type="text"
            value={value}
            onChange={(event) => {
              onChange(event.target.value);
              if (error) setError(false);
            }}
            placeholder="e.g. how a hash map works…"
            aria-describedby={error ? errorId : hintId}
            aria-invalid={error || undefined}
            autoComplete="off"
            spellCheck={false}
            maxLength={200}
            autoFocus
          />
          <Button type="submit" variant="accent">
            Generate course
          </Button>
        </div>
        {error && (
          <p id={errorId} className={styles.error} role="alert">
            Enter a topic to build a course.
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
