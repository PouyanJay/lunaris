import {
  type Clarification,
  type Clarifier,
  type DetailDepth,
  type LanguageStyle,
  type Level,
  QUESTION_IDS,
} from "../types/clarifier";

/**
 * The initial answers for a clarifier: each CHOICE pre-picks its `recommended` (else first) option,
 * each TEXT starts empty. TEXT must start empty because the server APPENDS a non-empty answer to the
 * inferred prior — pre-filling it with the inference would duplicate it on confirm.
 */
export function recommendedAnswers(clarifier: Clarifier): Record<string, string> {
  const answers: Record<string, string> = {};
  for (const question of clarifier.questions) {
    if (question.kind === "choice") {
      const picked = question.options.find((option) => option.recommended) ?? question.options[0];
      answers[question.id] = picked?.value ?? "";
    } else {
      answers[question.id] = "";
    }
  }
  return answers;
}

/**
 * Map the confirmed answers (keyed by question id) onto the typed {@link Clarification} the build
 * consumes. CHOICE answers always ride along (overriding with the inferred value is a harmless
 * no-op server-side); empty/whitespace TEXT is omitted, so confirming the inference verbatim is the
 * identity — byte-for-byte today's inferred-only build.
 */
export function answersToClarification(answers: Record<string, string>): Clarification {
  const clarification: Clarification = {};
  const level = answers[QUESTION_IDS.LEVEL];
  if (level) clarification.targetLevel = level as Level;
  const detail = answers[QUESTION_IDS.DETAIL];
  if (detail) clarification.detailDepth = detail as DetailDepth;
  const language = answers[QUESTION_IDS.LANGUAGE];
  if (language) clarification.languageStyle = language as LanguageStyle;
  const knowledge = answers[QUESTION_IDS.KNOWLEDGE]?.trim();
  if (knowledge) clarification.assumedKnown = knowledge;
  const background = answers[QUESTION_IDS.BACKGROUND]?.trim();
  if (background) clarification.background = background;
  return clarification;
}
