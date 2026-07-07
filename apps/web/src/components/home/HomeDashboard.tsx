import { Link } from "react-router";

import { Button } from "../primitives/Button";
import { ErrorState } from "../states/ErrorState";
import { useLibrary, type LibraryState } from "../../hooks/useLibrary";
import { displayNameFromEmail, greetingForHour } from "../../lib/greeting";
import { ROUTES } from "../../lib/routes";
import type { CourseRun } from "../../types/course";
import styles from "./HomeDashboard.module.css";

interface HomeDashboardProps {
  apiBaseUrl: string;
  /** The signed-in caller's email — the greeting name is derived from it (offline: null). */
  userEmail: string | null;
  /** Run history from the shell's useRuns — RUNNING rows drive the live-build banner (Task 2). */
  runs: CourseRun[];
  /** Open the composer (first-run recovery + the empty state's action). */
  onNewCourse: () => void;
}

const SKELETON_CARDS = 3;

/** A neutral, honest subline until the richer mastery figure lands (Task 4). */
function subline(state: LibraryState): string {
  if (state.status !== "ready") return "Your learning workspace";
  const count = state.courses.length;
  if (count === 0) return "Your learning workspace";
  return `${count} ${count === 1 ? "course" : "courses"} in your library`;
}

/** The first-run hero: no courses yet → name a topic. A real next step, never a blank canvas. */
function FirstRunHero({ onNewCourse }: { onNewCourse: () => void }) {
  return (
    <section className={styles.firstRun}>
      <p className="eyebrow">Get started</p>
      <h3 className={styles.firstRunTitle}>Build your first course</h3>
      <p className={styles.firstRunBody}>
        Name a topic and the agent researches, plans, and writes a grounded course — it will land
        here, ready to learn.
      </p>
      <Button variant="accent" onClick={onNewCourse}>
        New course
      </Button>
    </section>
  );
}

/** The data region below the greeting — loading skeleton, recoverable error, first-run empty, or
 *  (once courses exist) the recent grid + View-all. Grows across Tasks 1–3. */
function HomeBody({
  state,
  reload,
  onNewCourse,
}: {
  state: LibraryState;
  reload: () => void;
  onNewCourse: () => void;
}) {
  if (state.status === "loading") {
    return (
      <ul className={styles.grid} aria-busy="true" aria-label="Loading your courses">
        {Array.from({ length: SKELETON_CARDS }, (_, index) => (
          <li key={index} className={styles.skeletonCard} />
        ))}
      </ul>
    );
  }

  if (state.status === "error") {
    return <ErrorState eyebrow="Home" message={state.message} onRetry={reload} />;
  }

  if (state.courses.length === 0) {
    return <FirstRunHero onNewCourse={onNewCourse} />;
  }

  return (
    <div className={styles.viewAllRow}>
      <Link className={styles.viewAll} to={ROUTES.library}>
        View all courses →
      </Link>
    </div>
  );
}

/** The Home dashboard at `/`: a greeting header over the learner's live state — the recent grid,
 *  the continue-learning hero, and the live-build banner (built up across Tasks 1–3). Reads the
 *  Phase 3 courses API via useLibrary; the composer now lives at /new. */
export function HomeDashboard({ apiBaseUrl, userEmail, onNewCourse }: HomeDashboardProps) {
  const { state, reload } = useLibrary(apiBaseUrl);
  const name = displayNameFromEmail(userEmail);
  const greeting = greetingForHour(new Date().getHours());

  return (
    <div className={styles.canvas}>
      <header className={styles.greeting}>
        <h2 className={styles.title}>
          Good {greeting}, {name}
        </h2>
        <p className={styles.subline}>{subline(state)}</p>
      </header>
      <HomeBody state={state} reload={reload} onNewCourse={onNewCourse} />
    </div>
  );
}
