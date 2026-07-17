import { CollapsibleSection } from "../primitives/CollapsibleSection";
import { CredentialField } from "./CredentialField";
import { SecretField } from "./SecretField";
import { credentialsForSection, type CredentialSpec } from "./credentialCatalog";
import type { SettingsSurface } from "./settingsSurface";
import type { SettingsSection } from "../../lib/routes";
import styles from "./Settings.module.css";

/** One credential key, rendered with the right chrome for the deployment's mode: a per-user BYOK
 *  field (save / test / remove against the vault) when BYOK is on, or a write-only file-store secret
 *  field otherwise. Returns null when the key doesn't exist in the active mode — an operator-owned
 *  key (Supabase / LangSmith) has no BYOK field, and some keys (OpenAI) have no file-store field —
 *  so a section only shows the keys a user can actually set here. */
function CredentialRow({ spec, surface }: { spec: CredentialSpec; surface: SettingsSurface }) {
  if (surface.byokEnabled) {
    if (!spec.byok) return null;
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
  if (!spec.fileStore) return null;
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
  const specs = credentialsForSection(section);
  const visible = specs.filter((spec) => (surface.byokEnabled ? spec.byok : spec.fileStore));
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
