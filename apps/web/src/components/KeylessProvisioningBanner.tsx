import type { KeylessReadinessStatus } from "../lib/keylessReadiness";
import { AccentBand } from "./primitives/AccentBand";
import { StatusDot } from "./primitives/StatusDot";
import styles from "./KeylessProvisioningBanner.module.css";

interface KeylessProvisioningBannerProps {
  status: KeylessReadinessStatus | null;
}

/** Shown during a keyless build while the self-hosted model server is waking from scale-to-zero
 *  (keyless-fallbacks T8). It explains the one-time cold-start wait so a stalled first build reads as
 *  "warming up", not "stuck". Renders nothing unless the endpoint reports `provisioning` — a ready,
 *  keyed (`not_applicable`), or unwired endpoint shows no banner. */
export function KeylessProvisioningBanner({ status }: KeylessProvisioningBannerProps) {
  if (status !== "provisioning") return null;

  return (
    <AccentBand className={styles.row}>
      <StatusDot label="provisioning" tone="accent" live />
      <p className={styles.text}>
        Waking up the local model for this Draft build. The first build after an idle period can take
        <span className={styles.nowrap}> ~30–60s</span> while it starts up — it speeds up once warm.
      </p>
    </AccentBand>
  );
}
