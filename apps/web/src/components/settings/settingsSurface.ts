import type { CapabilityStatus } from "../../lib/capabilities";
import type { CredentialStatus } from "../../lib/credentials";
import type { SecretStatus } from "../../lib/settings";

/** The shared settings state the sub-nav sections read from — loaded once by `SettingsLayout` and
 *  passed down, so every section sees one consistent view (pipeline, capabilities, both credential
 *  stores, and the key-freshness signal). Sections that own credentials render them via
 *  `CredentialRow`; the rest read what they need and ignore the rest. */
export interface SettingsSurface {
  apiBaseUrl: string;
  /** The active pipeline mode (stub / live / agent), shown in the System section. */
  pipeline: string;
  /** Per-user BYOK on → credentials are the tenant's own vault; off → the file-store secret set. */
  byokEnabled: boolean;
  /** ConfigPanel copy: per-user vs process-wide operator config. */
  perUserConfigEnabled: boolean;
  /** The LLM runs on its keyless local fallback — video is deactivated, System shows the compute
   *  source picker. */
  keyless: boolean;
  capabilities: CapabilityStatus[];
  /** File-store secret statuses (the non-BYOK credential source). */
  secrets: SecretStatus[];
  /** BYOK vault statuses (the per-user credential source). */
  credentialStatuses: CredentialStatus[];
  /** Bumped on every key save/remove so key-gated sections (covers, narration) re-read the vault
   *  immediately instead of only after a full reload. */
  keysVersion: number;
  onSecretSaved: (status: SecretStatus) => void;
  onCredentialChanged: (status: CredentialStatus) => void;
}
