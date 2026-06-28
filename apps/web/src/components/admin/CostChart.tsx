import type { ProdCostPoint } from "../../lib/prodOps";
import styles from "./ProdOps.module.css";

function money(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

function dayLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** A hand-rolled SVG bar chart of daily Azure spend (house style — no chart lib). Bars are scaled to
 *  the window's peak; the most recent day (still settling, ~8-24h lag) is drawn muted and called out
 *  as partial. role="img" + a per-bar <title> + a visually-hidden data table keep it accessible. */
export function CostChart({ points, currency }: { points: ProdCostPoint[]; currency: string }) {
  const first = points[0];
  const last = points[points.length - 1];
  if (!first || !last) {
    return <p className={styles.empty}>No cost data for this window yet.</p>;
  }

  const width = 100;
  const height = 40;
  const gap = points.length > 1 ? 0.6 : 0;
  const barWidth = (width - gap * (points.length - 1)) / points.length;
  const peak = Math.max(...points.map((p) => p.amount), 0.01);
  const total = points.reduce((sum, p) => sum + p.amount, 0);
  const caption = `Daily ${currency} spend over ${points.length} days, peak ${money(peak, currency)}.`;

  return (
    <figure className={styles.chartFigure}>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={caption}
      >
        {points.map((point, i) => {
          const barHeight = Math.max((point.amount / peak) * height, 0.4);
          const x = i * (barWidth + gap);
          const y = height - barHeight;
          return (
            <rect
              key={point.day}
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              rx={0.4}
              className={point.isPartial ? styles.barPartial : styles.bar}
            >
              <title>
                {dayLabel(point.day)}: {money(point.amount, currency)}
                {point.isPartial ? " (partial)" : ""}
              </title>
            </rect>
          );
        })}
      </svg>
      <figcaption className={styles.chartAxis}>
        <span className={styles.meta}>{dayLabel(first.day)}</span>
        <span className={styles.axisPeak}>peak {money(peak, currency)}</span>
        <span className={styles.meta}>{dayLabel(last.day)}</span>
      </figcaption>
      <table className="sr-only">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Spend ({currency})</th>
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.day}>
              <td>
                {point.day}
                {point.isPartial ? " (partial)" : ""}
              </td>
              <td>{point.amount.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={styles.total}>
        {points.length}-day total <strong>{money(total, currency)}</strong>
      </p>
    </figure>
  );
}
