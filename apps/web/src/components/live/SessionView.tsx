import { useState } from "react";

import { useLiveSession } from "../../hooks/useLiveSession";
import type { LiveSession } from "../../lib/liveSession";
import { Button } from "../primitives/Button";
import { StatusDot } from "../primitives/StatusDot";
import { AnswerForm } from "./AnswerForm";
import { SessionTranscript } from "./SessionTranscript";
import styles from "./SessionView.module.css";

interface SessionViewProps {
  apiBaseUrl: string;
  graphId: string;
  /** The map's topic, shown as the session's subject. */
  topic: string;
}

/** A live session, in the plainest form that can carry one: the transcript, and a box to answer in.
 *
 *  Deliberately unadorned. P2b brings the generative surfaces (CopilotKit / A2UI); what this owes is
 *  that the loop is usable and legible end to end — every move visible with the reason behind it,
 *  every verdict attached to the answer that earned it, and every state a session can actually be
 *  in rendered rather than assumed. */
export function SessionView({ apiBaseUrl, graphId, topic }: SessionViewProps) {
  const { state, answer, retry } = useLiveSession(apiBaseUrl, graphId);
  // Their own words, shown the moment they send them. Optimistic about the *echo* only — never
  // about the verdict, which is the server's to give and the one thing that must not be guessed.
  const [sending, setSending] = useState<string | null>(null);
  const session = state.status === "opening" ? null : state.session;

  return (
    <section className={styles.session} aria-label={`Session on ${topic}`}>
      <header className={styles.header}>
        <div className={styles.identity}>
          <p className="eyebrow">Live session</p>
          <h2 className={styles.topic}>{topic}</h2>
        </div>
        {session ? <SessionMeta session={session} live={state.status !== "failed"} /> : null}
      </header>

      {state.status === "opening" ? <Opening /> : null}

      {session ? (
        <>
          <SessionTranscript
            session={session}
            pending={state.status === "answering" ? sending : null}
          />
          {state.status === "failed" ? (
            <p className={styles.failure} role="alert">
              {state.message}
            </p>
          ) : null}
          {session.status === "closed" ? (
            <p className={styles.ended}>
              This session has ended. Its record stays here, and what you demonstrated is remembered
              the next time you open this map.
            </p>
          ) : (
            <AnswerForm
              criterion={session.turns[session.turns.length - 1]?.criterion?.statement ?? null}
              busy={state.status === "answering"}
              onAnswer={(text) => {
                setSending(text);
                answer(text);
              }}
            />
          )}
        </>
      ) : null}

      {state.status === "failed" && !session ? (
        <div className={styles.failed}>
          <p className={styles.failureLead} role="alert">
            {state.message}
          </p>
          <Button variant="primary" onClick={retry}>
            Try again
          </Button>
        </div>
      ) : null}
    </section>
  );
}

/** How far in, and whether it is still going. Mono, because these are data. */
function SessionMeta({ session, live }: { session: LiveSession; live: boolean }) {
  const closed = session.status === "closed";
  return (
    <div className={styles.meta}>
      <StatusDot
        label={closed ? "closed" : "live"}
        tone={closed ? "neutral" : "accent"}
        live={live && !closed}
      />
      <span className={styles.turns}>
        {session.turns.length} {session.turns.length === 1 ? "turn" : "turns"}
      </span>
    </div>
  );
}

/** The gap between asking for a session and the first thing to read. Shaped like the transcript it
 *  is standing in for, so nothing jumps when the first turn lands. */
function Opening() {
  return (
    <div className={styles.opening} role="status">
      <p className={styles.openingLead}>Opening your session…</p>
      <div className={styles.skeletonLines} aria-hidden="true">
        <span className={styles.skeleton} />
        <span className={styles.skeleton} />
        <span className={styles.skeletonShort} />
      </div>
    </div>
  );
}
