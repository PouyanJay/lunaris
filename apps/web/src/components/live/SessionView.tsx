import { Suspense, lazy, useState } from "react";

import { useLiveSession } from "../../hooks/useLiveSession";
import type { LiveSession, SessionTurn } from "../../lib/liveSession";
import { Button } from "../primitives/Button";
import { StatusDot } from "../primitives/StatusDot";
import { nextReviewOf, type NextReview } from "../../lib/reviewSchedule";
import { AnswerForm } from "./AnswerForm";
import { LessonLayout } from "./LessonLayout";
import { SessionEnded } from "./SessionEnded";
import { SkeletonNotice, Warming } from "./SkeletonNotice";
import { SessionTranscript } from "./SessionTranscript";
import { SurfaceCard } from "./SurfaceCard";
import styles from "./SessionView.module.css";

/** CopilotKit's whole module graph, kept out of Live's chunk until a deployment actually has a
 *  runtime to talk to.
 *
 *  Statically imported it costs every `/live` visitor ~171 kB gzipped whether or not
 *  `VITE_COPILOT_URL` is set — and today it is set nowhere, so that would be the entire cost for
 *  none of the benefit. Lazily, the kit is fetched only once the surface is genuinely in use.
 *
 *  It also keeps Live's own lazy chunk light enough to resolve promptly: pulling the kit in eagerly
 *  made `App.liveRouting` and `App.composerFork` time out waiting for the shell to appear, which is
 *  a real signal about first paint rather than a quirk of the test environment. */
const CopilotSession = lazy(() =>
  import("./CopilotSession").then((module) => ({ default: module.CopilotSession })),
);

interface SessionViewProps {
  apiBaseUrl: string;
  /** The map to open on, when the learner already has one (P2a's opening). Absent, the session
   *  opens on `topic` instead — placing while the map compiles behind it (P2c). */
  graphId?: string | undefined;
  /** The session's subject: the map's topic, or the topic being compiled. */
  topic: string;
  /** Lunaris Live's CopilotKit runtime, when the deployment has one.
   *
   *  Undefined everywhere until an operator sets `VITE_COPILOT_URL`. When it *is* set the panel
   *  becomes the one place to answer and the transcript stays the record (T4) — two live answer
   *  paths on one session is how the two surfaces came to disagree about what the learner had
   *  done, which T2 recorded and this closes. */
  copilotUrl?: string | undefined;
}

/** A live session, in the plainest form that can carry one: the transcript, and a box to answer in.
 *
 *  Deliberately unadorned. P2b brings the generative surfaces (CopilotKit / A2UI); what this owes is
 *  that the loop is usable and legible end to end — every move visible with the reason behind it,
 *  every verdict attached to the answer that earned it, and every state a session can actually be
 *  in rendered rather than assumed. */
export function SessionView({ apiBaseUrl, graphId, topic, copilotUrl }: SessionViewProps) {
  const { state, answer, retry, refresh } = useLiveSession(
    apiBaseUrl,
    graphId !== undefined ? { graphId } : { topic },
  );
  // Their own words, shown the moment they send them. Optimistic about the *echo* only — never
  // about the verdict, which is the server's to give and the one thing that must not be guessed.
  const [sending, setSending] = useState<string | null>(null);
  const session = state.status === "opening" ? null : state.session;
  // The turn in front of the learner, named once. Two surfaces need it — the answer form asks for
  // its criterion, the generative panel opens on its words — and the Python side calls the same
  // thing `standing` (`SessionSnapshot.of`), so the concept keeps one name across the wire.
  const standing = session?.turns.at(-1) ?? null;
  // What the close scheduled (P2c T7), read off the goodbye turn's meter: the ending says the day
  // on both surfaces, so it is derived once here and handed to each. The meter is only ever the
  // goodbye's card, so "there is a meter standing" is "the session closed".
  const nextReview: NextReview | null =
    standing?.surface?.kind === "mastery_meter" ? nextReviewOf(standing.surface.entries) : null;
  // Exactly one live answer path. With a runtime configured the CopilotKit panel owns answering and
  // this side is the record; without one, this side is the whole session.
  const answerHere = !copilotUrl;
  const send = (text: string) => {
    setSending(text);
    answer(text);
  };

  return (
    <section className={styles.session} aria-label={`Session on ${topic}`}>
      <header className={styles.header}>
        <div className={styles.identity}>
          <p className="eyebrow">Live session</p>
          {/* The page's own heading: a session is the whole surface now (P2c, U5), and where it
              is reached from a map, the map has been put away — so it is never a second h1. */}
          <h1 className={styles.topic}>{topic}</h1>
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
          <TurnFooter
            standing={standing}
            closed={session.status === "closed"}
            nextReview={nextReview}
            warming={session.status === "warming"}
            answerHere={answerHere}
            busy={state.status === "answering"}
            onAnswer={send}
          />
        </>
      ) : null}

      {session && copilotUrl ? (
        <Suspense fallback={<p className={styles.ended}>Loading the live session surface…</p>}>
          <CopilotSession
            // Remounted when teaching begins (P2c T7): the panel's thread opens on the turn it
            // mounted with, and the first lesson arrives through the host's poll, not through a
            // run of the panel's own — so a placing panel would otherwise keep showing the last
            // interview question over a session that has moved on. The interview stays in the
            // transcript beside it, which is the record.
            key={`${session.sessionId}:${phaseOf(session)}`}
            runtimeUrl={copilotUrl}
            sessionId={session.sessionId}
            topic={topic}
            standingTurn={standing?.tutor ?? null}
            standingSeq={standing?.seq ?? null}
            nextReview={nextReview}
            onTurnTaken={refresh}
          />
        </Suspense>
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

/** What sits under the transcript: the director's card, a way to answer it, or the ending.
 *
 *  One function because it is one decision. Written as two adjacent conditionals it read as two —
 *  each re-deriving part of the same state — and the four cases it actually has (a card to answer,
 *  a card to read, a plain box for a session stored before P2b, and a session that has ended) were
 *  something a reader had to reassemble rather than see. */
function TurnFooter({
  standing,
  closed,
  nextReview,
  warming,
  answerHere,
  busy,
  onAnswer,
}: {
  standing: SessionTurn | null;
  closed: boolean;
  /** What the close scheduled, for the ending to say (P2c T7). */
  nextReview: NextReview | null;
  /** The interview has ended and the map has not landed (P2c T2): nothing to answer, the hook is
   *  polling, and the surface says so rather than offering a box. */
  warming: boolean;
  /** False when the generative panel owns answering, so this side is the record (T4). */
  answerHere: boolean;
  busy: boolean;
  onAnswer: (text: string) => void;
}) {
  if (warming) return <Warming />;
  return (
    <>
      {/* Tier 2 (T5). The layout says where the card goes and what supporting material sits around
          it; with no layout it draws the card alone, which is every session stored before P2b.
          The prose slot is empty here on purpose — the transcript above already holds every word
          the tutor has said, and putting the standing turn's words back would print them twice. */}
      <LessonLayout
        layout={standing?.layout ?? null}
        prose={null}
        card={
          /* Rendered on a closed session too, where it is the mastery meter and reads as the
             ending it is — but never answerable there. */
          standing?.surface ? (
            <SurfaceCard
              spec={standing.surface}
              busy={busy}
              answerable={answerHere && !closed}
              onAnswer={onAnswer}
              welded
            />
          ) : null
        }
      />
      {closed ? (
        <SessionEnded nextReview={nextReview} className={styles.ended} />
      ) : answerHere && !standing?.surface ? (
        // Every session P2a stored has no card. The plain box keeps that history answerable rather
        // than making the tier's arrival a migration.
        <AnswerForm
          criterion={standing?.criterion?.statement ?? null}
          busy={busy}
          onAnswer={onAnswer}
        />
      ) : null}
    </>
  );
}

/** Which of a session's two lives it is in: being placed (interview, and the wait for the map) or
 *  being taught. The panel is remounted across the boundary (see its `key`), and nowhere else. */
function phaseOf(session: LiveSession): "placing" | "teaching" {
  return session.status === "placing" || session.status === "warming" ? "placing" : "teaching";
}

/** How far in, and whether it is still going. Mono, because these are data. */
function SessionMeta({ session, live }: { session: LiveSession; live: boolean }) {
  const closed = session.status === "closed";
  return (
    <div className={styles.meta}>
      <StatusDot
        label={closed ? "closed" : session.status === "active" ? "live" : session.status}
        tone={closed ? "neutral" : "accent"}
        live={live && !closed}
      />
      <span className={styles.turns}>
        {session.turns.length} {session.turns.length === 1 ? "turn" : "turns"}
      </span>
    </div>
  );
}

/** The gap between asking for a session and the first thing to read. */
function Opening() {
  return <SkeletonNotice lead="Opening your session…" lines={3} />;
}
