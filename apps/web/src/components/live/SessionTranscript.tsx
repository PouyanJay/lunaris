import type { LiveSession, SessionTurn, TurnGrade } from "../../lib/liveSession";
import { StatusDot, type StatusTone } from "../primitives/StatusDot";
import styles from "./SessionTranscript.module.css";
import { LearnerSpeech, TutorSpeech, Working } from "./Speech";

/** How a verdict reads. Muted, reserved meanings, and never colour alone: the dot carries the tone
 *  and the uppercase mono word carries the meaning for anyone who cannot see it. */
const GRADE_TONE: Record<TurnGrade["kind"], StatusTone> = {
  met: "success",
  partial: "warning",
  not_met: "danger",
};

const GRADE_LABEL: Record<TurnGrade["kind"], string> = {
  met: "met",
  partial: "partial",
  not_met: "not met",
};

interface SessionTranscriptProps {
  session: LiveSession;
  /** Rendered under the last turn while the learner's answer is being marked. */
  pending?: string | null;
}

/** The session, read back: what was decided, what was said, what the learner answered, how it was
 *  marked. One list, hairline-divided — the transcript and the director's trace are the same
 *  sequence read two ways, so they are one thing on screen too. */
export function SessionTranscript({ session, pending }: SessionTranscriptProps) {
  return (
    // Announced as it grows: a turn arriving is the whole event of a session, and a learner using
    // a screen reader should hear it without going looking for it.
    <ol className={styles.transcript} aria-label="Session transcript" aria-live="polite">
      {session.turns.map((turn) => (
        <li key={turn.seq} className={styles.turn}>
          <Turn turn={turn} />
        </li>
      ))}
      {pending ? (
        <li className={styles.turn}>
          <LearnerSpeech>{pending}</LearnerSpeech>
          <Working>Marking your answer…</Working>
        </li>
      ) : null}
    </ol>
  );
}

function Turn({ turn }: { turn: SessionTurn }) {
  return (
    <>
      <p className={styles.move}>
        <span className={styles.moveKind}>{turn.move.kind.replace("_", " ").toUpperCase()}</span>
        {/* The director emits its reasoning into the trace so every move is auditable (plan §7).
            Shown to the learner too: a session is dozens of choices made on their behalf, and the
            only thing that makes that feel like teaching rather than being steered is being told. */}
        <span className={styles.moveReason}>{turn.move.reason}</span>
      </p>
      <TutorSpeech>{turn.tutor}</TutorSpeech>
      {turn.criterion ? (
        <p className={styles.criterion}>
          <span className={styles.criterionLabel}>Show me</span>
          <span className={styles.criterionText}>{turn.criterion.statement}</span>
        </p>
      ) : null}
      {turn.answer ? <LearnerSpeech>{turn.answer}</LearnerSpeech> : null}
      {turn.grade ? (
        <p className={styles.grade}>
          <StatusDot label={GRADE_LABEL[turn.grade.kind]} tone={GRADE_TONE[turn.grade.kind]} />
          <span className={styles.gradeReason}>{turn.grade.reason}</span>
        </p>
      ) : null}
    </>
  );
}
