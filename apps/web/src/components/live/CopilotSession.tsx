import { CopilotKit, useRenderToolCall } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";

import {
  LAYOUT_TOOL,
  LIVE_AGENT,
  SURFACE_TOOL,
  copilotRuntimeUrl,
  sessionHeaders,
} from "../../lib/copilotRuntime";
import type { LayoutSpec } from "../../lib/layoutSpec";
import type { SurfaceSpec } from "../../lib/surfaceSpec";
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
}

/** A live session over CopilotKit, streaming from the Node runtime.
 *
 *  T1 mounts the surface and proves the path; it is deliberately unstyled beyond its container.
 *  Binding CopilotKit's own look to our tokens — the `--copilot-kit-*` custom properties and the
 *  overridable slots — is T7, and doing it here would spread the re-skin across every task that
 *  touches this file.
 *
 *  Absent a runtime this renders an explanation rather than nothing. Live is still usable without
 *  it: P2a's transcript talks to the REST endpoints, which did not go away, so a blank panel would
 *  misreport a configuration gap as a broken session. */
export function CopilotSession({
  runtimeUrl,
  sessionId,
  topic,
  standingTurn,
}: CopilotSessionProps) {
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
      <CopilotKit
        runtimeUrl={copilotRuntimeUrl(runtimeUrl)}
        agent={LIVE_AGENT}
        headers={sessionHeaders(sessionId)}
      >
        {/* Sized by our own wrapper rather than by the kit's `className` prop: the prop is typed
            as a required string, and a CSS-module lookup is `string | undefined` under
            `exactOptionalPropertyTypes`. A wrapper also keeps layout ours when T7 swaps the kit's
            internals for our slots. */}
        <SurfaceTool />
        <LayoutTool />
        <div className={styles.chat}>
          {/* Seeded with the turn the learner is standing on, because from T2 a message sent here
              takes a real turn and is graded against *that* turn's criterion. An empty chat would
              invite an answer to a question they had never been shown, and the verdict would then
              look arbitrary. Omitted rather than passed empty when there is nothing standing: an
              empty initial label renders a blank assistant bubble, which reads as a tutor that said
              nothing. Replaying the stored turn as a *label* rather than a run is deliberate for
              now — T4 merges this surface with the transcript and reads the session's state off the
              stream's own STATE_SNAPSHOT instead. */}
          <CopilotChat {...(standingTurn ? { labels: { initial: standingTurn } } : {})} />
        </div>
      </CopilotKit>
    </section>
  );
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
