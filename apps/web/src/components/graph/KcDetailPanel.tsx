import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { difficultyTier, orderInPath, UNKNOWN_ORDER } from "../../lib/graphLayout";
import type { Course, KnowledgeComponent } from "../../types/course";
import styles from "./KcDetailPanel.module.css";

interface KcDetailPanelProps {
  course: Course;
  selectedId: string;
  onClose: () => void;
}

/** Right-docked inspector for the selected concept: its place in the path, what it needs,
 *  what it unlocks, the modules that teach it, and its grounding sources. */
export function KcDetailPanel({ course, selectedId, onClose }: KcDetailPanelProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const { graph, modules, provenance } = course;

  const kc = useMemo(
    () => graph.nodes.find((node) => node.id === selectedId),
    [graph.nodes, selectedId],
  );

  const byId = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const prerequisites = useMemo(
    () =>
      graph.edges
        .filter((edge) => edge.to === selectedId)
        .map((edge) => ({ kc: byId.get(edge.from), strength: edge.strength }))
        .filter((entry): entry is { kc: KnowledgeComponent; strength: number } =>
          Boolean(entry.kc),
        ),
    [graph.edges, byId, selectedId],
  );
  const unlocks = useMemo(
    () =>
      graph.edges
        .filter((edge) => edge.from === selectedId)
        .map((edge) => byId.get(edge.to))
        .filter((node): node is KnowledgeComponent => Boolean(node)),
    [graph.edges, byId, selectedId],
  );
  const coveringModules = useMemo(
    () => modules.filter((module) => module.kcs.includes(selectedId)),
    [modules, selectedId],
  );
  const sources = useMemo(
    () => provenance.filter((citation) => kc?.sources.includes(citation.id)),
    [provenance, kc],
  );

  // Move focus into the panel when the selection changes, so keyboard users land here.
  useEffect(() => {
    closeRef.current?.focus();
  }, [selectedId]);

  // Esc closes the panel.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!kc) return null;
  const order = orderInPath(graph.topoOrder, kc.id);
  const tier = difficultyTier(kc.difficulty);

  return (
    <aside className={styles.panel} aria-label={`Details for ${kc.label}`}>
      <header className={styles.header}>
        <div>
          <span className="eyebrow">Knowledge component</span>
          <h2 className={styles.title}>{kc.label}</h2>
          <span className={`${styles.id} mono`}>{kc.id}</span>
        </div>
        <button
          ref={closeRef}
          type="button"
          className={styles.close}
          aria-label="Close details"
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

      <dl className={styles.metrics}>
        <div className={styles.metric}>
          <dt className="eyebrow">Difficulty</dt>
          <dd className={`${styles.metricValue} mono`}>
            <span className={styles.tierDot} style={{ background: `var(--tier-${tier})` }} />
            {Math.round(kc.difficulty * 100)}%
          </dd>
        </div>
        <div className={styles.metric}>
          <dt className="eyebrow">Bloom</dt>
          <dd className={`${styles.metricValue} mono`}>{kc.bloomCeiling.toUpperCase()}</dd>
        </div>
        <div className={styles.metric}>
          <dt className="eyebrow">Order</dt>
          <dd className={`${styles.metricValue} mono`}>
            {order > UNKNOWN_ORDER ? `#${order}` : "—"}
          </dd>
        </div>
      </dl>

      <p className={styles.definition}>{kc.definition}</p>

      <Section title={`Prerequisites · ${prerequisites.length}`}>
        {prerequisites.length === 0 ? (
          <p className={styles.empty}>None — a foundation concept.</p>
        ) : (
          <ul className={styles.list}>
            {prerequisites.map(({ kc: prereq, strength }) => (
              <li key={prereq.id} className={styles.listItem}>
                <span className={styles.listLabel}>{prereq.label}</span>
                <span className={`${styles.strength} mono`}>{strength.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Unlocks · ${unlocks.length}`}>
        {unlocks.length === 0 ? (
          <p className={styles.empty}>Nothing further depends on this yet.</p>
        ) : (
          <ul className={styles.list}>
            {unlocks.map((node) => (
              <li key={node.id} className={styles.listItem}>
                <span className={styles.listLabel}>{node.label}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Covered by · ${coveringModules.length}`}>
        {coveringModules.length === 0 ? (
          <p className={styles.empty}>No module teaches this concept yet.</p>
        ) : (
          <ul className={styles.list}>
            {coveringModules.map((module) => (
              <li key={module.id} className={styles.listItem}>
                <span className={styles.listLabel}>{module.title}</span>
                <span className={`${styles.strength} mono`}>
                  {Math.round(module.difficultyIndex * 100)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Sources · ${sources.length}`}>
        {sources.length === 0 ? (
          <p className={styles.empty}>Ungrounded — no citation registered.</p>
        ) : (
          <ul className={styles.list}>
            {sources.map((citation) => (
              <li key={citation.id} className={styles.listItem}>
                {citation.url ? (
                  <a
                    className={styles.sourceLink}
                    href={citation.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {citation.title ?? citation.url}
                  </a>
                ) : (
                  <span className={styles.listLabel}>{citation.title ?? citation.id}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </aside>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.section}>
      <h3 className={styles.sectionTitle}>{title}</h3>
      {children}
    </section>
  );
}
