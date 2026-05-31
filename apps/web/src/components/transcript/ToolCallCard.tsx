import styles from "./ToolCallCard.module.css";

interface ToolCallCardProps {
  tool: string;
  args: Record<string, unknown> | null;
  /** The tool's result summary, or null while the call is still in flight. */
  result: string | null;
}

/** One tool call in the transcript: the tool name (mono, the data signature), its arguments, and
 *  its result — a single hairline-bordered region, not a floating card. */
export function ToolCallCard({ tool, args, result }: ToolCallCardProps) {
  const argEntries = args ? Object.entries(args) : [];
  const pending = result === null;

  return (
    <div className={styles.card} data-pending={pending}>
      <div className={styles.head}>
        <span className="eyebrow">Tool call</span>
        <span className={`mono ${styles.tool}`}>{tool}</span>
      </div>

      {argEntries.length > 0 && (
        <dl className={styles.args}>
          {argEntries.map(([key, value]) => (
            <div key={key} className={styles.arg}>
              <dt className={`mono ${styles.argKey}`}>{key}</dt>
              <dd className={`mono ${styles.argValue}`}>{formatValue(value)}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className={styles.result}>
        {pending ? (
          <span className={styles.runningResult}>
            <span className={styles.spinner} aria-hidden="true" />
            <span className="mono">running…</span>
          </span>
        ) : (
          <span className={`mono ${styles.resultText}`}>{result || "done"}</span>
        )}
      </div>
    </div>
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
