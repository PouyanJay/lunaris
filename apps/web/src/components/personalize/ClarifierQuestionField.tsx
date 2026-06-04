import { useId } from "react";

import type { ClarifierQuestion } from "../../types/clarifier";
import styles from "./ClarifierQuestionField.module.css";

interface ClarifierQuestionFieldProps {
  question: ClarifierQuestion;
  value: string;
  onChange: (value: string) => void;
}

// Mirrors the schema cap on the free-text Clarification fields (defence in depth at the input).
const MAX_TEXT_LENGTH = 1000;

/**
 * One clarifier question, rendered by its kind: a CHOICE as an accessible native radio group
 * (`<fieldset>` + `<legend>`, arrow-key navigation for free), or TEXT as a labelled multi-line
 * field whose placeholder shows the inference (typing ADDS to it; empty keeps the inference).
 */
export function ClarifierQuestionField({ question, value, onChange }: ClarifierQuestionFieldProps) {
  const fieldId = useId();

  if (question.kind === "choice") {
    return (
      <fieldset className={styles.fieldset}>
        <legend className={styles.legend}>{question.prompt}</legend>
        <div className={styles.options}>
          {question.options.map((option) => (
            <label key={option.value} className={styles.option}>
              <input
                type="radio"
                name={fieldId}
                value={option.value}
                checked={value === option.value}
                onChange={() => onChange(option.value)}
                className={styles.radio}
              />
              <span className={styles.optionLabel}>{option.label}</span>
              {option.recommended && <span className={styles.recommended}>Suggested</span>}
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  return (
    <div className={styles.text}>
      <label htmlFor={fieldId} className={styles.legend}>
        {question.prompt}
      </label>
      <textarea
        id={fieldId}
        className={styles.textarea}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={question.placeholder}
        rows={2}
        maxLength={MAX_TEXT_LENGTH}
        spellCheck={false}
      />
    </div>
  );
}
