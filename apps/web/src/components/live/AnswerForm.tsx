import { useId, useRef, useState, type KeyboardEvent } from "react";

import { MAX_ANSWER_CHARS } from "../../lib/liveSession";
import { Button } from "../primitives/Button";
import styles from "./AnswerForm.module.css";

interface AnswerFormProps {
  /** What the learner is being asked to demonstrate, or null when the turn stages nothing. */
  criterion: string | null;
  /** True while an answer is being marked — the box locks so one answer cannot be sent twice. */
  busy: boolean;
  onAnswer: (text: string) => void;
}

/** Where the learner replies. A textarea, because an answer is prose and the whole loop rests on
 *  them being able to say it in their own words.
 *
 *  Enter stays a newline and ⌘/Ctrl+Enter sends: a stray Return mid-thought that submitted the
 *  answer would be the surface answering for them. Submit is never pre-disabled — a form that
 *  greys out its own button hides the reason it is not ready — so an empty send explains itself
 *  instead. */
export function AnswerForm({ criterion, busy, onAnswer }: AnswerFormProps) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const boxId = useId();
  const errorId = useId();
  const box = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    if (busy) return;
    if (!text.trim()) {
      setError("Write something first — even a guess is worth marking.");
      box.current?.focus();
      return;
    }
    setError(null);
    onAnswer(text.trim());
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form
      className={styles.form}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label className={styles.label} htmlFor={boxId}>
        Your answer
      </label>
      <textarea
        id={boxId}
        ref={box}
        className={styles.box}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
        rows={3}
        maxLength={MAX_ANSWER_CHARS}
        disabled={busy}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        placeholder={criterion ? "In your own words…" : "Say what you're thinking…"}
      />
      <div className={styles.footer}>
        <p
          className={styles.hint}
          id={error ? errorId : undefined}
          role={error ? "alert" : undefined}
        >
          {error ?? (
            <>
              <kbd className={styles.kbd}>⌘</kbd>
              <kbd className={styles.kbd}>↵</kbd> to send
            </>
          )}
        </p>
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Sending…" : "Send"}
        </Button>
      </div>
    </form>
  );
}
