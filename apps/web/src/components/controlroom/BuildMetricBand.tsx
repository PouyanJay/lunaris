import type { ProgressEvent } from "../../types/course";
import styles from "./BuildMetricBand.module.css";

interface BuildMetricBandProps {
  events: ProgressEvent[];
}

/** The build topbar's metric band (P8): KCS / EDGES / ACYCLIC off the latest GRAPH_BUILT event.
 *  Renders nothing until the graph exists — no placeholder zeros. ACYCLIC reads from the
 *  structured payload (T1); "—" on a stream that predates it. */
export function BuildMetricBand({ events }: BuildMetricBandProps) {
  const graphEvent = [...events].reverse().find((event) => event.stage === "graph_built");
  if (!graphEvent || graphEvent.kcCount == null) return null;

  const acyclic =
    graphEvent.graph == null ? "—" : graphEvent.graph.isAcyclic ? "yes" : "no";

  return (
    <dl className={styles.band} aria-label="Graph metrics">
      <div className={styles.cell}>
        <dt className={`${styles.label} mono`}>KCS</dt>
        <dd className={`${styles.value} mono`}>{graphEvent.kcCount}</dd>
      </div>
      <div className={styles.cell}>
        <dt className={`${styles.label} mono`}>EDGES</dt>
        <dd className={`${styles.value} mono`}>{graphEvent.edgeCount ?? "—"}</dd>
      </div>
      <div className={styles.cell}>
        <dt className={`${styles.label} mono`}>ACYCLIC</dt>
        <dd className={`${styles.value} mono`} data-tone={acyclic === "yes" ? "success" : undefined}>
          {acyclic}
        </dd>
      </div>
    </dl>
  );
}
