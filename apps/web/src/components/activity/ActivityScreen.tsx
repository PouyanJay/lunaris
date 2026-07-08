import { Panel } from "../primitives/Panel";
import { CanvasNotice } from "../states/CanvasNotice";
import { ErrorState } from "../states/ErrorState";
import { useActivity } from "../../hooks/useActivity";
import type { ActivityFeedItem, ActivityView } from "../../lib/activity";
import styles from "./ActivityScreen.module.css";

interface ActivityScreenProps {
  apiBaseUrl: string;
  /** The empty state's next step — a fresh account has nothing to show but somewhere to go. */
  onBrowseCourses: () => void;
}

/** True only when every derived figure is genuinely zero — the designed empty state then replaces
 *  zero-tiles pretending to be data (honest-data rule). */
function isEmptyView(view: ActivityView): boolean {
  const { stats } = view;
  return (
    view.feed.length === 0 &&
    view.heat.every((day) => !day.active) &&
    view.week.every((day) => day.minutes === 0) &&
    stats.currentStreak === 0 &&
    stats.longestStreak === 0 &&
    stats.minutesThisWeek === 0 &&
    stats.conceptsThisWeek === 0
  );
}

function feedLine(item: ActivityFeedItem): string {
  const subject = item.lessonTitle ?? item.courseTitle ?? item.courseId;
  return `${item.eventType} · ${subject}`;
}

/** The Activity canvas: streaks, study minutes, and the recent-events feed, derived from real
 *  telemetry rows only. Walking-skeleton form — the designed tiles/heat/bars land next. */
export function ActivityScreen({ apiBaseUrl, onBrowseCourses }: ActivityScreenProps) {
  const { state, reload } = useActivity(apiBaseUrl);

  const body = (() => {
    if (state.status === "loading") {
      return (
        <div className={styles.skeleton} aria-busy="true" aria-label="Loading activity">
          <div className={styles.skeletonTiles}>
            {Array.from({ length: 4 }, (_, i) => (
              <div key={i} className={styles.skeletonTile} />
            ))}
          </div>
          <div className={styles.skeletonPanels}>
            <div className={styles.skeletonPanel} />
            <div className={styles.skeletonPanel} />
          </div>
          <div className={styles.skeletonFeed} />
        </div>
      );
    }
    if (state.status === "error") {
      return <ErrorState eyebrow="Activity" message={state.message} onRetry={reload} />;
    }
    if (isEmptyView(state.view)) {
      return (
        <CanvasNotice
          eyebrow="No history yet"
          title="No activity yet"
          body="Open a lesson and your streaks, study minutes, and mastered concepts start counting here."
          actionLabel="Browse my courses"
          onAction={onBrowseCourses}
        />
      );
    }
    return (
      <Panel heading="Recent">
        <ul className={styles.feedList}>
          {state.view.feed.map((item, index) => (
            <li key={index} className={styles.feedRow}>
              <span className={styles.feedText}>{feedLine(item)}</span>
            </li>
          ))}
        </ul>
      </Panel>
    );
  })();

  return (
    <div className={styles.canvas}>
      <div className={styles.inner}>
        <p className={styles.subline}>Your learning, day by day.</p>
        {body}
      </div>
    </div>
  );
}
