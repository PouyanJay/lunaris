import { useContext, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import { MAX_ANSWER_CHARS } from "../../lib/liveSession";
import { Button } from "../primitives/Button";
import styles from "./AnswerForm.module.css";
import { IncomingAnswerContext, type IncomingAnswer } from "./IncomingAnswerContext";

interface AnswerFormProps {
  /** What the learner is being asked to demonstrate, or null when the turn stages nothing. */
  criterion: string | null;
  /** Seed an editable transcript; remount with a new source identity for another draft. */
  initialAnswer?: string;
  /** True while an answer is being marked — the box locks so one answer cannot be sent twice. */
  busy: boolean;
  onAnswer: (text: string) => void;
  /** True when a Tier 1 card is already framing this (T4): the card carries the border, the
   *  eyebrow and the question, so the form drops its own chrome and keeps only the box. Two
   *  bordered regions inside one another is the cards-in-cards look the house style forbids. */
  embedded?: boolean;
}

/** Where the learner replies. A textarea, because an answer is prose and the whole loop rests on
 *  them being able to say it in their own words.
 *
 *  Enter stays a newline and ⌘/Ctrl+Enter sends: a stray Return mid-thought that submitted the
 *  answer would be the surface answering for them. Submit is never pre-disabled — a form that
 *  greys out its own button hides the reason it is not ready — so an empty send explains itself
 *  instead. */
export function AnswerForm({
  criterion,
  busy,
  onAnswer,
  embedded = false,
  initialAnswer = "",
}: AnswerFormProps) {
  const [text, setText] = useState(initialAnswer);
  const [error, setError] = useState<string | null>(null);
  const boxId = useId();
  const errorId = useId();
  const box = useRef<HTMLTextAreaElement>(null);
  const incoming = useContext(IncomingAnswerContext);
  const received = useRef<string | null>(null);
  const [overflow, setOverflow] = useState<IncomingAnswer | null>(null);
  useLayoutEffect(() => {
    if (!incoming || received.current === incoming.id) return;
    received.current = incoming.id;
    const combined = text.trim() ? `${text}\n${incoming.text}` : incoming.text;
    if (combined.length > MAX_ANSWER_CHARS) setOverflow(incoming);
    else {
      setText(combined);
      setOverflow(null);
      box.current?.focus();
    }
  }, [incoming, text]);

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
      className={`${styles.form} ${embedded ? styles.embedded : ""}`.trim()}
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label className={embedded ? styles.hiddenLabel : styles.label} htmlFor={boxId}>
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
      {overflow && overflow.id === incoming?.id ? (
        <div>
          <p className={styles.hint} role="alert">
            The recording is too long to add to your typed answer. You can use the recording
            instead.
          </p>
          <Button
            type="button"
            disabled={busy}
            onClick={() => {
              setText(overflow.text);
              setOverflow(null);
              box.current?.focus();
            }}
          >
            Use recording instead
          </Button>
        </div>
      ) : null}
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
