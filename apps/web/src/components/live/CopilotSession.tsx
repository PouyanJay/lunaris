import { CopilotKit, useCoAgent, useRenderToolCall } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import { useCallback, useEffect, useMemo, useState } from "react";

import { answeringSeqOf } from "../../lib/answeringSeq";
import {
  LAYOUT_TOOL,
  LIVE_AGENT,
  SURFACE_TOOL,
  copilotRuntimeUrl,
  sessionHeaders,
} from "../../lib/copilotRuntime";
import type { LayoutSpec } from "../../lib/layoutSpec";
import type { SurfaceSpec } from "../../lib/surfaceSpec";
import {
  LearnerMessage,
  MarkingAnswer,
  TurnComposer,
  TurnError,
  TutorMessage,
} from "./CopilotSlots";
import { LessonLayout } from "./LessonLayout";
import { SurfaceCard } from "./SurfaceCard";
import styles from "./CopilotSession.module.css";

interface CopilotSessionProps {
  /** The runtime's host, or `undefined` when the deployment has no runtime configured. */
  runtimeUrl: string | undefined;
  sessionId: string;
  /** The map's topic, which is what the session is about. */
  topic: string;
  /** What the tutor last said — the turn standing in front of the learner, or `null` when the
   *  session has none (it closed, or it has not taught yet). */
  standingTurn: string | null;
  /** That turn's seq as the REST read had it when the panel mounted, or `null` when nothing is
   *  standing. Names the answered turn on the first send; from then on the panel's own state
   *  frames say which turn is up (T9). */
  standingSeq: number | null;
}

/** The kit's `properties`, spread into `forwardedProps` on every run, when there is no turn to
 *  name. A stable object, so the provider sees no change from render to render. */
const NO_PROPERTIES: Record<string, never> = {};

/** The key the API reads out of `forwardedProps` (`RunProps.answering_seq`, camel-cased on the
 *  wire). Pinned as a literal like every other cross-deployable name in `copilotRuntime.ts`. */
export const ANSWERING_SEQ_PROP = "answeringSeq";

/** The kit's activity mark, built once: what it shows between the learner's send and the tutor's
 *  first word. */
const ICONS = { activityIcon: <MarkingAnswer /> };

/** A live session over CopilotKit, streaming from the Node runtime.
 *
 *  AD1, discharged here (T7): the kit's state machine, transport and generative-UI machinery, and
 *  none of its skin. Its stylesheet is not loaded at all — beyond its custom properties it carries a
 *  font stack, radii, hover motion and a vendor tag that no property reaches — and every slot that
 *  paints (`AssistantMessage`, `UserMessage`, `Input`, `ErrorMessage`, the activity mark) is one of
 *  our primitives from `CopilotSlots`. What the kit still renders itself is the message list's
 *  scaffolding, laid out by our own module.
 *
 *  Absent a runtime this renders an explanation rather than nothing. Live is still usable without
 *  it: P2a's transcript talks to the REST endpoints, which did not go away, so a blank panel would
 *  misreport a configuration gap as a broken session. */
export function CopilotSession({
  runtimeUrl,
  sessionId,
  topic,
  standingTurn,
  standingSeq,
}: CopilotSessionProps) {
  // Which turn the panel's next send is answering (T9): the turn the last state frame named for
  // *this* session, else the one the panel mounted with. Held per session id so a panel re-used
  // for another session cannot answer the new one with the old one's turn.
  const [answered, setAnswered] = useState<{ sessionId: string; seq: number } | null>(null);
  const answeringSeq = answered?.sessionId === sessionId ? answered.seq : standingSeq;
  const onTurn = useCallback((seq: number) => setAnswered({ sessionId, seq }), [sessionId]);
  // Both memoised: the provider re-runs its connect effect whenever either changes identity. A
  // reconnect is a no-op once connected, but re-applying properties on every parent render is
  // still churn for nothing, and a properties change is what carries the named turn to the wire.
  const headers = useMemo(() => sessionHeaders(sessionId), [sessionId]);
  const properties = useMemo(
    () => (answeringSeq === null ? NO_PROPERTIES : { [ANSWERING_SEQ_PROP]: answeringSeq }),
    [answeringSeq],
  );
  if (!runtimeUrl) {
    return (
      <p className={styles.unavailable} role="status">
        The live session surface is not configured for this deployment. Your session is still here
        and nothing has been lost.
      </p>
    );
  }

  return (
    <section className={styles.session} aria-label={`Session on ${topic}`}>
      {/* `useSingleEndpoint={false}`: the kit's default transport POSTs `{"method": …}` bodies to
          the bare base path; `apps/copilot` mounts the multi-route shape (`GET …/info`,
          `POST …/agent/live/run`, matching `mode: "multi-route"` there), and every request under
          the default 404'd — found by T7's output verification, invisible to six tasks of e2e that
          spoke the runtime's shape directly with curl.

          `enableInspector={false}`: left to decide by hostname the kit mounts its own inspector on
          localhost — a floating web component in its own skin, over our panel — which fetches from
          the vendor's CDN. Off, so dev and prod behave the same and a self-hosted deployment
          carrying learner sessions makes no third-party requests (the Node runtime's telemetry is
          off for the same reason). */}
      <CopilotKit
        // Keyed on the session: the kit's agent instance carries a thread and a state, and both
        // are the *previous* session's until the provider is rebuilt, a re-used panel would show
        // the old transcript and name the old turn. Remounting per session is the honest reset.
        key={sessionId}
        runtimeUrl={copilotRuntimeUrl(runtimeUrl)}
        agent={LIVE_AGENT}
        headers={headers}
        // Spread into `forwardedProps` on every run the kit makes (`CopilotKitCore.runAgent`),
        // which is where the API reads the answered turn (T9). The documented seam, and the
        // one that reaches the root entry: the kit's `useCopilotKit().setProperties` lives only on
        // its `/v2` entry, which imports the kit's stylesheet (AD35).
        properties={properties}
        useSingleEndpoint={false}
        enableInspector={false}
      >
        <AnsweredTurnTracker onTurn={onTurn} />
        {/* Sized by our own wrapper rather than by the kit's `className` prop: the prop is typed
            as a required string, and a CSS-module lookup is `string | undefined` under
            `exactOptionalPropertyTypes`. The wrapper is also where the kit's own structural
            classes are laid out. */}
        <SurfaceTool />
        <LayoutTool />
        <div className={styles.chat}>
          {/* Seeded with the turn the learner is standing on, because a message sent here takes a
              real turn and is graded against *that* turn's criterion. An empty chat would invite an
              answer to a question they had never been shown, and the verdict would then look
              arbitrary. Omitted rather than passed empty when there is nothing standing: an empty
              initial label renders a blank tutor row, which reads as a tutor that said nothing.

              `suggestions="manual"` with none set: the kit would otherwise offer generated
              "suggested replies", which is the surface answering for the learner. */}
          <CopilotChat
            {...(standingTurn ? { labels: { initial: standingTurn } } : {})}
            icons={ICONS}
            suggestions="manual"
            AssistantMessage={TutorMessage}
            UserMessage={LearnerMessage}
            Input={TurnComposer}
            ErrorMessage={TurnError}
          />
        </div>
      </CopilotKit>
    </section>
  );
}

/** Watches the agent's state for the turn now in front of the learner (T9).
 *
 *  Every run ends with a `STATE_SNAPSHOT` whose `turn` is `SessionSnapshot.turn`, the standing
 *  turn's seq, and it is the only thing in the panel that moves when the panel's own runs move
 *  the session on: the REST read that seeded the page does not re-read. Reported upward rather
 *  than used here, because the value has to reach the provider's `properties`, which sits above
 *  every hook the kit offers. Renders nothing. */
function AnsweredTurnTracker({ onTurn }: { onTurn: (seq: number) => void }) {
  const { state } = useCoAgent<{ turn?: unknown }>({ name: LIVE_AGENT });
  const named = answeringSeqOf(state, null);
  useEffect(() => {
    if (named !== null) onTurn(named);
  }, [named, onTurn]);
  return null;
}

/** Renders the turn's Tier 2 composition where the API called for it.
 *
 *  Registered as its own renderer rather than folded into `SurfaceTool`, mirroring the two tool
 *  calls the API sends: a build that draws the card and not the layout still assesses the learner
 *  correctly, which is the whole reason the tiers are separate calls.
 *
 *  The card slot is empty here. In the panel's message stream the card arrives as its own tool
 *  call, so drawing a second copy inside the layout would put two of them on screen — and the
 *  second would be the answerable one in a place a past turn can still be scrolled to. */
function LayoutTool() {
  useRenderToolCall({
    name: LAYOUT_TOOL,
    description: "How this turn was composed for this learner.",
    render: ({ args }) => (
      <LessonLayout layout={args as unknown as LayoutSpec} prose={null} card={null} />
    ),
  });
  return null;
}

/** Renders the director's Tier 1 card where the API called for it, inside the message stream.
 *
 *  `useRenderToolCall` rather than `useFrontendTool`: this tool is never *executed* here. The
 *  server already decided which card and filled every prop (plan §8's controlled tier), so the
 *  browser's only job is to draw it — a frontend handler would be a second place that could decide.
 *
 *  **Read-only in this panel, deliberately.** CopilotKit re-renders every tool call in the thread,
 *  so an answerable card would stay answerable long after its turn had moved on — and the AG-UI
 *  path derives the answering turn server-side (T2, AD10), so a late answer would be graded against
 *  whatever question is up *now* rather than refused. Answering happens in the composer below until
 *  the answered turn can be named on this transport, which is T9's work. The transcript surface,
 *  which every environment currently runs, is fully answerable in-card. */
function SurfaceTool() {
  useRenderToolCall({
    name: SURFACE_TOOL,
    description: "The Tier 1 card the director chose for this turn.",
    render: ({ args }) => (
      <SurfaceCard
        spec={args as unknown as SurfaceSpec}
        busy={false}
        answerable={false}
        onAnswer={() => {}}
      />
    ),
  });
  return null;
}
