import type {
  AssistantMessageProps,
  ErrorMessageProps,
  InputProps,
  UserMessageProps,
} from "@copilotkit/react-ui";
import { useEffect, useRef, useState } from "react";

import { Callout } from "../primitives/Callout";
import { AnswerForm } from "./AnswerForm";
import styles from "./CopilotSlots.module.css";
import { LearnerSpeech, TutorSpeech, Working } from "./Speech";

/** The slots this panel hands `<CopilotChat/>` — its `AssistantMessage`, `UserMessage`, `Input`
 *  and `ErrorMessage`. AD1: we take the kit's state machine, transport and generative-UI machinery
 *  and none of its skin, and these four are where the skin would otherwise be. Each is built from
 *  the same primitives as the transcript surface, so a turn reads the same on the record and live.
 *
 *  Nothing here decides anything about the session: the words are printed as written, the card is
 *  drawn as handed over, and an answer goes back through the kit's own `onSend`. */

/** The tutor's turn: its words, then the Tier 1 card / Tier 2 layout the API's tool calls
 *  produced, which the kit's `RenderMessage` passes in as `subComponent`.
 *
 *  Deliberately without the kit's regenerate / copy / thumbs controls. Regenerating a *graded*
 *  turn would take another turn against the same criterion — the loop has no such move — and
 *  feedback on a turn has nowhere to go. */
export function TutorMessage({
  message,
  subComponent,
  isLoading,
  isGenerating,
}: AssistantMessageProps) {
  const words = message?.content ?? "";
  // The kit lets a tool result ask to be drawn before the words; the director's card follows the
  // words that frame it, so that request is honoured only when made.
  const cardFirst = message?.generativeUIPosition === "before";
  const announced = useAnnouncedOnCompletion(words, Boolean(isLoading || isGenerating));
  if (!words && !subComponent && !isLoading) return null;

  const card = subComponent ? <div className={styles.surface}>{subComponent}</div> : null;
  return (
    <div className={styles.turn} data-speaker="tutor">
      {cardFirst ? card : null}
      {words ? <TutorSpeech>{words}</TutorSpeech> : null}
      {cardFirst ? null : card}
      {isLoading ? <Working>Tutor is writing…</Working> : null}
      {/* What a screen reader hears of a streamed turn (T10, the question T7 left): the whole
          turn, once, when it is complete. A live region on the words themselves would re-announce
          on every delta; the visible words stay where they are for anyone navigating to them. A
          `log` rather than a second `status`: this is a transcript being added to, and the
          "Tutor is writing…" mark above already holds the status role. */}
      <span className="sr-only" role="log" aria-label="What the tutor said">
        {announced}
      </span>
    </div>
  );
}

/** How long the announcement is left in the status region after it has been read out, before it
 *  is cleared so the same words are not met twice by anyone navigating the row. Long enough for
 *  an assistive technology to pick the change up; it is not a visible duration. */
const ANNOUNCEMENT_MS = 3000;

/** The words to announce: the finished turn, exactly once, only for a turn this component saw
 *  being written. A turn that mounts complete (a reload draws the whole transcript at once) is
 *  never announced, or arriving would read the sitting aloud. */
function useAnnouncedOnCompletion(words: string, streaming: boolean): string {
  const [announced, setAnnounced] = useState("");
  const wasStreaming = useRef(false);
  useEffect(() => {
    if (streaming) {
      wasStreaming.current = true;
      return;
    }
    if (!wasStreaming.current || !words) return;
    wasStreaming.current = false;
    setAnnounced(words);
    const clear = setTimeout(() => setAnnounced(""), ANNOUNCEMENT_MS);
    return () => clearTimeout(clear);
  }, [streaming, words]);
  return announced;
}

/** The learner's answer, as sent. AG-UI user content is a string or a list of parts; the text
 *  parts are joined the way the kit's own slot joins them, so the record reads the same. */
export function LearnerMessage({ message }: UserMessageProps) {
  const content = message?.content;
  const words =
    typeof content === "string"
      ? content
      : (content ?? [])
          .flatMap((part) => (part.type === "text" ? [part.text] : []))
          .join(" ")
          .trim();
  return (
    <div className={styles.turn} data-speaker="learner">
      <LearnerSpeech>{words}</LearnerSpeech>
    </div>
  );
}

/** Where the learner answers: the same form as the transcript surface (⌘↵ sends, Enter is a
 *  newline, submit is never pre-disabled), handed to the kit as its `Input`.
 *
 *  Locked while a turn is in flight (one turn per session, P2a) and until the kit has found the
 *  agent at the runtime (`chatReady`) — before that a send is dropped with nothing shown. There is
 *  no stop control on purpose: a dropped stream does not cancel the turn (AD8), so "Stop" here
 *  would stop the words and not the turn. */
export function TurnComposer({ inProgress, onSend, chatReady = false }: InputProps) {
  return (
    <div className={styles.composer}>
      <AnswerForm
        criterion={null}
        busy={inProgress || !chatReady}
        embedded
        onAnswer={(text) => {
          void onSend(text);
        }}
      />
    </div>
  );
}

/** A turn that failed after it began — a `RUN_ERROR` mid-turn, or a refusal the runtime relayed.
 *  Without this slot the kit shows nothing (it logs to the console), and a failed turn is
 *  indistinguishable from a tutor still thinking.
 *
 *  The message is printed as the API wrote it and the recovery is left to it (T9): every refusal's
 *  sentence already says what to do next, a ceiling says start a fresh session, a duplicate says
 *  give it a moment, a moved-on turn says reload, and a fixed "send it again" here contradicted
 *  three of them. What this adds is only what is true of every failure: nothing was lost. */
export function TurnError({ error }: ErrorMessageProps) {
  return (
    <div className={styles.turn} role="alert">
      <Callout variant="warning">
        <p className={styles.fault}>The turn could not be taken: {error.message}</p>
        <p className={styles.faultLead}>
          Your session is still here and nothing has been lost; the transcript above is the record.
        </p>
      </Callout>
    </div>
  );
}

/** What the kit shows between the learner's send and the tutor's first word (its `activityIcon`):
 *  the answer is with the grader, and the director has not decided yet. The same line, in the same
 *  words, the transcript surface shows for the same wait. */
export function MarkingAnswer() {
  return (
    <span className={styles.pending}>
      <Working>Marking your answer…</Working>
    </span>
  );
}
