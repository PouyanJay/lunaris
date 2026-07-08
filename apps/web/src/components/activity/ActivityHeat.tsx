import type { HeatDay } from "../../lib/activity";
import styles from "./ActivityHeat.module.css";

interface ActivityHeatProps {
  heat: HeatDay[];
}

const dayLabel = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

/** Amber intensity for a day's minutes, scaled to the window's max (the design's 18–80% alpha
 *  ramp). An active day with no recorded minutes (marks only) gets the lowest visible step —
 *  studied is studied. */
function squareBackground(day: HeatDay, maxMinutes: number): string | undefined {
  if (!day.active) return undefined;
  const intensity = maxMinutes > 0 ? day.minutes / maxMinutes : 0;
  const percent = Math.round(18 + intensity * 62);
  return `color-mix(in srgb, var(--accent-500) ${percent}%, transparent)`;
}

/** The last-14-days heat strip: one square per day, amber by study minutes, with an honest
 *  studied-days caption. Identity is never color-alone — each square carries its reading as a
 *  tooltip and the strip has an accessible per-day description. */
export function ActivityHeat({ heat }: ActivityHeatProps) {
  const studied = heat.filter((day) => day.active).length;
  const maxMinutes = Math.max(...heat.map((day) => day.minutes), 0);
  const reading = (day: HeatDay) =>
    `${dayLabel.format(new Date(`${day.date}T00:00:00`))}: ${
      day.active ? `${day.minutes} min` : "no study"
    }`;
  return (
    <div>
      <div
        className={styles.strip}
        role="img"
        aria-label={`Last 14 days: ${heat.map(reading).join(", ")}`}
      >
        {heat.map((day) => (
          <div
            key={day.date}
            className={styles.square}
            data-active={day.active || undefined}
            style={{ background: squareBackground(day, maxMinutes) }}
            title={reading(day)}
          />
        ))}
      </div>
      <p className={styles.caption}>
        Studied {studied} of the last {heat.length} days.
      </p>
    </div>
  );
}
