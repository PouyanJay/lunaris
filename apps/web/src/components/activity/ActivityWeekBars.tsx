import type { WeekDay } from "../../lib/activity";
import { parseLocalDate } from "../../lib/activityFeed";
import styles from "./ActivityWeekBars.module.css";

interface ActivityWeekBarsProps {
  week: WeekDay[];
}

const BAR_AREA_PX = 96;
const MIN_BAR_PX = 4;

const weekdayLetter = new Intl.DateTimeFormat(undefined, { weekday: "narrow" });
const dayLabel = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "short", day: "numeric" });

function isToday(date: string): boolean {
  return parseLocalDate(date).toDateString() === new Date().toDateString();
}

/** The current week's study minutes, Monday-first — today's bar is the accent, past days the
 *  deep amber, zero days a muted stub. Single series, so no legend; each bar carries its
 *  reading as a tooltip and the chart exposes a full accessible description. */
export function ActivityWeekBars({ week }: ActivityWeekBarsProps) {
  const max = Math.max(...week.map((day) => day.minutes), 1);
  const reading = (day: WeekDay) =>
    `${dayLabel.format(parseLocalDate(day.date))}: ${day.minutes} min`;
  return (
    <div
      className={styles.chart}
      role="img"
      aria-label={`Study minutes this week: ${week.map(reading).join(", ")}`}
    >
      {week.map((day) => (
        <div key={day.date} className={styles.column} title={reading(day)}>
          <div className={styles.barArea}>
            <div
              className={styles.bar}
              data-today={isToday(day.date) || undefined}
              data-empty={day.minutes === 0 || undefined}
              style={{
                height: `${Math.max(MIN_BAR_PX, Math.round((day.minutes / max) * BAR_AREA_PX))}px`,
              }}
            />
          </div>
          <span className={styles.day} aria-hidden="true">
            {weekdayLetter.format(parseLocalDate(day.date))}
          </span>
        </div>
      ))}
    </div>
  );
}
