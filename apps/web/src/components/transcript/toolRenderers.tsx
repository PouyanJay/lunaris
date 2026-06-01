import type { ReactNode } from "react";

import styles from "./toolRenderers.module.css";

/** What a per-tool renderer is handed: the (full, untruncated) call args, the result parsed into a
 *  record when it was intact JSON, the raw result string, and whether the call is still in flight. */
export interface ToolRenderContext {
  args: Record<string, unknown> | null;
  parsed: Record<string, unknown> | null;
  result: string | null;
  pending: boolean;
}

type ToolRenderer = (ctx: ToolRenderContext) => ReactNode;

// ─── Safe readers ──────────────────────────────────────────────────────────
// Tool args/results are untyped wire data; read defensively and degrade rather than throw.

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

interface ConceptLike {
  id: string;
  label: string;
}

/** Pull `{id, label}` concepts out of an args/result array, skipping malformed entries. */
function asConcepts(value: unknown): ConceptLike[] {
  const list = asArray(value);
  if (!list) return [];
  return list.flatMap((item) => {
    const record = asRecord(item);
    const id = record && asString(record.id);
    if (!id) return [];
    return [{ id, label: (record && asString(record.label)) ?? id }];
  });
}

// ─── Shared presentational primitives ───────────────────────────────────────

interface ChipItem {
  id: string;
  label: string;
  goal: boolean;
}

/** Mono ghost chips — the branded stand-in for a dumped array. The goal concept is accented. */
function Chips({ items }: { items: ChipItem[] }) {
  return (
    <ul className={styles.chips}>
      {items.map((item) => (
        <li
          key={item.id}
          className={`mono ${styles.chip}`}
          data-tone={item.goal ? "goal" : "default"}
        >
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** A one-line mono summary of a tool's outcome (e.g. "21 concepts · 27 edges · acyclic"). */
function Stat({ children }: { children: ReactNode }) {
  return <p className={`mono ${styles.stat}`}>{children}</p>;
}

/** A labelled value: an uppercase eyebrow over the value (e.g. Topic, Delegated to). */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <span className="eyebrow">{label}</span>
      <span className={styles.fieldValue}>{children}</span>
    </div>
  );
}

type StatusTone = "ok" | "warn" | "danger" | "neutral";

const STATUS_TONES: Record<string, StatusTone> = {
  published: "ok",
  supported: "ok",
  review: "warn",
  revise: "warn",
  cut: "danger",
  failed: "danger",
};

/** A status as a dot + uppercase-mono label (the design system's reserved status form, never a pill). */
function StatusTag({ status }: { status: string }) {
  const tone = STATUS_TONES[status.toLowerCase()] ?? "neutral";
  return (
    <span className={styles.status} data-tone={tone}>
      <span className={styles.statusDot} aria-hidden="true" />
      <span className="mono eyebrow">{status}</span>
    </span>
  );
}

/** The in-flight indicator: a spinner + "running…". Shared by every renderer and the fallback. */
function Pending() {
  return (
    <span className={styles.pending}>
      <span className={styles.spinner} aria-hidden="true" />
      <span className="mono">running…</span>
    </span>
  );
}

/** Render an argument value compactly: strings as-is, everything else as condensed JSON. */
function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

/** The default body for a tool with no branded renderer: the raw args + result tucked behind a
 *  collapsed disclosure (no JSON dumped open), plus the running indicator while in flight. */
function FallbackBody({ args, result, pending }: Omit<ToolRenderContext, "parsed">) {
  const entries = args ? Object.entries(args) : [];
  const hasResult = result !== null && result !== "";
  const hasRaw = entries.length > 0 || hasResult;
  return (
    <>
      {hasRaw && (
        <details className={styles.raw}>
          <summary className={styles.rawSummary}>
            <span className="eyebrow">Details</span>
          </summary>
          {entries.length > 0 && (
            <dl className={styles.args}>
              {entries.map(([key, value]) => (
                <div key={key} className={styles.arg}>
                  <dt className={`mono ${styles.argKey}`}>{key}</dt>
                  <dd className={`mono ${styles.argValue}`}>{formatValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
          {hasResult && <p className={`mono ${styles.rawResult}`}>{result}</p>}
        </details>
      )}
      {pending ? <Pending /> : !hasRaw && <Stat>done</Stat>}
    </>
  );
}

// ─── Per-tool renderers ──────────────────────────────────────────────────────

/** `extract_concepts` → the topic, the proposed concept chips, and the count. */
const renderExtractConcepts: ToolRenderer = ({ args, parsed, pending }) => {
  const topic = args && asString(args.topic);
  const concepts = asConcepts(parsed?.concepts);
  const count = (parsed && asNumber(parsed.count)) ?? (concepts.length || null);
  return (
    <>
      {topic && <Field label="Topic">{topic}</Field>}
      {concepts.length > 0 && <Chips items={concepts.map((c) => ({ ...c, goal: false }))} />}
      {count !== null && <Stat>{count} concepts</Stat>}
      {pending && <Pending />}
    </>
  );
};

/** `build_prerequisite_graph` → the concept chips (from the full args, marking the goal) and the
 *  graph stats. The result payload is large and arrives truncated, so the chips lean on args; edge
 *  count + acyclicity show only when the result was small enough to parse (the phase header always
 *  carries them too). */
const renderPrerequisiteGraph: ToolRenderer = ({ args, parsed, pending }) => {
  const concepts = asConcepts(args?.concepts);
  const goal = (args && asString(args.goal)) ?? null;
  const edges = asArray(parsed?.edges);
  const stats = [`${concepts.length} concepts`];
  if (edges) stats.push(`${edges.length} edges`);
  if (parsed?.isAcyclic === true) stats.push("acyclic");
  return (
    <>
      {concepts.length > 0 && (
        <Chips items={concepts.map((c) => ({ ...c, goal: c.id === goal }))} />
      )}
      <Stat>{stats.join(" · ")}</Stat>
      {pending && <Pending />}
    </>
  );
};

/** `design_curriculum` → each module by title with its KC + objective counts. */
const renderDesignCurriculum: ToolRenderer = ({ parsed, pending }) => {
  const modules = asArray(parsed?.modules) ?? [];
  const moduleCount = (parsed && asNumber(parsed.moduleCount)) ?? (modules.length || null);
  return (
    <>
      {modules.length > 0 ? (
        <ol className={styles.modules}>
          {modules.map((item, index) => {
            const record = asRecord(item);
            const title = (record && asString(record.title)) ?? `Module ${index + 1}`;
            const kcs = asArray(record?.kcs)?.length ?? 0;
            const objectives = (record && asNumber(record.objectiveCount)) ?? 0;
            return (
              <li key={(record && asString(record.id)) ?? index} className={styles.module}>
                <span className={styles.moduleTitle}>{title}</span>
                <span className={`mono ${styles.moduleMeta}`}>
                  {kcs} KCs · {objectives} objectives
                </span>
              </li>
            );
          })}
        </ol>
      ) : (
        moduleCount !== null && <Stat>{moduleCount} modules</Stat>
      )}
      {pending && <Pending />}
    </>
  );
};

/** `finalize_course` → the publish-gate verdict (status + module count) and any blocking issues. */
const renderFinalizeCourse: ToolRenderer = ({ parsed, pending }) => {
  if (pending) return <Pending />;
  const status = (parsed && asString(parsed.status)) ?? null;
  const moduleCount = parsed ? asNumber(parsed.moduleCount) : null;
  const issues = (asArray(parsed?.issues) ?? []).map(String).filter(Boolean);
  return (
    <>
      <div className={styles.statusRow}>
        {status && <StatusTag status={status} />}
        {moduleCount !== null && (
          <span className={`mono ${styles.stat}`}>{moduleCount} modules</span>
        )}
      </div>
      {issues.length > 0 && (
        <ul className={styles.issues}>
          {issues.map((issue) => (
            <li key={issue} className={styles.issue}>
              {issue}
            </li>
          ))}
        </ul>
      )}
    </>
  );
};

/** `verify_claims` → the supported-vs-cut tally (the publish gate). Falls back to the submitted
 *  claim count from args when the result is too large to parse. */
const renderVerifyClaims: ToolRenderer = ({ args, parsed, pending }) => {
  if (pending) {
    const submitted = asArray(args?.claims)?.length ?? 0;
    return (
      <>
        {submitted > 0 && <Stat>verifying {submitted} claims</Stat>}
        <Pending />
      </>
    );
  }
  const results = asArray(parsed?.results);
  if (!results) {
    const submitted = asArray(args?.claims)?.length ?? 0;
    return submitted > 0 ? <Stat>{submitted} claims verified</Stat> : <Stat>done</Stat>;
  }
  const supported = results.filter((r) => asRecord(r)?.status === "supported").length;
  const cut = results.length - supported;
  return (
    <p className={styles.tally}>
      <span className={`mono ${styles.tallyItem}`} data-tone="ok">
        {supported} supported
      </span>
      <span className={`mono ${styles.tallyItem}`} data-tone="danger">
        {cut} cut
      </span>
    </p>
  );
};

/** `task` → the delegated subagent and what it was asked to do (and its summary once it returns). */
const renderTask: ToolRenderer = ({ args, result, pending }) => {
  const subagent = (args && asString(args.subagent_type)) ?? null;
  const description = (args && asString(args.description)) ?? null;
  return (
    <>
      {subagent && <Field label="Delegated to">{subagent}</Field>}
      {description && <p className={styles.description}>{description}</p>}
      {pending ? <Pending /> : result && <Stat>{result}</Stat>}
    </>
  );
};

/** The renderer registry, keyed by tool name. A tool with no entry uses the raw fallback body. */
const toolRenderers: Record<string, ToolRenderer> = {
  extract_concepts: renderExtractConcepts,
  build_prerequisite_graph: renderPrerequisiteGraph,
  design_curriculum: renderDesignCurriculum,
  finalize_course: renderFinalizeCourse,
  verify_claims: renderVerifyClaims,
  task: renderTask,
};

/** A tool call's body: the branded per-tool view when one is registered, else the raw fallback
 *  (args + result behind a collapsed disclosure). The single entry point {@link ToolCallCard} uses. */
export function ToolBody({
  tool,
  args,
  parsed,
  result,
  pending,
}: { tool: string } & ToolRenderContext) {
  const renderer = toolRenderers[tool];
  if (renderer) return renderer({ args, parsed, result, pending });
  return <FallbackBody args={args} result={result} pending={pending} />;
}
