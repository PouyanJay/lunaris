import { useId, useRef, useState } from "react";

import { Button } from "./primitives/Button";
import styles from "./TopicForm.module.css";

interface TopicFormProps {
  onGenerate: (topic: string) => void;
}

const EXAMPLES = ["How binary search works", "How merge sort works", "How HTTPS works"];

/** The idle entry point: name a topic and Lunaris builds a verified course for it.
 *  A real <form> (Enter submits), a labelled input, and example topics for a warm start. */
export function TopicForm({ onGenerate }: TopicFormProps) {
  const inputId = useId();
  const hintId = useId();
  const errorId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [topic, setTopic] = useState("");
  const [error, setError] = useState(false);

  // Don't pre-disable submit: let an empty submit surface a clear error and refocus the
  // field, rather than leaving the user staring at a dead button (enterprise-ui forms rule).
  function submit(value: string) {
    const trimmed = value.trim();
    if (!trimmed) {
      setError(true);
      inputRef.current?.focus();
      return;
    }
    setError(false);
    onGenerate(trimmed);
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
        <h2 className={styles.title}>What do you want to learn?</h2>
        <p id={hintId} className={styles.hint}>
          Name a topic. Lunaris maps its prerequisites, writes the lessons, and verifies every claim
          &mdash; you&rsquo;ll watch each step run.
        </p>

        <label className={styles.label} htmlFor={inputId}>
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
          <Button type="submit" variant="primary">
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
