import type { ReactNode } from "react";

import {
  LAYOUT_CATALOG,
  type ExampleBlockSpec,
  type HintBlockSpec,
  type LayoutBlockSpec,
  type LayoutSpec,
  type PracticeBlockSpec,
} from "../../lib/layoutSpec";
import styles from "./LessonLayout.module.css";

interface Slots {
  /** What the tutor said. Goes wherever the layout's `Prose` slot is. */
  prose: ReactNode;
  /** The Tier 1 card. Goes wherever the layout's `Surface` slot is; null when the turn has none. */
  card: ReactNode;
}

interface LessonLayoutProps extends Slots {
  /** The composition the server chose for this learner, or null for a turn that has none. */
  layout: LayoutSpec | null;
}

/** A turn drawn the way it was composed — Tier 2 (P2b T5).
 *
 *  **This decides nothing.** Which blocks exist, in what order, and whether the worked example
 *  opens open are all the server's, read off what the learner has shown about this concept. The one
 *  thing this owes in return is that it draws exactly what it was handed: no reordering, no
 *  supplying a hint the layout withheld, no expanding an example the composition closed. A renderer
 *  that improved on the arrangement would make the two-learner claim unprovable from the wire, the
 *  same way an improvising Tier 1 renderer would corrupt the assessment (`SurfaceCard`, AD20).
 *
 *  **Slots, not copies.** The words and the card are passed in and placed. They live on the turn,
 *  which is the only place either can be authoritative — a layout carrying its own text could
 *  disagree with the transcript, and the learner is marked against the transcript.
 *
 *  **No layout is a real state, not a failure.** Every turn P2a stored has none, and so does a turn
 *  whose material could not be written. It falls back to the words and the card in that order,
 *  which is the composition itself minus the trimmings — so a session with no layouts reads as a
 *  plainer lesson rather than a broken one. */
export function LessonLayout({ layout, prose, card }: LessonLayoutProps) {
  const slots: Slots = { prose, card };
  const byId = new Map((layout?.blocks ?? []).map((block) => [block.id, block]));
  const root = byId.get("root");

  // A catalog this build has never heard of is treated as no layout at all. The API and this SPA
  // deploy separately, so the server can learn a v2 first — and drawing only the blocks this build
  // happens to recognise would show the learner a lesson with holes where the new ones were.
  const drawable = layout?.catalogId === LAYOUT_CATALOG && root?.component === "Stack";

  return (
    <div className={styles.lesson}>
      {drawable ? (
        <Children ids={root.children} byId={byId} drawn={new Set(["root"])} slots={slots} />
      ) : (
        <>
          {prose}
          {card}
        </>
      )}
    </div>
  );
}

/** Every child of one stack, in the order it was given.
 *
 *  ``drawn`` is carried down so a layout that names an ancestor as its own descendant stops instead
 *  of recursing until the tab dies. The server refuses such a layout, and this does not depend on
 *  that: these ids arrive over a wire, and a renderer that trusts them has made the browser's
 *  stability a property of somebody else's validator. */
function Children({
  ids,
  byId,
  drawn,
  slots,
}: {
  ids: string[];
  byId: Map<string, LayoutBlockSpec>;
  drawn: ReadonlySet<string>;
  slots: Slots;
}) {
  return (
    <>
      {ids.map((id) => {
        const block = byId.get(id);
        // Silently skipped rather than rendered as a gap: the server's own validator refuses a
        // layout naming a child it does not carry, so reaching here means a payload that has
        // already been tampered with or truncated, and a placeholder would dress that up as design.
        if (!block || drawn.has(id)) {
          return null;
        }
        return <Block key={id} block={block} byId={byId} drawn={drawn} slots={slots} />;
      })}
    </>
  );
}

function Block({
  block,
  byId,
  drawn,
  slots,
}: {
  block: LayoutBlockSpec;
  byId: Map<string, LayoutBlockSpec>;
  drawn: ReadonlySet<string>;
  slots: Slots;
}) {
  switch (block.component) {
    case "Prose":
      return <>{slots.prose}</>;
    case "Surface":
      return <>{slots.card}</>;
    case "WorkedExample":
      return <WorkedExample block={block} />;
    case "Hint":
      return <Hint block={block} />;
    case "Practice":
      return <Practice block={block} />;
    case "Stack":
      // Nothing composes a nested stack today, and the catalog can describe one. Drawn rather than
      // dropped, because a block the server put in a layout is material it meant to be seen.
      return (
        <div className={styles.lesson}>
          <Children
            ids={block.children}
            byId={byId}
            drawn={new Set([...drawn, block.id])}
            slots={slots}
          />
        </div>
      );
    default:
      return unhandled(block);
  }
}

/** The worked example, as a native disclosure.
 *
 *  `<details>` rather than a hand-rolled toggle: it is keyboard-operable, announces its own
 *  expanded state to a screen reader, and is findable by in-page search even while closed — three
 *  things a `useState` + `aria-expanded` version has to reimplement and usually gets half right.
 *
 *  `open` is set from the server's decision and deliberately *not* controlled afterwards: the
 *  composition chooses how the example arrives, and once the learner has opened or closed it, it is
 *  theirs. A controlled `open` would fight them every time the turn re-rendered. */
function WorkedExample({ block }: { block: ExampleBlockSpec }) {
  return (
    <details className={styles.disclosure} open={block.expanded}>
      <summary className={styles.summary}>
        <span className={styles.eyebrow}>Worked example</span>
        <span className={styles.summaryTitle}>{block.title}</span>
      </summary>
      <ol className={styles.steps}>
        {block.steps.map((step, index) => (
          <li key={step} className={styles.step}>
            <span className={styles.stepIndex}>{index + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
    </details>
  );
}

/** One hint, closed. Its being closed is the point: reaching for it is the learner's own move, and
 *  a hint that opened itself would be the answer moved up the page. */
function Hint({ block }: { block: HintBlockSpec }) {
  return (
    <details className={styles.disclosure}>
      <summary className={styles.summary}>
        <span className={styles.eyebrow}>Stuck?</span>
        <span className={styles.summaryTitle}>Show a hint</span>
      </summary>
      <p className={styles.hint}>{block.hint}</p>
    </details>
  );
}

/** Prompts to think through. Not a form and not marked — the evidence comes from the card. */
function Practice({ block }: { block: PracticeBlockSpec }) {
  return (
    <section className={styles.practice} aria-label="Before you answer">
      <p className={styles.eyebrow}>Before you answer</p>
      <ul className={styles.prompts}>
        {block.prompts.map((prompt) => (
          <li key={prompt} className={styles.prompt}>
            {prompt}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Two different jobs behind one line, kept distinguishable.
 *
 *  At compile time the `never` parameter is an exhaustiveness check: adding a seventh component to
 *  `LayoutBlockSpec` without handling it fails `tsc` here rather than silently rendering nothing.
 *  At runtime it is the deliberate behaviour for a value off the wire this build has never heard
 *  of — the server can learn a component first, and half a lesson is worse than a plain one. */
function unhandled(block: never): null {
  void block;
  return null;
}
