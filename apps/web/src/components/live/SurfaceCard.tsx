import { useId, useState } from "react";

import type {
  ConceptMapSpec,
  CriterionCardSpec,
  ExplainBackSpec,
  MasteryMeterSpec,
  QuizCardSpec,
  SurfaceSpec,
} from "../../lib/surfaceSpec";
import { Button } from "../primitives/Button";
import { ProgressBar } from "../primitives/ProgressBar";
import { AnswerForm } from "./AnswerForm";
import styles from "./SurfaceCard.module.css";

/** What every answerable card is handed.
 *
 *  One declaration rather than three near-identical inline shapes: the only thing that differs
 *  between them is which member of the union `spec` is, and the generic keeps that difference while
 *  removing the copy. */
interface AnswerableCardProps<T extends SurfaceSpec> {
  spec: T;
  busy: boolean;
  answerable: boolean;
  onAnswer: (text: string) => void;
  welded: boolean;
}

interface SurfaceCardProps {
  /** The card the director chose, and every prop in it. Rendered as given. */
  spec: SurfaceSpec;
  /** True while an answer is being marked. */
  busy: boolean;
  /** False once the turn this card belonged to has been answered, or the session has closed —
   *  the card stays on screen as a record and stops taking answers. */
  answerable: boolean;
  onAnswer: (text: string) => void;
  /** True when the card sits directly under the transcript, which owns the shared top edge.
   *  False when it renders on its own — in the generative panel's message stream it has nothing
   *  above it, and a missing top border there reads as broken rather than as continuous. */
  welded?: boolean;
}

/** The Tier 1 card for one turn: what the director chose, rendered as it was chosen.
 *
 *  A switch and nothing more. Plan §8 makes this tier's rendering deterministic *because these
 *  components feed the learner model* — so the one thing this must not do is decide anything. It
 *  does not reorder the quiz's options (the server's order is what keeps the true one from always
 *  sitting in the same place), does not paraphrase a criterion (the learner is marked on those
 *  exact words), and does not fill a gap it was not given.
 *
 *  A kind this build does not know renders **nothing**. The API and this bundle are deployed
 *  separately, so the server can learn a sixth card first — and a wrong card is worse than no card
 *  when the answer it collects becomes mastery evidence. */
export function SurfaceCard({
  spec,
  busy,
  answerable,
  onAnswer,
  welded = false,
}: SurfaceCardProps) {
  const frame = { welded };
  switch (spec.kind) {
    case "criterion_card":
      return (
        <Criterion spec={spec} busy={busy} answerable={answerable} onAnswer={onAnswer} {...frame} />
      );
    case "quiz_card":
      return (
        <Quiz spec={spec} busy={busy} answerable={answerable} onAnswer={onAnswer} {...frame} />
      );
    case "explain_back":
      return (
        <Explain spec={spec} busy={busy} answerable={answerable} onAnswer={onAnswer} {...frame} />
      );
    case "mastery_meter":
      return <Meter spec={spec} {...frame} />;
    case "concept_map":
      return <Placement spec={spec} {...frame} />;
    default:
      return unhandled(spec);
  }
}

/** A card neither this build's union nor its switch knows about.
 *
 *  Two jobs, and they are not the same job. **At compile time** the parameter is `never`, so adding
 *  a sixth `SurfaceKind` without a `case` above becomes a type error rather than a silent
 *  fall-through — the safety net a bare `return null` does not provide. **At runtime** an older
 *  bundle meeting a newer server lands here and renders nothing, which is the deliberate behaviour:
 *  a wrong card is worse than no card when the answer it collects becomes mastery evidence. */
function unhandled(spec: never): null {
  void spec;
  return null;
}

/** What kind of thinking a criterion asks for, said plainly. The enum reads as a system word
 *  (`predict`); the learner is owed a sentence. */
const ASK_LABELS: Record<CriterionCardSpec["asks"], string> = {
  predict: "Predict what happens",
  manipulate: "Work it through",
  explain: "Explain it",
};

function Criterion({
  spec,
  busy,
  answerable,
  onAnswer,
  welded,
}: AnswerableCardProps<CriterionCardSpec>) {
  return (
    <Shell eyebrow={ASK_LABELS[spec.asks]} concept={spec.concept} welded={welded}>
      <p className={styles.ask}>{spec.statement}</p>
      {answerable ? (
        <AnswerForm criterion={spec.statement} busy={busy} onAnswer={onAnswer} embedded />
      ) : null}
    </Shell>
  );
}

function Explain({
  spec,
  busy,
  answerable,
  onAnswer,
  welded,
}: AnswerableCardProps<ExplainBackSpec>) {
  return (
    <Shell eyebrow="In your own words" concept={spec.concept} welded={welded}>
      <p className={styles.ask}>{spec.prompt}</p>
      {answerable ? (
        <AnswerForm criterion={spec.prompt} busy={busy} onAnswer={onAnswer} embedded />
      ) : null}
    </Shell>
  );
}

function Quiz({ spec, busy, answerable, onAnswer, welded }: AnswerableCardProps<QuizCardSpec>) {
  const [chosen, setChosen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const groupName = useId();
  const errorId = useId();
  const questionId = useId();

  const submit = () => {
    if (busy) return;
    if (chosen === null) {
      // Explained rather than prevented: a disabled button hides the reason it is not ready.
      setError("Pick one first — a guess tells us more than a blank.");
      return;
    }
    setError(null);
    // The option's *text*, because it is graded as an answer against the same criterion any prose
    // answer is (U1). An index would be a second assessment protocol with a different meaning.
    onAnswer(chosen);
  };

  return (
    <Shell eyebrow="Which one" concept={spec.concept} welded={welded}>
      {/* A form, so Enter submits from wherever the caret is — a radio group that could only be
          sent with the mouse would make the whole card slower to answer by keyboard than by hand. */}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        className={styles.quizForm}
      >
        {/* A fieldset for the native `disabled` cascade, and an explicit radiogroup role so the
          question is announced as the group's name — a bare fieldset reports as a generic group,
          which leaves a screen-reader user with three options and no question. */}
        <fieldset
          className={styles.options}
          role="radiogroup"
          aria-labelledby={questionId}
          aria-describedby={error ? errorId : undefined}
          disabled={!answerable || busy}
        >
          <legend className={styles.ask} id={questionId}>
            {spec.question}
          </legend>
          {spec.options.map((option) => (
            <label key={option} className={styles.option}>
              <input
                type="radio"
                name={groupName}
                value={option}
                className={styles.radio}
                checked={chosen === option}
                onChange={() => {
                  setChosen(option);
                  setError(null);
                }}
              />
              <span className={styles.optionText}>{option}</span>
            </label>
          ))}
        </fieldset>
        {answerable ? (
          <div className={styles.footer}>
            <p
              className={styles.hint}
              id={error ? errorId : undefined}
              role={error ? "alert" : undefined}
            >
              {error ?? "Graded the same way as anything else you write."}
            </p>
            <Button type="submit" variant="primary" disabled={busy}>
              {busy ? "Sending…" : "Send"}
            </Button>
          </div>
        ) : null}
      </form>
    </Shell>
  );
}

/** Where a bar stops reading as "in progress" and starts reading as "held".
 *
 *  The director's own `_MASTERED` (`decide_move.py`), mirrored rather than imported — it is a
 *  pedagogical constant on the far side of a wire, and a learner whose bar turned green at a
 *  different point from where the director stopped re-teaching would be reading a second opinion.
 *  If that number moves, this one moves with it. */
const HELD_RECALL = 0.6;

function Meter({ spec, welded }: { spec: MasteryMeterSpec; welded: boolean }) {
  return (
    <Shell eyebrow="What you showed" concept="This session" welded={welded}>
      {spec.entries.length === 0 ? (
        <p className={styles.note}>
          Nothing was marked this time. What you read is still yours — the map remembers where you
          got to.
        </p>
      ) : (
        <ul className={styles.meter}>
          {spec.entries.map((entry) => (
            <li key={entry.nodeId} className={styles.meterRow}>
              <span className={styles.meterConcept}>{entry.concept}</span>
              <ProgressBar
                value={entry.recall}
                label={`${entry.concept} — what you recall now`}
                tone={entry.recall >= HELD_RECALL ? "success" : "accent"}
              />
              <span className={styles.meterEvidence}>
                {`${entry.evidenceCount} ${entry.evidenceCount === 1 ? "answer" : "answers"}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Shell>
  );
}

function Placement({ spec, welded }: { spec: ConceptMapSpec; welded: boolean }) {
  return (
    <Shell eyebrow="Where this sits" concept={spec.concept} welded={welded}>
      <p className={styles.note}>
        This one can&rsquo;t be checked by talking — it needs something to play with, which is
        coming. Nothing you say here is marked.
      </p>
      {spec.prerequisites.length === 0 ? (
        <p className={styles.chainEmpty}>
          There is nothing before it: this is where the map opens.
        </p>
      ) : (
        <>
          <p className={styles.chainLabel}>What it rests on</p>
          <ol className={styles.chain}>
            {spec.prerequisites.map((name) => (
              <li key={name} className={styles.chainItem}>
                {name}
              </li>
            ))}
          </ol>
        </>
      )}
    </Shell>
  );
}

/** The frame every card shares: an eyebrow micro-label, the concept it is about, and the body.
 *
 *  Welded to the transcript above it rather than floating beside it — the card is part of the
 *  session's record, not a widget parked next to it. */
function Shell({
  eyebrow,
  concept,
  welded,
  children,
}: {
  eyebrow: string;
  concept: string;
  welded: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={styles.card} data-welded={welded} aria-label={`${eyebrow}: ${concept}`}>
      <header className={styles.head}>
        <p className={styles.eyebrow}>{eyebrow}</p>
        <p className={styles.concept}>{concept}</p>
      </header>
      {children}
    </section>
  );
}
