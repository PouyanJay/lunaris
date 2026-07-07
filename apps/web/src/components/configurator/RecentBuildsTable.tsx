import { Link } from "react-router";

import { StatusDot } from "../primitives/StatusDot";
import { relativeTime } from "../../lib/relativeTime";
import { coursePath } from "../../lib/routes";
import { RUN_STATUS_TONE } from "../../lib/runStatus";
import type { CourseRun } from "../../types/course";
import styles from "./RecentBuildsTable.module.css";

/** How many recent builds the composer table shows before deferring to the full history. */
const RECENT_LIMIT = 6;

interface RecentBuildsTableProps {
  /** The run history (newest first, from the shell's useRuns). Empty → the table is hidden. */
  runs: CourseRun[];
}

function structureLabel(run: CourseRun): string {
  const kcs = `${run.kcCount} ${run.kcCount === 1 ? "KC" : "KCs"}`;
  const modules = `${run.moduleCount} ${run.moduleCount === 1 ? "module" : "modules"}`;
  return `${kcs} · ${modules}`;
}

/** The composer's recent-builds table (P5): the last few builds as a compact, edge-to-edge table —
 *  status dot, topic (a real link into the course/build canvas), structure, and when. Sits under
 *  the composer alongside the sidebar history (which stays). Renders nothing with no builds yet. */
export function RecentBuildsTable({ runs }: RecentBuildsTableProps) {
  const recent = runs.slice(0, RECENT_LIMIT);
  if (recent.length === 0) return null;

  return (
    <section className={styles.section} aria-labelledby="recent-builds-heading">
      <h2 id="recent-builds-heading" className={`eyebrow ${styles.heading}`}>
        Recent builds
      </h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col" className={styles.statusCol}>
                Status
              </th>
              <th scope="col">Topic</th>
              <th scope="col" className={styles.structureCol}>
                Structure
              </th>
              <th scope="col" className={styles.whenCol}>
                Built
              </th>
            </tr>
          </thead>
          <tbody>
            {recent.map((run) => {
              const { tone, live } = RUN_STATUS_TONE[run.status];
              return (
                <tr key={run.runId} className={styles.row}>
                  <td>
                    <StatusDot label={run.status} tone={tone} live={live} />
                  </td>
                  <td>
                    <Link className={styles.topic} to={coursePath(run.id)}>
                      {run.topic}
                    </Link>
                  </td>
                  <td className={`${styles.structureCol} mono`}>{structureLabel(run)}</td>
                  <td className={`${styles.whenCol} mono`}>{relativeTime(run.createdAt)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
