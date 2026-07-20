import { useState } from "react";

import type { AssessmentItem, Objective } from "../../types/course";
import { ChallengeCard, type ChallengeGrade } from "./ChallengeCard";
import type { LessonStep } from "./lessonSteps";
import styles from "./ChallengeStep.module.css";

type GradeMap = Record<string, ChallengeGrade>;

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
function findObjectiveIndex(item: AssessmentItem, objectives: Objective[]): number {
  return objectives.findIndex((objective) => objective.kc === item.objective);
}

/** A bare self-check reflection: one challenge, no answer and no objective to evidence. */
function CheckChallenge({
  step,
  glossary,
}: {
  step: LessonStep;
  glossary?: ReadonlyMap<string, string> | undefined;
}) {
  const [grade, setGrade] = useState<ChallengeGrade>();
  return (
    <ChallengeCard
      prompt={step.items?.[0] ?? ""}
      onGrade={setGrade}
      grade={grade}
      glossary={glossary}
    />
  );
}

/** The module assessment as challenges: each item's self-graded "I got it" evidences the objective
 *  it assesses through the existing progress channel (AD2). Local grade state seeds from persisted
 *  objective-understood, so a revisited challenge shows its verdict. */
function AssessmentChallenges({
  items,
  objectives,
  understoodObjectives,
  onEvidenceObjective,
  glossary,
}: {
  items: AssessmentItem[];
  objectives: Objective[];
  understoodObjectives: ReadonlySet<number>;
  onEvidenceObjective?: ((objectiveIndex: number, understood: boolean) => void) | undefined;
  glossary?: ReadonlyMap<string, string> | undefined;
}) {
  const [grades, setGrades] = useState<GradeMap>({});
  return (
    <>
      {items.map((item) => {
        const objectiveIndex = findObjectiveIndex(item, objectives);
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
    </>
  );
}

/** A challenge step (Try First): a `check` step renders a single reflection; an `assessment` step
 *  renders each item as an attempt-before-explanation challenge wired to objective evidence. */
export function ChallengeStep({
  step,
  glossary,
  objectives,
  understoodObjectives,
  onEvidenceObjective,
}: ChallengeStepProps) {
  return (
    <div className={styles.stack}>
      {step.kind === "check" ? (
        <CheckChallenge step={step} glossary={glossary} />
      ) : (
        <AssessmentChallenges
          items={step.assessment ?? []}
          objectives={objectives}
          understoodObjectives={understoodObjectives}
          onEvidenceObjective={onEvidenceObjective}
          glossary={glossary}
        />
      )}
    </div>
  );
}
