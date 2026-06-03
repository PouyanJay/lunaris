import type { ReactNode } from "react";

import { LunarSpinner } from "./LunarSpinner";
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

/** Humanise an enum token for display: "in_depth" → "in depth". */
function pretty(token: string): string {
  return token.replace(/_/g, " ");
}

/** A source URL's host for compact display, www stripped: "https://www.x.gov/a" → "x.gov". */
function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
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
  complete: "ok",
  review: "warn",
  revise: "warn",
  partial: "warn",
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

/** The in-flight indicator: the branded moon spinner + "running…". Shared by every renderer and the
 *  fallback. (The literal "running…" stays here; the cycling personality lives in the phase header.) */
function Pending() {
  return (
    <span className={styles.pending}>
      <LunarSpinner size={9} />
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

/** `interpret_request` → the interpreted brief as a compact card: subject, goal, target (level +
 *  any named standard), assumed prior, and a summary of the deliverable shape + preferences. */
const renderInterpretRequest: ToolRenderer = ({ args, parsed, pending }) => {
  if (pending) return <Pending />;
  const subject = parsed && asString(parsed.subject);
  const goal = parsed && asString(parsed.goal);
  if (!subject && !goal) {
    // The brief result was truncated/unparseable — fall back to the request from the call args
    // (the same lean-on-args degradation the graph renderer uses), never an empty card.
    const request = args && asString(args.request);
    return request ? <Field label="Request">{request}</Field> : <Stat>interpreted</Stat>;
  }
  const level = (parsed && asString(parsed.targetLevel)) ?? null;
  const standardName = asString(asRecord(parsed?.targetStandard)?.name);
  const assumedPrior = parsed && asString(parsed.assumedPrior);
  const target = [level && level !== "n/a" ? pretty(level) : null, standardName]
    .filter(Boolean)
    .join(" · ");
  const lessons = asNumber(asRecord(parsed?.deliverableShape)?.lessons);
  const prefs = asRecord(parsed?.preferences);
  const detailDepth = prefs ? asString(prefs.detailDepth) : null;
  const languageStyle = prefs ? asString(prefs.languageStyle) : null;
  const bits = [
    lessons !== null ? `${lessons} lessons` : null,
    detailDepth ? pretty(detailDepth) : null,
    languageStyle ? pretty(languageStyle) : null,
    parsed?.needsResearch === true ? "needs research" : null,
  ].filter(Boolean);
  return (
    <>
      {subject && <Field label="Subject">{subject}</Field>}
      {goal && <Field label="Goal">{goal}</Field>}
      {target && <Field label="Target">{target}</Field>}
      {assumedPrior && <Field label="Assumes">{assumedPrior}</Field>}
      {bits.length > 0 && <Stat>{bits.join(" · ")}</Stat>}
    </>
  );
};

/** `model_learner` → the inferred frontier: the areas the learner already knows (and the course
 *  will skip), or a novice note when the frontier is empty. */
const renderModelLearner: ToolRenderer = ({ parsed, pending }) => {
  if (pending) return <Pending />;
  const frontier = (asArray(parsed?.frontier) ?? []).filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  );
  if (frontier.length === 0) {
    return <Stat>novice — teaching from the foundations</Stat>;
  }
  return (
    <>
      <Chips items={frontier.map((label) => ({ id: label, label, goal: false }))} />
      <Stat>
        assumes {frontier.length} known area{frontier.length === 1 ? "" : "s"} — skipped
      </Stat>
    </>
  );
};

interface SourceLike {
  url: string;
  trustTier: string;
}

/** Pull `{url, trustTier}` vetted sources out of the result array, skipping url-less entries. */
function asSources(value: unknown): SourceLike[] {
  const list = asArray(value);
  if (!list) return [];
  return list.flatMap((item) => {
    const record = asRecord(item);
    const url = record && asString(record.url);
    if (!url) return [];
    return [{ url, trustTier: (record && asString(record.trustTier)) ?? "open" }];
  });
}

/** Filter a result array down to its non-empty strings (competencies / score lines). */
function asStrings(value: unknown): string[] {
  return (asArray(value) ?? []).filter(
    (item): item is string => typeof item === "string" && item.length > 0,
  );
}

/** `research_standard` → the grounding: a status, the researched competency chips, any score/
 *  threshold lines, and the source-vetting table (each vetted source's domain + its classified
 *  trust tier). When no source met the bar the stage degrades honestly to a plain note. */
const renderResearchStandard: ToolRenderer = ({ parsed, pending }) => {
  if (pending) return <Pending />;
  const status = (parsed && asString(parsed.status)) ?? null;
  if (status === "unavailable") {
    return <Stat>no source met the bar — designing from general knowledge</Stat>;
  }
  const competencies = asStrings(parsed?.competencies);
  const scoreTable = asStrings(parsed?.scoreTable);
  const sources = asSources(parsed?.sources);
  return (
    <>
      <div className={styles.statusRow}>
        {status && <StatusTag status={status} />}
        {competencies.length > 0 && (
          <span className={`mono ${styles.stat}`}>
            {competencies.length} competenc{competencies.length === 1 ? "y" : "ies"}
          </span>
        )}
      </div>
      {competencies.length > 0 && (
        <Chips items={competencies.map((label) => ({ id: label, label, goal: false }))} />
      )}
      {scoreTable.length > 0 && <Stat>{scoreTable.join(" · ")}</Stat>}
      {sources.length > 0 && (
        <ul className={styles.sources}>
          {sources.map((source) => (
            <li key={source.url} className={styles.source}>
              <span className={`mono ${styles.sourceDomain}`}>{host(source.url)}</span>
              <span className={`mono ${styles.trustTier}`} data-tier={source.trustTier}>
                {source.trustTier}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
};

/** The renderer registry, keyed by tool name. A tool with no entry uses the raw fallback body. */
const toolRenderers: Record<string, ToolRenderer> = {
  interpret_request: renderInterpretRequest,
  research_standard: renderResearchStandard,
  model_learner: renderModelLearner,
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
