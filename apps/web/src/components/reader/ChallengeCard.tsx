import { useId, useState } from "react";

import { Button } from "../primitives/Button";
import { Markdown } from "./Markdown";
import styles from "./ChallengeCard.module.css";

/** The learner's self-assessed verdict after seeing the answer (AD1: self-report is the grade). */
export type ChallengeGrade = "got-it" | "not-yet";

interface ChallengeCardProps {
  /** The question the learner commits to before the explanation. */
  prompt: string;
  /** The model answer (assessment items); absent for a bare self-check reflection. */
  answer?: string | null;
  /** The gradeable bar a passing response clears ("Passes when …"); may be empty. */
  criterion?: string;
  /** Called when the learner self-grades; absent hides the grade step (e.g. read-only contexts). */
  onGrade?: (grade: ChallengeGrade) => void;
  /** The learner's prior verdict, so a revisited challenge shows its state. */
  grade?: ChallengeGrade | undefined;
  /** Course glossary, so a revealed answer gets the same rich rendering as prose. */
  glossary?: ReadonlyMap<string, string> | undefined;
}

/** A word from the model answer the learner echoed — surfaced as SOFT assistance, never as the
 *  grade (AD1). Only fires on distinctive tokens (≥3 chars, alphanumeric) to avoid matching "the". */
function echoedTerm(attempt: string, answer: string): string | null {
  const haystack = attempt.toLowerCase();
  const terms = answer
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((term) => term.length >= 3);
  return terms.find((term) => haystack.includes(term)) ?? null;
}

/** A Try First challenge (Focus Flow phase 3): the prompt leads, the learner commits an attempt,
 *  and only then is the model answer + pass criterion revealed as the explanation "into the gap".
 *  There is no runtime grader (AD1), so the learner self-assesses; where an answer exists, a soft
 *  echo hint assists without deciding. Advancing is never gated on any of this (AD4). */
export function ChallengeCard({
  prompt,
  answer,
  criterion,
  onGrade,
  grade,
  glossary,
}: ChallengeCardProps) {
  const [attempt, setAttempt] = useState("");
  const [revealed, setRevealed] = useState(false);
  const fieldId = useId();
  const hint = revealed && answer ? echoedTerm(attempt, answer) : null;
  // A bare self-check carries no answer or criterion — there is nothing to "reveal", so the
  // commit step leads straight to honest self-assessment.
  const hasExplanation = Boolean(answer || criterion);

  return (
    <div className={styles.card}>
      <p className={styles.prompt}>{prompt}</p>

      <div className={styles.field}>
        <label htmlFor={fieldId} className={styles.label}>
          Your answer
        </label>
        <textarea
          id={fieldId}
          className={styles.textarea}
          value={attempt}
          onChange={(event) => setAttempt(event.target.value)}
          placeholder="Commit to an answer before you reveal — that's where the learning happens."
          rows={3}
          maxLength={2000}
          spellCheck={false}
        />
      </div>

      {!revealed ? (
        <div className={styles.actions}>
          <Button variant="accent" onClick={() => setRevealed(true)}>
            {hasExplanation ? "Reveal answer" : "Check yourself"}
          </Button>
        </div>
      ) : (
        <>
          {hasExplanation && (
            <div className={styles.reveal} role="region" aria-label="The answer" aria-live="polite">
              <p className={styles.revealHead}>The answer</p>
              {answer && (
                <div className={styles.answerText}>
                  <Markdown glossary={glossary}>{answer}</Markdown>
                </div>
              )}
              {criterion && (
                <p className={styles.criterion}>
                  <span className={styles.criterionLabel}>Passes when</span> {criterion}
                </p>
              )}
              {hint && (
                <span className={styles.hint}>
                  <span className={styles.hintMark} aria-hidden="true">
                    ✓
                  </span>
                  Your answer mentions “{hint}”.
                </span>
              )}
            </div>
          )}

          {onGrade && (
            <div className={styles.grade} role="group" aria-label="How did you do?">
              <span className={styles.gradeCue}>
                Compare honestly with the answer — did you have it?
              </span>
              {grade ? (
                <span className={styles.verdict} data-grade={grade}>
                  <span className={styles.verdictDot} aria-hidden="true" />
                  {grade === "got-it" ? "You marked: got it" : "You marked: not yet"}
                </span>
              ) : (
                <div className={styles.gradeButtons}>
                  <Button variant="accent" onClick={() => onGrade("got-it")}>
                    I got it
                  </Button>
                  <Button onClick={() => onGrade("not-yet")}>Not yet</Button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
