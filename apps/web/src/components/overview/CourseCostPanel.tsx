import { useState } from "react";

import { useCourseCost } from "../../hooks/useCourseCost";
import { useCourseCostEvents } from "../../hooks/useCourseCostEvents";
import { money } from "../../lib/cost";
import type { CostBreakdown, CostEvent, CourseCost } from "../../lib/cost";
import { Button } from "../primitives/Button";
import styles from "./CourseCostPanel.module.css";

interface CourseCostPanelProps {
  /** The API origin; the panel is only rendered when this is present (a signed read needs it). */
  apiBaseUrl: string;
  courseId: string;
}

/** Human labels for the raw provider / pocket identifiers the ledger stores. Unknown providers fall
 *  back to their capitalized key, so a new seam still renders sanely before it's mapped here. */
const PROVIDER_LABEL: Record<string, string> = {
  anthropic: "Claude",
  voyage: "Embeddings",
  tavily: "Web search",
  openai: "Cover image",
  elevenlabs: "Voiceover",
  manim: "Video render",
  local: "Local (keyless)",
};

const POCKET_LABEL: Record<string, string> = {
  user_key: "Your key",
  platform: "Platform",
};

function providerLabel(key: string): string {
  return PROVIDER_LABEL[key] ?? key.charAt(0).toUpperCase() + key.slice(1);
}

function pocketLabel(key: string): string {
  return POCKET_LABEL[key] ?? key;
}

/** Compact usage summary for a ledger row, e.g. "1,000 input_tokens · 200 output_tokens". */
function usageSummary(usage: Record<string, number>): string {
  return Object.entries(usage)
    .map(([unit, value]) => `${value.toLocaleString()} ${unit}`)
    .join(" · ");
}

/** A course was built keyless (local models) when it recorded calls but they cost nothing. */
function isKeylessBuild(cost: CourseCost): boolean {
  return cost.totalAmount <= 0 && cost.breakdown.eventCount > 0;
}

/**
 * The build-cost panel on the course Overview: the calculated total, the who-paid split, a
 * per-provider breakdown, and an on-demand drill-through into the full ledger. Renders every data
 * state — loading, loaded, "not metered" (a pre-feature course), a keyless "~$0" build, and a load
 * error with retry.
 */
export function CourseCostPanel({ apiBaseUrl, courseId }: CourseCostPanelProps) {
  const { state, reload } = useCourseCost(apiBaseUrl, courseId);

  return (
    <section className={styles.panel} aria-label="Build cost">
      <p className="eyebrow">Build cost</p>
      {state.status === "loading" && (
        <p className={styles.status} role="status" aria-live="polite">
          Loading…
        </p>
      )}
      {state.status === "error" && (
        <div className={styles.status}>
          <p className={styles.error} role="alert">
            {state.message}
          </p>
          <Button onClick={reload}>Retry</Button>
        </div>
      )}
      {state.status === "ready" && state.cost === null && (
        <p className={styles.notMetered}>
          Not metered yet — no build cost is on record for this course.
        </p>
      )}
      {state.status === "ready" && state.cost !== null && (
        <MeteredCost apiBaseUrl={apiBaseUrl} courseId={courseId} cost={state.cost} />
      )}
    </section>
  );
}

function MeteredCost({
  apiBaseUrl,
  courseId,
  cost,
}: {
  apiBaseUrl: string;
  courseId: string;
  cost: CourseCost;
}) {
  const [expanded, setExpanded] = useState(false);
  const keyless = isKeylessBuild(cost);

  return (
    <div className={styles.body}>
      <Headline cost={cost} keyless={keyless} />
      {keyless ? (
        <KeylessNotice />
      ) : (
        <>
          <PocketSplit breakdown={cost.breakdown} currency={cost.currency} />
          <ProviderBreakdown breakdown={cost.breakdown} currency={cost.currency} />
        </>
      )}
      <DrillToggle
        count={cost.breakdown.eventCount}
        expanded={expanded}
        onToggle={() => setExpanded((open) => !open)}
      />
      {expanded && (
        <div id="cost-ledger">
          <CostLedger apiBaseUrl={apiBaseUrl} courseId={courseId} />
        </div>
      )}
    </div>
  );
}

/** The one accent metric — the total, or "≈ $0.00" for a keyless build. */
function Headline({ cost, keyless }: { cost: CourseCost; keyless: boolean }) {
  return (
    <div className={styles.headline}>
      <p className={`${styles.total} mono`}>
        {keyless ? `≈ ${money(0, cost.currency)}` : money(cost.totalAmount, cost.currency)}
      </p>
      <p className={styles.totalLabel}>{keyless ? "keyless build" : "to build"}</p>
    </div>
  );
}

function KeylessNotice() {
  return (
    <p className={styles.keyless}>
      Ran on local models at no metered cost — measured, not missing.
    </p>
  );
}

/** The who-paid split: BYOK (the owner's key) vs Lunaris-platform spend. */
function PocketSplit({ breakdown, currency }: { breakdown: CostBreakdown; currency: string }) {
  return (
    <dl className={styles.pockets}>
      <PocketFigure
        label={pocketLabel("user_key")}
        amount={breakdown.byPocket.user_key ?? 0}
        currency={currency}
      />
      <PocketFigure
        label={pocketLabel("platform")}
        amount={breakdown.byPocket.platform ?? 0}
        currency={currency}
      />
    </dl>
  );
}

function PocketFigure({
  label,
  amount,
  currency,
}: {
  label: string;
  amount: number;
  currency: string;
}) {
  return (
    <div className={styles.pocket} role="group" aria-label={label}>
      <dd className={`${styles.pocketValue} mono`}>{money(amount, currency)}</dd>
      <dt className={styles.pocketLabel}>{label}</dt>
    </div>
  );
}

/** Per-provider subtotals as a compact instrument-style bar list, largest first. */
function ProviderBreakdown({
  breakdown,
  currency,
}: {
  breakdown: CostBreakdown;
  currency: string;
}) {
  const providers = Object.entries(breakdown.byProvider).sort(([, a], [, b]) => b - a);
  const peak = providers[0]?.[1] ?? 0;

  return (
    <ul className={styles.providers}>
      {providers.map(([key, amount]) => (
        <li key={key} className={styles.providerRow}>
          <span className={styles.providerName}>{providerLabel(key)}</span>
          <span className={styles.barTrack} aria-hidden="true">
            <span
              className={styles.barFill}
              style={{ width: `${peak > 0 ? Math.max((amount / peak) * 100, 1.5) : 0}%` }}
            />
          </span>
          <span className={`${styles.providerAmount} mono`}>{money(amount, currency)}</span>
        </li>
      ))}
    </ul>
  );
}

/** The drill-through affordance — names the call count and toggles the ledger open. */
function DrillToggle({
  count,
  expanded,
  onToggle,
}: {
  count: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={styles.drillToggle}
      aria-expanded={expanded}
      aria-controls="cost-ledger"
      onClick={onToggle}
    >
      <span className={styles.chevron} data-open={expanded} aria-hidden="true" />
      Calculated from <span className="mono">{count.toLocaleString()}</span> paid
      {count === 1 ? " call" : " calls"}
    </button>
  );
}

function CostLedger({ apiBaseUrl, courseId }: { apiBaseUrl: string; courseId: string }) {
  const { state, reload } = useCourseCostEvents(apiBaseUrl, courseId, true);

  if (state.status === "loading" || state.status === "idle") {
    return (
      <p className={styles.status} role="status" aria-live="polite">
        Loading the breakdown…
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <div className={styles.status}>
        <p className={styles.error} role="alert">
          {state.message}
        </p>
        <Button onClick={reload}>Retry</Button>
      </div>
    );
  }
  if (state.events.length === 0) {
    return <p className={styles.notMetered}>No paid calls on record.</p>;
  }
  return <CostLedgerTable events={state.events} />;
}

function CostLedgerTable({ events }: { events: CostEvent[] }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Call</th>
            <th scope="col">Provider</th>
            <th scope="col">Paid by</th>
            <th scope="col">Usage</th>
            <th scope="col" className={styles.numCol}>
              Cost
            </th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={`${event.runId}:${event.seq}`}>
              <td className="mono">{event.component}</td>
              <td>{providerLabel(event.provider)}</td>
              <td>{pocketLabel(event.pocket)}</td>
              <td className={`${styles.usageCell} mono`}>{usageSummary(event.usage)}</td>
              <td className={`${styles.numCol} mono`}>{money(event.amount, event.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
