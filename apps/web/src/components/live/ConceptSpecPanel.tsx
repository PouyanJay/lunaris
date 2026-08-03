import { useEffect, useRef, type ReactNode } from "react";

import type { ConceptGraph, ConceptNode, MasteryCriterion } from "../../lib/liveGraph";
import styles from "./ConceptSpecPanel.module.css";

/** The notes panel's DOM id — referenced by the concept button's `aria-controls`, so the two are
 *  named in one place rather than by two matching string literals. */
export const NOTES_PANEL_ID = "live-concept-notes";

interface ConceptSpecPanelProps {
  graph: ConceptGraph;
  concept: ConceptNode;
  onClose: () => void;
}

/** How the criterion is evidenced, in the learner's terms. The kind is what the Phase 2 director
 *  keys its next move off, so it is shown rather than flattened into prose. */
const CRITERION_KIND: Record<MasteryCriterion["kind"], string> = {
  predict: "PREDICT",
  manipulate: "MANIPULATE",
  explain: "EXPLAIN",
};

/** How deeply the concept is meant to be taught. */
const DEPTH_COPY: Record<NonNullable<ConceptNode["teachingSpec"]>["depth"], string> = {
  intuition_first: "Intuition first",
  formal: "Formal",
  applied: "Applied",
};

/** The teaching notes for one concept — what the session will actually do with it.
 *
 *  This is the node showing its own contents: what a learner should end up able to do, the wrong
 *  models to go looking for, and the things they have to be able to *perform* to have understood
 *  it. Phase 2 teaches from exactly these fields, so a map that hid them would be a map of a
 *  curriculum nobody can inspect before sitting through it. */
export function ConceptSpecPanel({ graph, concept, onClose }: ConceptSpecPanelProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const spec = concept.teachingSpec;

  // Focus moves into the panel on open, so a keyboard learner lands on what they just opened.
  useEffect(() => {
    closeRef.current?.focus();
  }, [concept.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const needs = concept.requires.map((id) => byId.get(id)?.name ?? id);

  return (
    <aside
      id={NOTES_PANEL_ID}
      className={styles.panel}
      aria-label={`Teaching notes for ${concept.name}`}
    >
      <header className={styles.header}>
        <div className={styles.identity}>
          <p className={`eyebrow ${styles.eyebrow}`}>Concept</p>
          <h2 className={styles.title}>{concept.name}</h2>
          <p className={`mono ${styles.id}`}>{concept.id}</p>
        </div>
        <button
          ref={closeRef}
          type="button"
          className={styles.close}
          aria-label="Close teaching notes"
          onClick={onClose}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
            <path
              d="M3 3l8 8M11 3l-8 8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>

      <p className={styles.definition}>{concept.definition}</p>

      {spec ? (
        <>
          <Section title="What you'll be able to do" cue={DEPTH_COPY[spec.depth]}>
            <p className={styles.prose}>{spec.objective}</p>
          </Section>

          {spec.misconceptions.length > 0 && (
            <Section title="Where people go wrong">
              {/* Written as the learner would believe them, not as corrections — that is what lets
                  a tutor go looking for the wrong model rather than pre-empting it. */}
              <ul className={styles.list}>
                {/* Keyed by position, not by text: these are model-authored and a repeated line
                    is entirely possible — duplicate keys would drop one of them from the list. */}
                {spec.misconceptions.map((misconception, index) => (
                  <li key={index} className={styles.misconception}>
                    {misconception}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </>
      ) : (
        <Section title="What you'll be able to do">
          <p className={styles.absent}>
            No teaching notes — writing them failed for this concept. It is still on the map, and
            the session can still reach it.
          </p>
        </Section>
      )}

      {concept.masteryCriteria.length > 0 && (
        <Section title="How you'll prove it">
          <ul className={styles.list}>
            {concept.masteryCriteria.map((criterion, index) => (
              <li key={index} className={styles.criterion}>
                <span className={`mono ${styles.kind}`}>{CRITERION_KIND[criterion.kind]}</span>
                <span className={styles.prose}>{criterion.statement}</span>
                {criterion.needsSim && (
                  <span className={styles.needsSim}>Needs a simulator (Phase 3)</span>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Needs first">
        {needs.length > 0 ? (
          <ul className={styles.list}>
            {needs.map((name, index) => (
              <li key={index} className={styles.prose}>
                {name}
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.absent}>Nothing — this is a place to start.</p>
        )}
      </Section>

      {concept.aliases.length > 0 && (
        <Section title="Also called">
          <p className={styles.prose}>{concept.aliases.join(" · ")}</p>
        </Section>
      )}
    </aside>
  );
}

function Section({ title, cue, children }: { title: string; cue?: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle}>{title}</h3>
        {cue && <span className={`mono ${styles.cue}`}>{cue}</span>}
      </div>
      {children}
    </section>
  );
}
