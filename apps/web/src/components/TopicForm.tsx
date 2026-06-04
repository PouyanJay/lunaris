import { useId, useRef, useState } from "react";

import { Button } from "./primitives/Button";
import styles from "./TopicForm.module.css";

interface TopicFormProps {
  onGenerate: (topic: string) => void;
  /** Opt into the infer-and-confirm clarifier for this topic before building (P7.5). */
  onPersonalize: (topic: string) => void;
}

const EXAMPLES = ["How binary search works", "How merge sort works", "How HTTPS works"];

/** The idle entry point: name a topic and Lunaris builds a verified course for it.
 *  A real <form> (Enter submits), a labelled input, and example topics for a warm start.
 *  "Generate course" builds straight from the inference; "Personalize" opts into a short
 *  confirm step first (the default stays one click). */
export function TopicForm({ onGenerate, onPersonalize }: TopicFormProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [topic, setTopic] = useState("");
  const [error, setError] = useState(false);

  // Validate a non-empty topic, surfacing the same inline error + refocus for either action, then
  // run `proceed`. Don't pre-disable submit (enterprise-ui forms rule).
  function withTopic(value: string, proceed: (topic: string) => void) {
    const trimmed = value.trim();
    if (!trimmed) {
      setError(true);
      inputRef.current?.focus();
      return;
    }
    setError(false);
    proceed(trimmed);
  }

  function submit(value: string) {
    withTopic(value, onGenerate);
  }

  return (
    <div className={styles.center}>
      <form
        className={styles.form}
        onSubmit={(event) => {
          event.preventDefault();
          submit(topic);
        }}
      >
        <span className="eyebrow">Build a course</span>
        <h2 className={styles.title}>
          What do you want to <span className={styles.titleAccent}>learn</span>?
        </h2>
        <p id={hintId} className={styles.hint}>
          Name a topic. Lunaris maps its prerequisites, writes the lessons, and verifies every claim
          &mdash; you&rsquo;ll watch each step run.
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
            value={topic}
            onChange={(event) => {
              setTopic(event.target.value);
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

        {/* Opt into the short confirm step (level, what you know, depth, style) before building. */}
        <button
          type="button"
          className={styles.personalize}
          onClick={() => withTopic(topic, onPersonalize)}
        >
          Personalize before building&hellip;
        </button>

        <div className={styles.examples}>
          <span className="eyebrow">Try</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className={styles.example}
              onClick={() => {
                setTopic(example);
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
