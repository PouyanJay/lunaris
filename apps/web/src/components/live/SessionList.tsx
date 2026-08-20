import { useState } from "react";
import { Link } from "react-router";

import { useLiveSessions } from "../../hooks/useLiveSessions";
import { useSessionVerb } from "../../hooks/useSessionVerb";
import {
  discardSession,
  endSession,
  isFinished,
  type LiveSessionStatus,
  type LiveSessionSummary,
} from "../../lib/liveSessions";
import { Button } from "../primitives/Button";
import { ConfirmSessionVerb, type PendingVerb } from "./ConfirmSessionVerb";
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
  const { busy, failure, run, clear } = useSessionVerb(refresh);
  const [pending, setPending] = useState<PendingVerb>(null);

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

      <ConfirmSessionVerb
        pending={pending}
        busy={busy}
        errorMessage={failure}
        apiBaseUrl={apiBaseUrl}
        onRun={(sessionId, verb) => {
          void run(sessionId, verb).then(() => setPending(null));
        }}
        onCancel={() => {
          setPending(null);
          clear();
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
