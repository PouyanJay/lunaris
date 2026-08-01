import { Button } from "../primitives/Button";
import { MenuPanel } from "../primitives/MenuPanel";
import { ClarifierQuestionField } from "../personalize/ClarifierQuestionField";
import { QUESTION_IDS, type BriefLoadState } from "../../types/clarifier";
import styles from "./PersonalizeMenu.module.css";

interface PersonalizeMenuProps {
  /** The topic being configured; the brief is read from it, so there is nothing to do without one. */
  topic: string;
  brief: BriefLoadState;
  /** Read (or re-read) the brief for the current topic. */
  onLoadBrief: () => void;
  /** A clarifier answer changed (question id to value). Answers thread into the build as they are
   *  edited, so there is no separate commit step. */
  onAnswerChange: (id: string, value: string) => void;
}

/** Personalization, docked in the composer's settings bar.
 *
 *  The interpreter reads the topic and pre-fills every answer, so the zero-friction path is to open
 *  this, glance, and close. The chip carries the state: it reads "Personalize" while the build will
 *  use pure inference, and "Tailored" once a brief has been read and its answers are threading.
 *
 *  Level is deliberately absent. The Level chip beside this one owns it, and two level pickers is a
 *  bug rather than a convenience. */
export function PersonalizeMenu({
  topic,
  brief,
  onLoadBrief,
  onAnswerChange,
}: PersonalizeMenuProps) {
  const ready = brief.status === "ready";

  return (
    <MenuPanel label="For you" value={ready ? "Tailored" : "Personalize"} set={ready} align="right">
      {(close) => (
        <>
          <div className={styles.head}>
            <h3 className={styles.title}>For you</h3>
            <p className={styles.sub}>
              We read your goal and pre-fill every answer. Change what looks wrong.
            </p>
          </div>

          <div className={styles.body}>
            {brief.status === "blank" && topic.trim() === "" && (
              <p className={styles.muted}>Name a topic first. We read your goal from it.</p>
            )}

            {brief.status === "blank" && topic.trim() !== "" && (
              <>
                <p className={styles.muted}>
                  Skip this and we will build from the inference alone.
                </p>
                <Button variant="secondary" onClick={onLoadBrief}>
                  Personalize this topic
                </Button>
              </>
            )}

            {brief.status === "loading" && (
              <p className={styles.muted} role="status">
                Reading your goal&hellip;
              </p>
            )}

            {brief.status === "error" && (
              <>
                <p className={styles.error} role="alert">
                  {brief.message}
                </p>
                <Button variant="secondary" onClick={onLoadBrief}>
                  Try again
                </Button>
              </>
            )}

            {brief.status === "ready" && (
              <>
                <p className={styles.read}>
                  We read this as{" "}
                  <strong>{brief.data.brief.goal || brief.data.brief.subject}</strong>.
                </p>
                <div className={styles.questions}>
                  {brief.data.clarifier.questions
                    .filter((question) => question.id !== QUESTION_IDS.LEVEL)
                    .map((question) => (
                      <ClarifierQuestionField
                        key={question.id}
                        question={question}
                        value={brief.answers[question.id] ?? ""}
                        onChange={(value) => onAnswerChange(question.id, value)}
                      />
                    ))}
                </div>
              </>
            )}
          </div>

          {ready && (
            <div className={styles.foot}>
              {/* Answers thread as they change, so this only dismisses. Calling it "Apply" would
                  imply the edits were not already in effect. */}
              <Button variant="secondary" onClick={close}>
                Done
              </Button>
            </div>
          )}
        </>
      )}
    </MenuPanel>
  );
}
