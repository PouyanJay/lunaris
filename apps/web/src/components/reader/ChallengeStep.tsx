import { useState } from "react";

import type { AssessmentItem, Objective } from "../../types/course";
import { ChallengeCard, type ChallengeGrade } from "./ChallengeCard";
import type { LessonStep } from "./lessonSteps";
import styles from "./ChallengeStep.module.css";

interface ChallengeStepProps {
  step: LessonStep;
  glossary?: ReadonlyMap<string, string> | undefined;
  /** The owning module's objectives, so an item can evidence the objective it assesses. */
  objectives: Objective[];
  /** Objective indexes already marked understood (drives the persisted "got it" verdict). */
  understoodObjectives: ReadonlySet<number>;
  /** Evidence an objective from a self-grade; absent (offline) → self-grade stays local only. */
  onEvidenceObjective?: ((objectiveIndex: number, understood: boolean) => void) | undefined;
}

/** The module-objective index an assessment item assesses (`item.objective` is the objective's
 *  KC), or -1 when the item maps to none. */
function objectiveIndexFor(item: AssessmentItem, objectives: Objective[]): number {
  return objectives.findIndex((objective) => objective.kc === item.objective);
}

/** A challenge step (Try First): renders the step's prompts as attempt-before-explanation
 *  challenges. An `assessment` step maps each `AssessmentItem` to a card and, where the item
 *  assesses a module objective, a self-graded "I got it" evidences that objective through the
 *  existing progress channel (AD2). A `check` step is a single bare self-check reflection with no
 *  answer and no objective link. Local grade state seeds from persisted objective-understood so a
 *  revisited challenge shows its verdict; it also holds self-check verdicts for the visit. */
export function ChallengeStep({
  step,
  glossary,
  objectives,
  understoodObjectives,
  onEvidenceObjective,
}: ChallengeStepProps) {
  const [grades, setGrades] = useState<Record<string, ChallengeGrade>>({});

  if (step.kind === "check") {
    const prompt = step.items?.[0] ?? "";
    return (
      <div className={styles.stack}>
        <ChallengeCard
          prompt={prompt}
          onGrade={(grade) => setGrades((prev) => ({ ...prev, [step.id]: grade }))}
          grade={grades[step.id]}
          glossary={glossary}
        />
      </div>
    );
  }

  const items = step.assessment ?? [];
  return (
    <div className={styles.stack}>
      {items.map((item) => {
        const objectiveIndex = objectiveIndexFor(item, objectives);
        const evidenced = objectiveIndex >= 0 && understoodObjectives.has(objectiveIndex);
        const grade = grades[item.id] ?? (evidenced ? "got-it" : undefined);
        return (
          <ChallengeCard
            key={item.id}
            prompt={item.prompt}
            answer={item.answer}
            criterion={item.passCriterion}
            glossary={glossary}
            grade={grade}
            onGrade={(next) => {
              setGrades((prev) => ({ ...prev, [item.id]: next }));
              if (objectiveIndex >= 0) onEvidenceObjective?.(objectiveIndex, next === "got-it");
            }}
          />
        );
      })}
    </div>
  );
}
