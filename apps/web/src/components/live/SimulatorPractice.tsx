import type { SessionTurn } from "../../lib/liveSession";
import { InteractiveSimFrame } from "./InteractiveSimFrame";
import styles from "./SurfaceCard.module.css";

/** Practice shares the tutor's state without submitting an assessment answer. */
export function SimulatorPractice({
  app,
  active,
  busy,
}: {
  app: NonNullable<SessionTurn["practiceSim"]>;
  active: boolean;
  busy: boolean;
}) {
  if (!app.contract) return null;
  return (
    <section className={styles.card} aria-label="Simulator practice">
      <p className="eyebrow">Try it yourself</p>
      <p className={styles.ask}>{app.contract.objective}</p>
      <p className={styles.note}>
        Practice does not count toward mastery. Answer the assessment in your own words.
      </p>
      <InteractiveSimFrame
        url={app.url}
        title={app.title}
        appId={app.appId}
        contract={app.contract}
        answerable={active}
        busy={busy}
      />
    </section>
  );
}
