import { createElement, useEffect, useMemo, useRef, type ReactNode } from "react";
import type { Components } from "react-markdown";

import type { PhraseMark } from "./annotations";
import { Markdown } from "./Markdown";
import styles from "./LessonProse.module.css";

interface LessonProseProps {
  prose: string;
  /** Matched-claim sentence texts for this phase; the containing block is tagged as a cross-link. */
  marks: PhraseMark[];
  /** Course glossary for auto-marking terms in this phase's prose (Field Guide). */
  glossary?: ReadonlyMap<string, string> | undefined;
  activeClaimId: string | null;
  onSelectClaim: (id: string) => void;
}

/** Collapse to comparable words so a rendered block ("source with purpose") matches the raw
 *  sentence ("*source with purpose*") regardless of Markdown markers or punctuation. */
function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The visible text of a hast node (react-markdown passes the source node to each component). */
function nodeText(node: unknown): string {
  if (!node || typeof node !== "object") return "";
  const element = node as { type?: string; value?: string; children?: unknown[] };
  if (element.type === "text") return element.value ?? "";
  if (Array.isArray(element.children)) return element.children.map(nodeText).join("");
  return "";
}

/** A phase's prose, rendered as rich Markdown (bold/italic/lists/links/tables no longer show as
 *  literal markers). The block (paragraph or list-item) that contains a verifier claim's matched
 *  sentence is tagged as a cross-link to its rail annotation: selecting the rail entry highlights +
 *  scrolls to this block, and a marker on the block selects the rail entry (bidirectional). A claim
 *  with no confident sentence match links to its phase instead (handled by the reader).
 *
 *  The parsed Markdown is memoised and the active highlight is applied imperatively, so selecting a
 *  claim never re-parses the prose or remounts its (future) stateful children (video, collapsibles). */
export function LessonProse({
  prose,
  marks,
  glossary,
  activeClaimId,
  onSelectClaim,
}: LessonProseProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const components = useMemo<Components>(() => {
    const needles = marks.map((mark) => ({ claimId: mark.claimId, needle: normalize(mark.text) }));

    const renderBlock =
      (tag: "p" | "li") =>
      ({ node, children }: { node?: unknown; children?: ReactNode }) => {
        const haystack = normalize(nodeText(node));
        const match = needles.find((m) => m.needle.length > 0 && haystack.includes(m.needle));
        if (!match) return createElement(tag, null, children);
        return createElement(
          tag,
          { "data-claim-id": match.claimId, className: styles.block },
          children,
          <button
            key="marker"
            type="button"
            data-marker=""
            className={styles.marker}
            aria-pressed={false}
            aria-label="Show the source note for this passage"
            onClick={() => onSelectClaim(match.claimId)}
          >
            <span aria-hidden="true">◦</span>
          </button>,
        );
      };

    return { p: renderBlock("p"), li: renderBlock("li") };
  }, [marks, onSelectClaim]);

  // Memoised so an activeClaimId change doesn't re-parse the Markdown or remount its children.
  const markdown = useMemo(
    () => (
      <Markdown components={components} glossary={glossary}>
        {prose}
      </Markdown>
    ),
    [components, glossary, prose],
  );

  // Apply the active highlight imperatively (the DOM node persists, so cross-highlight state and any
  // stateful block children survive selection).
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    for (const block of root.querySelectorAll<HTMLElement>("[data-claim-id]")) {
      const active = block.dataset.claimId === activeClaimId;
      if (styles.blockActive) block.classList.toggle(styles.blockActive, active);
      if (styles.block) block.classList.toggle(styles.block, !active);
      block.querySelector("[data-marker]")?.setAttribute("aria-pressed", String(active));
    }
  }, [activeClaimId, markdown]);

  if (!prose.trim()) return null;
  return <div ref={containerRef}>{markdown}</div>;
}
