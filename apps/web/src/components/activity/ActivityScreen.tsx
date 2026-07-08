import { Panel } from "../primitives/Panel";
import { CanvasNotice } from "../states/CanvasNotice";
import { ErrorState } from "../states/ErrorState";
import { useActivity } from "../../hooks/useActivity";
import type { ActivityView } from "../../lib/activity";
import { ActivityFeed } from "./ActivityFeed";
import { ActivityHeat } from "./ActivityHeat";
import { ActivityStatTiles } from "./ActivityStatTiles";
import { ActivityWeekBars } from "./ActivityWeekBars";
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

/** The Activity canvas: streaks, study minutes, and the recent-events feed, derived from real
 *  telemetry rows only. */
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
    const { view } = state;
    return (
      <div className={styles.instrument}>
        <ActivityStatTiles stats={view.stats} />
        <div className={styles.charts}>
          <Panel heading="Last 14 days" variant="plain">
            <ActivityHeat heat={view.heat} />
          </Panel>
          <Panel heading="Study minutes · this week" variant="plain">
            <ActivityWeekBars week={view.week} />
          </Panel>
        </div>
        <section aria-label="Recent activity">
          <h2 className={styles.recentLabel}>Recent</h2>
          <Panel variant="plain">
            {view.feed.length > 0 ? (
              <ActivityFeed feed={view.feed} />
            ) : (
              <p className={styles.quietFeed}>
                Nothing in the feed yet — finish a lesson or mark a concept understood and it
                lands here.
              </p>
            )}
          </Panel>
        </section>
      </div>
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
