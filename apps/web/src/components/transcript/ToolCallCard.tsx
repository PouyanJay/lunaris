import { parseToolResult } from "../../lib/toolResult";
import { ToolBody } from "./toolRenderers";
import styles from "./ToolCallCard.module.css";

interface ToolCallCardProps {
  tool: string;
  args: Record<string, unknown> | null;
  /** The tool's result summary, or null while the call is still in flight. */
  result: string | null;
}

/** One tool call in the transcript: a hairline-bordered region with the tool name (mono, the data
 *  signature) over a branded body. Known tools render through {@link toolRenderers} — concept chips,
 *  graph stats, the module list, the publish verdict — so no raw JSON reaches the user; an unknown
 *  tool degrades to {@link FallbackBody} (its args + result tucked behind a collapsed disclosure). */
export function ToolCallCard({ tool, args, result }: ToolCallCardProps) {
  const pending = result === null;

  return (
    <div className={styles.card} data-pending={pending}>
      <div className={styles.head}>
        <span className="eyebrow">Tool call</span>
        <span className={`mono ${styles.tool}`}>{tool}</span>
      </div>
      <div className={styles.body}>
        <ToolBody
          tool={tool}
          args={args}
          parsed={parseToolResult(result)}
          result={result}
          pending={pending}
        />
      </div>
    </div>
  );
}
