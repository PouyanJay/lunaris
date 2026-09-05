import { deleteSession, forgetTopic, type LiveSessionSummary } from "../../lib/liveSessions";
import { ConfirmDialog } from "../overlays/ConfirmDialog";

/** Which destructive verb is being confirmed, and about which session. */
export type PendingVerb = { verb: "delete" | "forget"; session: LiveSessionSummary } | null;

interface ConfirmSessionVerbProps {
  pending: PendingVerb;
  /** The session a verb is in flight for, so the dialog only shows itself as working for its own. */
  busy: string | null;
  errorMessage: string | null;
  /** Where the API lives, threaded from the surface that owns the list. */
  apiBaseUrl: string;
  /** Run the verb and re-read the list. The runner is the surface's, so one failure state serves
   *  both the dialog and the verbs pressed outside it. */
  onRun: (sessionId: string, verb: () => Promise<unknown>) => void;
  onCancel: () => void;
}

/** The confirmation both destructive verbs share.
 *
 *  One dialog rather than two, because they ask the same shape of question and two near-identical
 *  modals is how two warnings come to disagree about what they warn people of. Its own component so
 *  the list stays a list (review finding).
 *
 *  Deleting and forgetting remove different things, which is the whole reason they are two verbs,
 *  so each description says what the other one keeps. */
export function ConfirmSessionVerb({
  pending,
  busy,
  errorMessage,
  apiBaseUrl,
  onRun,
  onCancel,
}: ConfirmSessionVerbProps) {
  const forgetting = pending?.verb === "forget";
  return (
    <ConfirmDialog
      open={pending !== null}
      title={forgetting ? "Forget this topic?" : "Delete this session?"}
      description={pending ? descriptionOf(pending) : ""}
      confirmLabel={forgetting ? "Forget topic" : "Delete session"}
      pendingLabel={forgetting ? "Forgetting…" : "Deleting…"}
      danger
      pending={pending !== null && busy === pending.session.sessionId}
      errorMessage={errorMessage}
      onConfirm={() => {
        if (!pending) return;
        const { verb, session } = pending;
        onRun(session.sessionId, () =>
          verb === "forget"
            ? forgetTopic(apiBaseUrl, session.graphId)
            : deleteSession(apiBaseUrl, session.sessionId),
        );
      }}
      onCancel={onCancel}
    />
  );
}

/** What the learner is actually agreeing to. */
function descriptionOf({ verb, session }: NonNullable<PendingVerb>): string {
  const name = session.topic ?? "this session";
  return verb === "forget"
    ? `Lunaris will forget what it knows about you on “${name}”: the progress you demonstrated, and the review schedule that came out of it. Your sessions and their transcripts stay where they are. This can't be undone.`
    : `“${name}” and everything said in it will be removed. What you demonstrated stays, so your progress on the topic is unaffected. This can't be undone.`;
}
