import { useState } from "react";

import type { ProdComputePoint } from "../../lib/prodOps";
import styles from "./ProdOps.module.css";

type Metric = "replicas" | "cpuCores" | "memoryGb";

const METRICS: { key: Metric; label: string; unit: string }[] = [
  { key: "replicas", label: "Replicas", unit: "" },
  { key: "cpuCores", label: "CPU", unit: "cores" },
  { key: "memoryGb", label: "Memory", unit: "GB" },
];

const METRIC_META: Record<Metric, { label: string; unit: string }> = {
  replicas: { label: "Replicas", unit: "" },
  cpuCores: { label: "CPU", unit: "cores" },
  memoryGb: { label: "Memory", unit: "GB" },
};

function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function hourLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" });
}

/** A hand-rolled dual-axis chart (house style — no chart lib): a selectable usage metric (replicas /
 *  CPU / memory) as bars on the left axis, with amortized hourly cost overlaid as a line on the right
 *  axis. role="img" + a visually-hidden table keep it accessible. */
export function ComputeChart({
  points,
  currency,
}: {
  points: ProdComputePoint[];
  currency: string;
}) {
  const [metric, setMetric] = useState<Metric>("replicas");

  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) {
    return <p className={styles.empty}>No compute data for this window yet.</p>;
  }

  const active = METRIC_META[metric];
  const width = 100;
  const height = 40;
  const usagePeak = Math.max(...points.map((p) => p[metric]), 0.01);
  const costPeak = Math.max(...points.map((p) => p.cost), 0.001);
  const step = width / points.length;
  const costLine = points
    .map((p, i) => `${i * step + step / 2},${height - (p.cost / costPeak) * height}`)
    .join(" ");
  const caption =
    `Hourly ${active.label.toLowerCase()} usage with amortized ${currency} cost overlaid, ` +
    `${points.length} hours; usage peak ${usagePeak.toFixed(2)}, cost peak ${money(costPeak, currency)}.`;

  return (
    <figure className={styles.chartFigure}>
      <div className={styles.controls}>
        <span className={styles.controlLabel} id="compute-metric-label">
          Usage
        </span>
        <div className={styles.rangeGroup} role="group" aria-labelledby="compute-metric-label">
          {METRICS.map((m) => (
            <button
              key={m.key}
              type="button"
              className={`${styles.rangeButton} ${m.key === metric ? styles.rangeButtonActive : ""}`}
              aria-pressed={m.key === metric}
              onClick={() => setMetric(m.key)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <span className={styles.legend}>
          <span className={styles.legendBar} /> usage
          <span className={styles.legendLine} /> cost
        </span>
      </div>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={caption}
      >
        {points.map((point, i) => {
          const barHeight = Math.max((point[metric] / usagePeak) * height, 0.2);
          return (
            <rect
              key={point.hour}
              x={i * step}
              y={height - barHeight}
              width={Math.max(step - 0.15, 0.2)}
              height={barHeight}
              className={styles.bar}
            >
              <title>
                {hourLabel(point.hour)}: {point[metric].toFixed(2)} {active.unit} ·{" "}
                {money(point.cost, currency)}
              </title>
            </rect>
          );
        })}
        <polyline className={styles.costLine} points={costLine} />
      </svg>
      <figcaption className={styles.chartAxis}>
        <span className={styles.meta}>{hourLabel(first.hour)}</span>
        <span className={styles.axisPeak}>
          peak {usagePeak.toFixed(1)} {active.unit} · {money(costPeak, currency)}/h
        </span>
        <span className={styles.meta}>{hourLabel(last.hour)}</span>
      </figcaption>
      <table className="sr-only">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Hour</th>
            <th scope="col">Replicas</th>
            <th scope="col">CPU cores</th>
            <th scope="col">Memory GB</th>
            <th scope="col">Cost ({currency})</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.hour}>
              <td>{p.hour}</td>
              <td>{p.replicas}</td>
              <td>{p.cpuCores}</td>
              <td>{p.memoryGb}</td>
              <td>{p.cost.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
