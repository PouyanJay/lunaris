import { useEffect, useId, useMemo, useRef } from "react";

import { conceptLevels } from "./conceptLevels";
import { NOTES_PANEL_ID } from "./ConceptSpecPanel";
import type { ConceptGraph } from "../../lib/liveGraph";
import styles from "./ConceptMap.module.css";

interface ConceptMapProps {
  graph: ConceptGraph;
  /** The concept whose notes are open, or null when none is. */
  selectedId: string | null;
  onSelect: (conceptId: string) => void;
}

/** The compiled map, ranked by what has to be learned before what.
 *
 *  Levels rather than a list: everything on one level is learnable at the same time, which is the
 *  one structural fact a flat topological order hides — and it is the fact Phase 2's director
 *  trades on when it decides where to go next. Each concept is a real button, because opening its
 *  teaching notes is an action rather than a navigation. */
export function ConceptMap({ graph, selectedId, onSelect }: ConceptMapProps) {
  const levels = useMemo(() => conceptLevels(graph), [graph]);
  const byId = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  // Namespaced so a concept id that also exists elsewhere in the document cannot collide.
  const nameIds = useId();

  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const lastSelected = useRef<string | null>(null);

  // Closing the notes returns focus to the concept they were opened from — otherwise a keyboard
  // learner is dropped back at the top of the document and has to walk the whole map again.
  useEffect(() => {
    if (selectedId) {
      lastSelected.current = selectedId;
      return;
    }
    const previous = lastSelected.current;
    lastSelected.current = null;
    if (previous) buttons.current.get(previous)?.focus();
  }, [selectedId]);

  return (
    <div className={styles.map}>
      <header className={styles.head}>
        <p className={`eyebrow ${styles.eyebrow}`}>Concept map</p>
        <h1 className={styles.title}>{graph.topic}</h1>
        <p className={styles.meta}>
          <span className="mono">{graph.nodes.length}</span> concepts across{" "}
          <span className="mono">{levels.length}</span> levels. Everything on a level can be learned
          in any order.
        </p>
      </header>

      <ol className={styles.levels}>
        {levels.map((level) => (
          <li key={level.depth} className={styles.level}>
            <p className={`eyebrow ${styles.levelLabel}`}>
              Level <span className="mono">{String(level.depth).padStart(2, "0")}</span>
            </p>
            <ul className={styles.concepts}>
              {level.concepts.map((concept) => (
                <li key={concept.id}>
                  <button
                    type="button"
                    ref={(element) => {
                      if (element) buttons.current.set(concept.id, element);
                      else buttons.current.delete(concept.id);
                    }}
                    className={styles.concept}
                    // A disclosure, not a toggle: this opens the notes panel elsewhere on the
                    // page. `aria-controls` is set only while it is open, so it never points at an
                    // element that isn't in the document.
                    aria-expanded={selectedId === concept.id}
                    {...(selectedId === concept.id ? { "aria-controls": NOTES_PANEL_ID } : {})}
                    // Named by the concept alone. Without this the button's name is everything
                    // inside it read as one run-on — definition, dependency count, and the names of
                    // its prerequisites — so two different concepts announce almost identically.
                    aria-labelledby={`${nameIds}${concept.id}`}
                    onClick={() => onSelect(concept.id)}
                  >
                    <span id={`${nameIds}${concept.id}`} className={styles.conceptName}>
                      {concept.name}
                    </span>
                    <span className={styles.conceptDefinition}>{concept.definition}</span>
                    <span className={styles.conceptMeta}>
                      {concept.provenance === "extended" && (
                        // Structural provenance, surfaced: a concept a learner's own question added
                        // mid-session did not come from the cold compile, and the map says so.
                        <span className={`mono ${styles.added}`}>ADDED</span>
                      )}
                      <span className="mono">
                        {concept.requires.length > 0
                          ? `NEEDS ${concept.requires.length}`
                          : "STARTS HERE"}
                      </span>
                      {concept.requires.length > 0 && (
                        <span className={styles.needs}>
                          {concept.requires.map((id) => byId.get(id)?.name ?? id).join(" · ")}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
