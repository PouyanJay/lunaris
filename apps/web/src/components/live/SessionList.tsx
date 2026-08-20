import { Link } from "react-router";

import { useLiveSessions } from "../../hooks/useLiveSessions";
import { type LiveSessionStatus, type LiveSessionSummary } from "../../lib/liveSessions";
import { SkeletonNotice } from "./SkeletonNotice";
import styles from "./SessionList.module.css";

/** What each status is called in front of a learner. Their own words rather than the wire's: a row
 *  reading "placing" tells somebody nothing about whether they can carry on with it. */
const STATUS_LABEL: Record<LiveSessionStatus, string> = {
  placing: "Getting to know you",
  warming: "Getting ready",
  active: "In progress",
  closed: "Finished",
};

interface SessionListProps {
  /** Where the API lives, threaded from the app root as every other request surface is. */
  apiBaseUrl: string;
}

/** A learner's own sessions (T2).
 *
 *  The first screen in Live that is *about* sessions rather than inside one, and the surface every
 *  lifecycle verb this journey adds gets pressed on. Until it existed there was nowhere to end,
 *  discard or delete a session from, and nowhere to see that one was still open. */
export function SessionList({ apiBaseUrl }: SessionListProps) {
  const { state, refresh } = useLiveSessions(apiBaseUrl);

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
          <button type="button" className={styles.retry} onClick={refresh}>
            Try again
          </button>
        </div>
      ) : null}

      {state.status === "ready" && state.sessions.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyLead}>You haven&rsquo;t had a session yet.</p>
          <Link className={styles.start} to="/new">
            Start one
          </Link>
        </div>
      ) : null}

      {state.status === "ready" && state.sessions.length > 0 ? (
        <ul className={styles.rows}>
          {state.sessions.map((session) => (
            <SessionRow key={session.sessionId} session={session} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** One session, as a row. The topic is the link, because it is the thing a learner is looking for;
 *  the rest is the shape of what they did, set in the data face the rest of the product uses. */
function SessionRow({ session }: { session: LiveSessionSummary }) {
  const name = session.topic ?? "Untitled session";
  return (
    <li className={styles.row}>
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
