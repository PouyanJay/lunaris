import { useMemo } from "react";

import type { LessonStep } from "./lessonSteps";
import { Button } from "../primitives/Button";
import { LessonAssessment } from "./LessonAssessment";
import { LessonResources } from "./LessonResources";
import { LessonScaffold } from "./LessonScaffold";
import { Markdown } from "./Markdown";
import { VisualRenderer } from "./visuals/VisualRenderer";
import styles from "./LearnMode.module.css";

/** Reading speed the time-left metric assumes — matches the Read mode's estimate. */
const WORDS_PER_MINUTE = 220;

interface SectionRef {
  id: string;
  label: string;
  firstIndex: number;
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
}

function sectionsOf(steps: LessonStep[]): SectionRef[] {
  const sections: SectionRef[] = [];
  steps.forEach((step, index) => {
    if (sections[sections.length - 1]?.id !== step.sectionId) {
      sections.push({ id: step.sectionId, label: step.sectionLabel, firstIndex: index });
    }
  });
  return sections;
}

function StepBody({ step, glossary }: { step: LessonStep; glossary?: LearnModeProps["glossary"] }) {
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
      return (
        <LessonScaffold
          title="Self-check"
          cue="Confirm you’ve got it before moving on"
          items={step.items ?? []}
        />
      );
    case "assessment":
      return <LessonAssessment items={step.assessment ?? []} />;
  }
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
}: LearnModeProps) {
  const sections = useMemo(() => sectionsOf(steps), [steps]);
  const step = steps[Math.min(index, Math.max(0, steps.length - 1))];

  if (!step) {
    return (
      <section className={styles.stage} aria-label="Lesson steps">
        <p className={styles.empty} role="status">
          This lesson has no content to step through — switch to Read for the full page.
        </p>
      </section>
    );
  }

  const last = index >= steps.length - 1;
  const wordsLeft = steps.slice(index).reduce((sum, s) => sum + s.words, 0);
  const minutesLeft = Math.ceil(wordsLeft / WORDS_PER_MINUTE);
  const currentSectionId = step.sectionId;
  const sectionState = (section: SectionRef, next: SectionRef | undefined) => {
    if (section.id === currentSectionId) return "current";
    return next && index >= next.firstIndex ? "done" : "upcoming";
  };

  return (
    <section className={styles.stage} aria-label="Lesson steps">
      <div className={styles.progressRow}>
        <div className={styles.segments} aria-hidden="true">
          {steps.map((s, i) => (
            <i
              key={s.id}
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

      <div className={styles.card}>
        {step.cue && step.kind === "content" && (
          <p className={styles.cardEyebrow}>
            {step.cue} · {step.sectionLabel}
          </p>
        )}
        <StepBody step={step} glossary={glossary} />
      </div>

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

      <nav className={styles.map} aria-label="Lesson sections">
        {sections.map((section, i) => (
          <button
            key={section.id}
            type="button"
            className={styles.mapItem}
            data-state={sectionState(section, sections[i + 1])}
            aria-current={section.id === currentSectionId ? "step" : undefined}
            onClick={() => onNavigate(section.firstIndex)}
          >
            <span className={styles.mapDot} aria-hidden="true" />
            {section.label}
          </button>
        ))}
      </nav>
    </section>
  );
}
