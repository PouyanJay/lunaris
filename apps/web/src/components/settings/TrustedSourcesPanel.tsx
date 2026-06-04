import { useId, useState } from "react";

import { AuthoritiesError, deleteAuthority, upsertAuthority } from "../../lib/authorities";
import { useAuthorities } from "../../hooks/useAuthorities";
import type {
  AuthorityKind,
  SourceAuthority,
  SourceType,
  SubjectField,
  TrustTier,
} from "../../types/course";
import { Button } from "../primitives/Button";
import { SourceTrust } from "../primitives/SourceTrust";
import styles from "./TrustedSources.module.css";

interface TrustedSourcesPanelProps {
  apiBaseUrl: string;
}

const KINDS: { value: AuthorityKind; label: string }[] = [
  { value: "spine", label: "Spine (every topic)" },
  { value: "pack", label: "Field pack" },
  { value: "denylist", label: "Denylist (never used)" },
];
const FIELDS: { value: SubjectField; label: string }[] = [
  { value: "cs_ml", label: "CS / ML / AI" },
  { value: "medicine", label: "Medicine" },
  { value: "physics", label: "Physics" },
  { value: "chemistry", label: "Chemistry" },
  { value: "shared", label: "Shared (multidisciplinary)" },
];
const TIERS: TrustTier[] = ["official", "reputable", "open", "blocked", "vouched"];
const SOURCE_TYPES: SourceType[] = [
  "peer_reviewed",
  "preprint",
  "official",
  "database",
  "docs",
  "reference",
  "web",
];
const KIND_GROUPS: { kind: AuthorityKind; heading: string }[] = [
  { kind: "spine", heading: "Universal spine" },
  { kind: "pack", heading: "Field packs" },
  { kind: "denylist", heading: "Denylist" },
];

interface Draft {
  domain: string;
  kind: AuthorityKind;
  field: SubjectField;
  tier: TrustTier;
  sourceType: SourceType | "";
  note: string;
}

const EMPTY_DRAFT: Draft = {
  domain: "",
  kind: "spine",
  field: "cs_ml",
  tier: "reputable",
  sourceType: "",
  note: "",
};

function draftToAuthority(draft: Draft): SourceAuthority {
  const isPack = draft.kind === "pack";
  return {
    domain: draft.domain.trim().toLowerCase(),
    kind: draft.kind,
    tier: draft.tier,
    field: isPack ? draft.field : null,
    sourceType: draft.sourceType === "" ? null : draft.sourceType,
    note: draft.note.trim() === "" ? null : draft.note.trim(),
  };
}

const sourceTypeLabel = (value: SourceType): string => value.replace(/_/g, " ");
const fieldLabel = (value: SubjectField): string =>
  FIELDS.find((f) => f.value === value)?.label ?? value;

/** The global trust-config admin (P6.2 §4a): the editable spine + field packs + denylist that the
 *  credibility scorer reads. Add/replace a domain's authority tier or remove it. A spine/pack hit is
 *  a tier *prior* — it never inflates a source's credibility; the verifier's risk-tiered floor is
 *  what actually gates evidence. */
export function TrustedSourcesPanel({ apiBaseUrl }: TrustedSourcesPanelProps) {
  const { state, reload } = useAuthorities(apiBaseUrl);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "ok" | "error"; message: string } | null>(null);
  const formId = useId();

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((prev) => ({ ...prev, [key]: value }));

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (draft.domain.trim() === "" || saving) return;
    setSaving(true);
    setFeedback(null);
    try {
      const saved = await upsertAuthority(apiBaseUrl, draftToAuthority(draft));
      setFeedback({ tone: "ok", message: `Saved ${saved.domain}.` });
      setDraft(EMPTY_DRAFT);
      reload();
    } catch (error: unknown) {
      const message =
        error instanceof AuthoritiesError ? error.message : "Couldn't save the entry.";
      setFeedback({ tone: "error", message });
    } finally {
      setSaving(false);
    }
  }

  async function onEdit(authority: SourceAuthority) {
    setDraft({
      domain: authority.domain,
      kind: authority.kind,
      field: authority.field ?? "cs_ml",
      tier: authority.tier,
      sourceType: authority.sourceType ?? "",
      note: authority.note ?? "",
    });
    setFeedback(null);
  }

  async function onDelete(authority: SourceAuthority) {
    setFeedback(null);
    try {
      await deleteAuthority(apiBaseUrl, authority.domain, authority.field);
      reload();
    } catch (error: unknown) {
      const message =
        error instanceof AuthoritiesError ? error.message : "Couldn't remove the entry.";
      setFeedback({ tone: "error", message });
    }
  }

  const authorities = state.status === "ready" ? state.authorities : [];

  return (
    <section className={styles.panel} aria-labelledby="trusted-sources-heading">
      <header className={styles.header}>
        <div>
          <span className="eyebrow">Trusted sources</span>
          <h2 id="trusted-sources-heading" className={styles.title}>
            Source authority config
          </h2>
        </div>
      </header>
      <p className={styles.note}>
        The editable allow / deny list the grounding scorer reads. A spine or pack entry sets a
        domain&rsquo;s trust tier (a prior, not a credibility boost); a denylist entry is never
        used.
      </p>

      <form
        className={styles.form}
        onSubmit={onSubmit}
        aria-label="Add or replace a trusted source"
      >
        <div className={styles.row}>
          <label className={styles.fieldLabel} htmlFor={`${formId}-domain`}>
            Domain
            <input
              id={`${formId}-domain`}
              className={styles.input}
              value={draft.domain}
              onChange={(e) => set("domain", e.target.value)}
              placeholder="en.wikipedia.org"
              autoComplete="off"
              spellCheck={false}
              required
            />
          </label>
          <label className={styles.fieldLabel} htmlFor={`${formId}-kind`}>
            Kind
            <select
              id={`${formId}-kind`}
              className={styles.input}
              value={draft.kind}
              onChange={(e) => set("kind", e.target.value as AuthorityKind)}
            >
              {KINDS.map((k) => (
                <option key={k.value} value={k.value}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className={styles.row}>
          {draft.kind === "pack" && (
            <label className={styles.fieldLabel} htmlFor={`${formId}-field`}>
              Field
              <select
                id={`${formId}-field`}
                className={styles.input}
                value={draft.field}
                onChange={(e) => set("field", e.target.value as SubjectField)}
              >
                {FIELDS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className={styles.fieldLabel} htmlFor={`${formId}-tier`}>
            Tier
            <select
              id={`${formId}-tier`}
              className={styles.input}
              value={draft.tier}
              onChange={(e) => set("tier", e.target.value as TrustTier)}
            >
              {TIERS.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className={styles.fieldLabel} htmlFor={`${formId}-type`}>
            Source type (optional)
            <select
              id={`${formId}-type`}
              className={styles.input}
              value={draft.sourceType}
              onChange={(e) => set("sourceType", e.target.value as SourceType | "")}
            >
              <option value="">—</option>
              {SOURCE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {sourceTypeLabel(t)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className={styles.fieldLabel} htmlFor={`${formId}-note`}>
          Note (optional)
          <input
            id={`${formId}-note`}
            className={styles.input}
            value={draft.note}
            onChange={(e) => set("note", e.target.value)}
            placeholder="Why this domain is trusted / blocked"
            autoComplete="off"
          />
        </label>
        <div className={styles.actions}>
          <Button type="submit" variant="accent" disabled={saving || draft.domain.trim() === ""}>
            {saving ? "Saving…" : "Save entry"}
          </Button>
          {feedback && (
            <span
              className={feedback.tone === "ok" ? styles.feedbackOk : styles.feedbackError}
              role={feedback.tone === "error" ? "alert" : "status"}
            >
              {feedback.message}
            </span>
          )}
        </div>
      </form>

      {state.status === "loading" && <p className={styles.muted}>Loading trusted sources…</p>}
      {state.status === "error" && (
        <div className={styles.stateBlock} role="alert">
          <p className={styles.error}>{state.message}</p>
          <Button type="button" onClick={reload}>
            Try again
          </Button>
        </div>
      )}
      {state.status === "empty" && (
        <p className={styles.muted}>
          No trusted sources configured yet. Add one above — or rely on the built-in domain
          heuristics until you do.
        </p>
      )}
      {state.status === "ready" && (
        <div className={styles.groups}>
          {KIND_GROUPS.map(({ kind, heading }) => {
            const rows = authorities.filter((a) => a.kind === kind);
            if (rows.length === 0) return null;
            return (
              <div key={kind} className={styles.group}>
                <h3 className={styles.groupHeading}>{heading}</h3>
                <ul className={styles.list}>
                  {rows.map((authority) => (
                    <li
                      key={`${authority.domain}:${authority.field ?? ""}`}
                      className={styles.item}
                    >
                      <div className={styles.itemMain}>
                        <span className={`mono ${styles.domain}`}>{authority.domain}</span>
                        <span className={styles.trust}>
                          <SourceTrust tier={authority.tier} />
                        </span>
                        {authority.field && (
                          <span className={styles.meta}>{fieldLabel(authority.field)}</span>
                        )}
                        {authority.sourceType && (
                          <span className={styles.meta}>
                            {sourceTypeLabel(authority.sourceType)}
                          </span>
                        )}
                      </div>
                      {authority.note && <p className={styles.itemNote}>{authority.note}</p>}
                      <div className={styles.itemActions}>
                        <Button
                          type="button"
                          onClick={() => onEdit(authority)}
                          aria-label={`Edit ${authority.domain}`}
                        >
                          Edit
                        </Button>
                        <Button
                          type="button"
                          variant="danger"
                          onClick={() => onDelete(authority)}
                          aria-label={`Remove ${authority.domain}`}
                        >
                          Remove
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
