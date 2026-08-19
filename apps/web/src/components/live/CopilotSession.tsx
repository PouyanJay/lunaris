import { CopilotKit, useCoAgent, useRenderToolCall } from "@copilotkit/react-core";
import { CopilotChat, type InputProps } from "@copilotkit/react-ui";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";

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
import { SessionEnded } from "./SessionEnded";
import { SurfaceCard } from "./SurfaceCard";
import styles from "./CopilotSession.module.css";
import slotStyles from "./CopilotSlots.module.css";

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
  /** Called each time the panel's own runs move the session on to a new turn (T10). The host
   *  re-reads the session so the transcript beside the panel stays the record it claims to be. */
  onTurnTaken?: (() => void) | undefined;
}

/** What the agent's state says, as the last `STATE_SNAPSHOT` left it (`SessionSnapshot` on the
 *  API); every field optional because the state is `{}` until the first run answers. */
interface PanelState {
  turn?: unknown;
  status?: unknown;
  surfaceCallId?: unknown;
}

/** The one send path in the panel, as the kit hands it to its `Input` slot, made reachable by the
 *  cards the kit renders elsewhere in the tree (T10). `send` is the composer's own `onSend`
 *  (`agent.addMessage` + `runAgent`, so the named turn rides along) held in a ref, because its
 *  identity is the kit's business and a state update per identity would re-render the panel into
 *  a loop; `busy` while a turn is in flight and `ready` once the kit has found the agent are
 *  primitives, so a same-value report is a no-op. Before the composer has reported, nothing can
 *  send, which is also true. */
interface ComposerBridge {
  send: MutableRefObject<(text: string) => void>;
  busy: boolean;
  ready: boolean;
}

interface ComposerReport {
  send: (text: string) => void;
  busy: boolean;
  ready: boolean;
}

const NOBODY = { current: () => {} };
const NOT_YET: ComposerBridge = { send: NOBODY, busy: false, ready: false };
const ComposerContext = createContext<ComposerBridge>(NOT_YET);
const ReportComposerContext = createContext<(report: ComposerReport) => void>(() => {});

/** The composer's side of the bridge, held above the kit: the cards read `bridge`, the composer
 *  calls `report`. Its own hook so `CopilotSession` composes it beside the answered-turn state
 *  rather than growing the plumbing inline (T10, from review). */
function useComposerBridge(): {
  bridge: ComposerBridge;
  report: (report: ComposerReport) => void;
} {
  const send = useRef<(text: string) => void>(() => {});
  const [state, setState] = useState({ busy: false, ready: false });
  const report = useCallback((next: ComposerReport) => {
    send.current = next.send;
    setState((held) =>
      held.busy === next.busy && held.ready === next.ready
        ? held
        : { busy: next.busy, ready: next.ready },
    );
  }, []);
  const bridge = useMemo<ComposerBridge>(
    () => ({ send, busy: state.busy, ready: state.ready }),
    [state],
  );
  return { bridge, report };
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
  onTurnTaken,
}: CopilotSessionProps) {
  // Which turn the panel's next send is answering (T9): the turn the last state frame named for
  // *this* session, else the one the panel mounted with. Held per session id so a panel re-used
  // for another session cannot answer the new one with the old one's turn.
  const [answered, setAnswered] = useState<{ sessionId: string; seq: number } | null>(null);
  const answeringSeq = answered?.sessionId === sessionId ? answered.seq : standingSeq;
  const onTurn = useCallback(
    (seq: number) => {
      setAnswered((held) => {
        // Reported once per new turn: the tracker re-fires on every re-render of its own, and the
        // host's re-read is a request.
        if (held?.sessionId === sessionId && held.seq === seq) return held;
        onTurnTaken?.();
        return { sessionId, seq };
      });
    },
    [sessionId, onTurnTaken],
  );
  // The composer reports its send path and its state; the cards read them (T10).
  const { bridge: composer, report: reportComposer } = useComposerBridge();
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
        <SurfaceTool />
        <LayoutTool />
        <ComposerContext.Provider value={composer}>
          <ReportComposerContext.Provider value={reportComposer}>
            {/* Sized by our own wrapper rather than by the kit's `className` prop: the prop is
                typed as a required string, and a CSS-module lookup is `string | undefined` under
                `exactOptionalPropertyTypes`. The wrapper is also where the kit's own structural
                classes are laid out. */}
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
                Input={PanelComposer}
                ErrorMessage={TurnError}
              />
            </div>
          </ReportComposerContext.Provider>
        </ComposerContext.Provider>
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
  const { state } = useCoAgent<PanelState>({ name: LIVE_AGENT });
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
  useRenderToolCall(LAYOUT_RENDERER);
  return null;
}

/** Module-level and never re-created, and this is load-bearing (T10): the kit's hook re-registers
 *  its renderer whenever the config object changes identity, each registration wraps `render` in a
 *  fresh component, and the kit's `ToolCallRenderer` is memoised on that identity, so a config
 *  literal in the component body remounted every card in the thread on the next re-render of its
 *  row, and a learner's half-picked quiz or half-typed answer was thrown away by their first click.
 *  Neither renderer reads anything from the component scope; what a card needs it takes from
 *  context and the agent's state itself. */
const LAYOUT_RENDERER = {
  name: LAYOUT_TOOL,
  description: "How this turn was composed for this learner.",
  render: ({ args }: { args: unknown }) => (
    <LessonLayout layout={args as LayoutSpec} prose={null} card={null} />
  ),
};

/** The composer the kit renders as its `Input`: the transcript's own form, plus what the panel
 *  needs from it (T10). It reports its send path and state upward for the cards, and when the
 *  session has closed it is the ending, said in the transcript surface's words, rather than a box
 *  the API would refuse (409) or a box locked with no reason given. */
export function PanelComposer(props: InputProps) {
  const { onSend, inProgress, chatReady = false } = props;
  const report = useContext(ReportComposerContext);
  const { state } = useCoAgent<PanelState>({ name: LIVE_AGENT });
  const closed = state.status === "closed";
  useEffect(() => {
    report({ send: (text) => void onSend(text), busy: inProgress, ready: chatReady && !closed });
  }, [report, onSend, inProgress, chatReady, closed]);
  if (closed) {
    return <SessionEnded className={slotStyles.composer} />;
  }
  return <TurnComposer {...props} />;
}

/** The director's Tier 1 card as the kit renders it in the message stream, answerable in place
 *  when it is the question in front of the learner (T10, closing AD22).
 *
 *  Which card that is comes from the API, not from the browser: the last state frame names the
 *  tool-call id of the standing card (`surfaceCallId`), and only the card whose id matches, on a
 *  session still open, offers an answer. Every other card in the thread is the record. The answer
 *  goes out through the composer's own send path (so it names the turn, T9) and is graded by the
 *  same separate grader against the same criterion as a typed one (AD16). Busy and not-yet-ready
 *  are the composer's states, shared, so one turn is in flight at a time whichever way it is sent. */
function PanelCard({ toolCallId, spec }: { toolCallId: string | null; spec: SurfaceSpec }) {
  const { state } = useCoAgent<PanelState>({ name: LIVE_AGENT });
  const composer = useContext(ComposerContext);
  const standing = isStandingCard(toolCallId, state);
  return (
    <SurfaceCard
      spec={spec}
      busy={composer.busy}
      // Whether the session is still open is the composer's to say (`ready` is withheld once it
      // has closed); a second check here would be a second place for that rule to be got wrong.
      answerable={standing && composer.ready}
      onAnswer={(text) => composer.send.current(text)}
    />
  );
}

/** Whether the card rendered under `toolCallId` is the one the last state frame named as standing.
 *
 *  A card with no id at all (a build of the kit that stopped passing `toolCallId`) is never
 *  standing, whatever the state says: the alternative is every card answerable, and a wrong card
 *  is worse than a read-only one when the answer it collects becomes evidence (AD20). Pure and
 *  exported so that fallback is pinned on its own, rather than through a tree the kit builds. */
export function isStandingCard(toolCallId: string | null, state: PanelState): boolean {
  return toolCallId !== null && state.surfaceCallId === toolCallId;
}

/** Renders the director's Tier 1 card where the API called for it, inside the message stream.
 *
 *  `useRenderToolCall` rather than `useFrontendTool`: this tool is never *executed* here. The
 *  server already decided which card and filled every prop (plan §8's controlled tier), so the
 *  browser's only job is to draw it, and a frontend handler would be a second place that could
 *  decide. Drawn by `PanelCard`, which decides nothing about the card either: only whether this
 *  copy is the one being asked. */
function SurfaceTool() {
  useRenderToolCall(SURFACE_RENDERER);
  return null;
}

/** See `LAYOUT_RENDERER` for why this is module-level. `toolCallId` is on the props the kit passes
 *  (its v2 renderer's), not on the v1 type the root hook declares, so it is read structurally; a
 *  build of the kit that stopped passing it leaves every card a record rather than every card
 *  answerable. */
const SURFACE_RENDERER = {
  name: SURFACE_TOOL,
  description: "The Tier 1 card the director chose for this turn.",
  render: (props: { args: unknown }) => (
    <PanelCard
      toolCallId={(props as { toolCallId?: string }).toolCallId ?? null}
      spec={props.args as SurfaceSpec}
    />
  ),
};
