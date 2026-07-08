import type { ActivityFeedItem } from "../../lib/activity";
import { feedLine, groupFeedByDay } from "../../lib/activityFeed";
import { relativeTime } from "../../lib/relativeTime";
import styles from "./ActivityFeed.module.css";

interface ActivityFeedProps {
  feed: ActivityFeedItem[];
}

/** Dot tone per event type. Identity is carried by the worded row (never color alone):
 *  mastered wears the accent (the celebration), completed/verified the success green, and
 *  started stays neutral — a start is a low-signal fact. */
const DOT_TONE: Record<ActivityFeedItem["eventType"], string> = {
  started: styles.dotNeutral!,
  completed: styles.dotSuccess!,
  verified: styles.dotSuccess!,
  mastered: styles.dotAccent!,
};

/** The recent-events feed, grouped by the viewer's local day (Today / Yesterday / a date). */
export function ActivityFeed({ feed }: ActivityFeedProps) {
  const groups = groupFeedByDay(feed);
  return (
    <div>
      {groups.map((group) => (
        <section key={group.label} className={styles.group} aria-label={group.label}>
          <h3 className={styles.day}>{group.label}</h3>
          <ul className={styles.list}>
            {group.items.map((item, index) => (
              <li key={index} className={styles.row}>
                <span className={`${styles.dot} ${DOT_TONE[item.eventType]}`} aria-hidden="true" />
                <span className={styles.text}>{feedLine(item)}</span>
                <time className={styles.time} dateTime={item.occurredAt}>
                  {relativeTime(item.occurredAt)}
                </time>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
