import { useEffect, useMemo, useRef, type KeyboardEvent } from "react";

import { buildSections, sectionProgressAt, type LessonStep, type StepSection } from "./lessonSteps";
import type { Objective } from "../../types/course";
import { Button } from "../primitives/Button";
import { ChallengeStep } from "./ChallengeStep";
import { LessonResources } from "./LessonResources";
import { LessonScaffold } from "./LessonScaffold";
import { Markdown } from "./Markdown";
import { VisualRenderer } from "./visuals/VisualRenderer";
import styles from "./LearnMode.module.css";

/** Reading speed the time-left metric assumes — matches the Read mode's estimate. */
const WORDS_PER_MINUTE = 220;

/** The objectives context a challenge step needs to evidence what it assesses (Try First). */
interface ChallengeContext {
  objectives: Objective[];
  understoodObjectives: ReadonlySet<number>;
  onEvidenceObjective?: ((objectiveIndex: number, understood: boolean) => void) | undefined;
}

interface LearnModeProps {
  steps: LessonStep[];
  /** The current step (clamped by the parent). */
  index: number;
  onNavigate: (index: number) => void;
  /** Continue past the final step — the lesson's completion signal. */
  onComplete: () => void;
  /** Label for the final step's Continue ("Next lesson" / "Finish course"). */
  completeLabel: string;
  /** Course glossary, threaded into content steps' prose. */
  glossary?: ReadonlyMap<string, string> | undefined;
  /** Objectives context for the Try First challenge steps. */
  challenge: ChallengeContext;
}

function StepBody({
  step,
  glossary,
  challenge,
}: {
  step: LessonStep;
  glossary?: LearnModeProps["glossary"];
  challenge: ChallengeContext;
}) {
  switch (step.kind) {
    case "intro":
      return (
        <LessonScaffold
          title={step.sectionLabel}
          cue="What to be comfortable with before you start"
          items={step.items ?? []}
        />
      );
    case "content":
      return <Markdown glossary={glossary}>{step.markdown ?? ""}</Markdown>;
    case "visual":
      return step.visual ? <VisualRenderer visual={step.visual} /> : null;
    case "resources":
      return <LessonResources resources={step.resources ?? []} />;
    case "check":
    case "assessment":
      return (
        <ChallengeStep
          step={step}
          glossary={glossary}
          objectives={challenge.objectives}
          understoodObjectives={challenge.understoodObjectives}
          onEvidenceObjective={challenge.onEvidenceObjective}
        />
      );
  }
}

function ProgressRow({ steps, index }: { steps: LessonStep[]; index: number }) {
  const wordsLeft = steps.slice(index).reduce((sum, step) => sum + step.words, 0);
  const minutesLeft = Math.ceil(wordsLeft / WORDS_PER_MINUTE);
  return (
    <div className={styles.progressRow}>
      <div className={styles.segments} aria-hidden="true">
        {steps.map((step, i) => (
          <i
            key={step.id}
            className={styles.segment}
            data-state={i < index ? "done" : i === index ? "current" : undefined}
          />
        ))}
      </div>
      <div className={styles.metrics}>
        <p className={styles.metric} aria-live="polite">
          Step {index + 1} of {steps.length}
        </p>
        {wordsLeft > 0 && <p className={styles.metric}>≈ {minutesLeft} min left</p>}
      </div>
    </div>
  );
}

function StepNav({
  index,
  last,
  onNavigate,
  onComplete,
  completeLabel,
}: Pick<LearnModeProps, "onNavigate" | "onComplete" | "completeLabel"> & {
  index: number;
  last: boolean;
}) {
  return (
    <div className={styles.nav}>
      <Button disabled={index === 0} onClick={() => onNavigate(index - 1)}>
        Back
      </Button>
      {last ? (
        <Button variant="accent" onClick={onComplete}>
          {completeLabel}
        </Button>
      ) : (
        <Button variant="accent" onClick={() => onNavigate(index + 1)}>
          Continue
        </Button>
      )}
    </div>
  );
}

function SectionMap({
  sections,
  activeSection,
  passedSections,
  onNavigate,
}: {
  sections: StepSection[];
  activeSection: string | null;
  passedSections: ReadonlySet<string>;
  onNavigate: (index: number) => void;
}) {
  const stateOf = (section: StepSection) => {
    if (section.id === activeSection) return "current";
    return passedSections.has(section.id) ? "done" : "upcoming";
  };
  return (
    <nav className={styles.map} aria-label="Lesson sections">
      {sections.map((section) => (
        <button
          key={section.id}
          type="button"
          className={styles.mapItem}
          data-state={stateOf(section)}
          aria-current={section.id === activeSection ? "step" : undefined}
          onClick={() => onNavigate(section.firstIndex)}
        >
          <span className={styles.mapDot} aria-hidden="true" />
          {section.label}
        </button>
      ))}
    </nav>
  );
}

/** The guided Learn mode (Focus Flow): one idea per screen with a visible finish line — a
 *  segmented per-step bar, mono position/time-left metrics, the step card, Continue/Back, and a
 *  section map for orientation and jumps. The final Continue is the lesson's completion signal
 *  (the parent marks the lesson done and advances, exactly like Read mode's Next). */
export function LearnMode({
  steps,
  index,
  onNavigate,
  onComplete,
  completeLabel,
  glossary,
  challenge,
}: LearnModeProps) {
  const sections = useMemo(() => buildSections(steps), [steps]);
  const { activeSection, passedSections } = useMemo(
    () => sectionProgressAt(sections, index),
    [sections, index],
  );
  const step = steps[Math.min(index, Math.max(0, steps.length - 1))];

  // A step change moves focus to the fresh card so keyboard/AT users land on the new content;
  // never on first paint (the reader owns initial focus), so track the previous position.
  const cardRef = useRef<HTMLDivElement>(null);
  const previousIndex = useRef<number | null>(null);
  useEffect(() => {
    if (previousIndex.current !== null && previousIndex.current !== index) {
      cardRef.current?.focus();
    }
    previousIndex.current = index;
  }, [index]);

  // Left/Right walk the steps from anywhere inside the stage (the mode toggle lives outside it,
  // so its own arrow-key behaviour is untouched). The last step's advance stays on Continue —
  // completing a lesson is an explicit click, not an arrow slip.
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "ArrowRight" && index < steps.length - 1) {
      event.preventDefault();
      onNavigate(index + 1);
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      onNavigate(index - 1);
    }
  };

  if (!step) {
    return (
      <section className={styles.stage} aria-label="Lesson steps">
        <p className={styles.empty} role="status">
          This lesson has no content to step through yet.
        </p>
      </section>
    );
  }

  return (
    // The key handler is an enrichment over fully keyboard-operable buttons below.
    <section className={styles.stage} aria-label="Lesson steps" onKeyDown={onKeyDown}>
      <ProgressRow steps={steps} index={index} />
      <div
        ref={cardRef}
        className={styles.card}
        role="group"
        aria-label="Step content"
        tabIndex={-1}
      >
        {step.cue && step.kind === "content" && (
          <p className={styles.cardEyebrow}>
            {step.cue} · {step.sectionLabel}
          </p>
        )}
        <StepBody step={step} glossary={glossary} challenge={challenge} />
      </div>
      <StepNav
        index={index}
        last={index >= steps.length - 1}
        onNavigate={onNavigate}
        onComplete={onComplete}
        completeLabel={completeLabel}
      />
      <SectionMap
        sections={sections}
        activeSection={activeSection}
        passedSections={passedSections}
        onNavigate={onNavigate}
      />
    </section>
  );
}
