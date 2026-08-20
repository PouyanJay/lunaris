import { useState } from "react";
import { Link } from "react-router";

import { useLiveSessions } from "../../hooks/useLiveSessions";
import {
  deleteSession,
  discardSession,
  endSession,
  forgetTopic,
  isFinished,
  type LiveSessionStatus,
  type LiveSessionSummary,
} from "../../lib/liveSessions";
import { ConfirmDialog } from "../overlays/ConfirmDialog";
import { Button } from "../primitives/Button";
import { SkeletonNotice } from "./SkeletonNotice";
import styles from "./SessionList.module.css";

/** What each status is called in front of a learner. Their own words rather than the wire's: a row
 *  reading "placing" tells somebody nothing about whether they can carry on with it. */
const STATUS_LABEL: Record<LiveSessionStatus, string> = {
  placing: "Getting to know you",
  warming: "Getting ready",
  active: "In progress",
  closed: "Finished",
  abandoned: "Left",
};

/** Which confirmation is open, and about what. `null` when none is. */
type Pending =
  | { verb: "delete"; session: LiveSessionSummary }
  | { verb: "forget"; session: LiveSessionSummary }
  | null;

interface SessionListProps {
  /** Where the API lives, threaded from the app root as every other request surface is. */
  apiBaseUrl: string;
}

/** A learner's own sessions, and the four things they can do with one (T2, T7b).
 *
 *  The first screen in Live that is *about* sessions rather than inside one, and the surface every
 *  lifecycle verb is pressed on. Until it existed there was nowhere to end, leave, delete or reset
 *  from, and nowhere to see that a session was still open. */
export function SessionList({ apiBaseUrl }: SessionListProps) {
  const { state, refresh } = useLiveSessions(apiBaseUrl);
  const [pending, setPending] = useState<Pending>(null);
  /** The session a verb is currently in flight for, so only its own row shows as busy. */
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  /** Run one verb, then re-read the list from the server rather than guessing the new row.
   *
   *  Never optimistic. Every verb here is either irreversible or costs a model call, which is
   *  exactly where the design system says to show a real pending state and confirm the true
   *  result. The server also decides things the surface cannot: whether a close wrote a goodbye
   *  turn, whether a reset was refused because a session is still going. */
  async function run(id: string, verb: () => Promise<unknown>) {
    setBusy(id);
    setFailure(null);
    try {
      await verb();
      setPending(null);
      refresh();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : "That didn't go through.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className={styles.panel} aria-labelledby="live-sessions-heading">
      <header className={styles.header}>
        <h1 id="live-sessions-heading" className={styles.heading}>
          Your sessions
        </h1>
      </header>

      {state.status === "loading" ? (
        <SkeletonNotice lead="Reading your sessions…" lines={3} />
      ) : null}

      {state.status === "failed" ? (
        <div className={styles.failed} role="alert">
          <p className={styles.failedMessage}>{state.message}</p>
          <Button variant="secondary" onClick={refresh}>
            Try again
          </Button>
        </div>
      ) : null}

      {state.status === "ready" && state.sessions.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyLead}>You haven&rsquo;t had a session yet.</p>
          <Link className={styles.start} to="/new?mode=live">
            Start one
          </Link>
        </div>
      ) : null}

      {state.status === "ready" && state.sessions.length > 0 ? (
        <ul className={styles.rows}>
          {state.sessions.map((session) => (
            <SessionRow
              key={session.sessionId}
              session={session}
              busy={busy === session.sessionId}
              onEnd={() =>
                void run(session.sessionId, () => endSession(apiBaseUrl, session.sessionId))
              }
              onLeave={() =>
                void run(session.sessionId, () => discardSession(apiBaseUrl, session.sessionId))
              }
              onDelete={() => setPending({ verb: "delete", session })}
              onForget={() => setPending({ verb: "forget", session })}
            />
          ))}
        </ul>
      ) : null}

      {/* One dialog for both destructive verbs: they ask the same shape of question, and two
          near-identical modals is how the two come to disagree about what they warn people of. */}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.verb === "forget" ? "Forget this topic?" : "Delete this session?"}
        description={pending ? descriptionOf(pending) : ""}
        confirmLabel={pending?.verb === "forget" ? "Forget topic" : "Delete session"}
        pendingLabel={pending?.verb === "forget" ? "Forgetting…" : "Deleting…"}
        danger
        pending={pending !== null && busy === pending.session.sessionId}
        errorMessage={failure}
        onConfirm={() => {
          if (!pending) return;
          const { verb, session } = pending;
          void run(session.sessionId, () =>
            verb === "forget"
              ? forgetTopic(apiBaseUrl, session.graphId)
              : deleteSession(apiBaseUrl, session.sessionId),
          );
        }}
        onCancel={() => {
          setPending(null);
          setFailure(null);
        }}
      />

      {/* A verb that failed outside a dialog (finishing, leaving) still has to say so. Live, so a
          screen reader hears it without having to go looking. */}
      {failure && pending === null ? (
        <p className={styles.verbFailed} role="alert">
          {failure}
        </p>
      ) : null}
    </section>
  );
}

/** What the learner is actually agreeing to. The two verbs remove different things (U2), and a
 *  learner has to be able to tell which one they are about to press. */
function descriptionOf({ verb, session }: NonNullable<Pending>): string {
  const name = session.topic ?? "this session";
  return verb === "forget"
    ? `Lunaris will forget what it knows about you on “${name}” — the progress you demonstrated, and the review schedule that came out of it. Your sessions and their transcripts stay where they are. This can't be undone.`
    : `“${name}” and everything said in it will be removed. What you demonstrated stays, so your progress on the topic is unaffected. This can't be undone.`;
}

/** One session, as a row: what it is, how it went, and what can still be done with it. */
function SessionRow({
  session,
  busy,
  onEnd,
  onLeave,
  onDelete,
  onForget,
}: {
  session: LiveSessionSummary;
  busy: boolean;
  onEnd: () => void;
  onLeave: () => void;
  onDelete: () => void;
  onForget: () => void;
}) {
  const name = session.topic ?? "Untitled session";
  const finished = isFinished(session.status);
  return (
    <li className={styles.row}>
      <div className={styles.rowMain}>
        <Link className={styles.topic} to={`/live?graph=${encodeURIComponent(session.graphId)}`}>
          {name}
        </Link>
        <p className={styles.meta}>
          <span className={styles.status} data-status={session.status}>
            {STATUS_LABEL[session.status]}
          </span>
          <span className={styles.separator} aria-hidden="true">
            ·
          </span>
          <span className={styles.turns}>
            {session.turnCount} {session.turnCount === 1 ? "turn" : "turns"}
          </span>
          <span className={styles.separator} aria-hidden="true">
            ·
          </span>
          <time className={styles.when} dateTime={session.updatedAt}>
            {whenOf(session.updatedAt)}
          </time>
        </p>
      </div>

      {/* Always present rather than revealed on hover: an action a keyboard or touch user cannot
          find is an action they do not have. */}
      <div className={styles.actions}>
        {finished ? null : (
          <>
            {/* Finishing writes the recap, the mastery delta and the review day, so it is the
                encouraged way out and needs no confirmation: nothing is lost by it. */}
            <Button variant="secondary" onClick={onEnd} disabled={busy}>
              Finish
            </Button>
            <Button variant="ghost" onClick={onLeave} disabled={busy}>
              Leave
            </Button>
          </>
        )}
        {/* Only once nothing is still going on this map: the API refuses a reset underneath a live
            session, because that session would write its beliefs back over it. Showing the rule as
            an absent button teaches it; showing the button and then a 409 does not. */}
        {finished ? (
          <Button variant="ghost" onClick={onForget} disabled={busy}>
            Forget topic
          </Button>
        ) : null}
        <Button variant="ghost" onClick={onDelete} disabled={busy}>
          Delete
        </Button>
      </div>
    </li>
  );
}

/** The day a session last moved, in the learner's own locale. Not a relative "3 hours ago": a list
 *  ordered by recency already says which is newest, and a date is what somebody scans for. */
function whenOf(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  return at.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
