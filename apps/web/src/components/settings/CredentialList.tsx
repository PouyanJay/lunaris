import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { CredentialField } from "./CredentialField";
import { SecretField } from "./SecretField";
import { credentialsForSection, type CredentialSpec } from "./credentialCatalog";
import type { SettingsSurface } from "./settingsSurface";
import type { SettingsSection } from "../../lib/routes";
import styles from "./Settings.module.css";

/** Whether a key is settable in the deployment's active mode — an operator-owned key (Supabase /
 *  LangSmith) has no BYOK field, and some keys (OpenAI) have no file-store field, so a section only
 *  shows what a user can actually set here. The single source of truth for the mode filter. */
function isSettable(spec: CredentialSpec, byokEnabled: boolean): boolean {
  return byokEnabled ? spec.byok : spec.fileStore;
}

/** One settable credential key, rendered with the right chrome for the mode: a per-user BYOK field
 *  (save / test / remove against the vault) when BYOK is on, or a write-only file-store secret field
 *  otherwise. Only ever rendered for a spec that `isSettable` in the active mode (the caller filters
 *  first), so it has no null branch. */
function CredentialRow({ spec, surface }: { spec: CredentialSpec; surface: SettingsSurface }) {
  if (surface.byokEnabled) {
    return (
      <CredentialField
        apiBaseUrl={surface.apiBaseUrl}
        provider={spec.key}
        label={spec.label}
        hint={spec.hint}
        placeholder={spec.placeholder}
        status={surface.credentialStatuses.find((s) => s.provider === spec.key)}
        onChanged={surface.onCredentialChanged}
      />
    );
  }
  return (
    <SecretField
      apiBaseUrl={surface.apiBaseUrl}
      name={spec.key}
      label={spec.label}
      hint={spec.hint}
      placeholder={spec.placeholder}
      status={surface.secrets.find((s) => s.name === spec.key)}
      onSaved={surface.onSecretSaved}
    />
  );
}

/** The credentials a section owns, in a titled disclosure with the shared write-only note. Renders
 *  nothing when the section has no settable keys in the active mode (an operator-only key set in
 *  BYOK mode, or an all-BYOK section in file-store mode), so a caller can drop it in unconditionally. */
export function CredentialList({
  section,
  surface,
  eyebrow = "Keys",
  title = "API keys",
}: {
  section: SettingsSection;
  surface: SettingsSurface;
  eyebrow?: string;
  title?: string;
}) {
  const visible = credentialsForSection(section).filter((spec) =>
    isSettable(spec, surface.byokEnabled),
  );
  if (visible.length === 0) return null;

  return (
    <CollapsibleSection eyebrow={eyebrow} title={title} defaultOpen={false}>
      <div className={styles.fields}>
        {visible.map((spec) => (
          <CredentialRow key={spec.key} spec={spec} surface={surface} />
        ))}
      </div>
      <p className={styles.note}>
        {surface.byokEnabled
          ? "Your own provider keys — encrypted on the server and never sent back to the browser. Only whether they’re set and the last four characters are shown."
          : "Keys are stored on the backend and never sent back to the browser — only whether they’re set and the last four characters are shown."}
      </p>
    </CollapsibleSection>
  );
}
