import type { SettingsSection } from "../../lib/routes";

/** One provider/secret key, and where it belongs in the reorganized Settings. A key can appear as a
 *  per-user BYOK provider, a file-store secret, or both — the two credential UXs (see `CredentialRow`)
 *  are chosen from `byok`/`fileStore` against the deployment's mode. The list is the single source of
 *  truth for which section owns which key; it stays in lockstep with the API's BYOK_PROVIDERS
 *  (byok=true) and the file-store secret set (fileStore=true). */
export interface CredentialSpec {
  /** The BYOK provider id AND the file-store secret name (they coincide for every shared key). */
  key: string;
  label: string;
  hint: string;
  placeholder: string;
  section: SettingsSection;
  /** Offered as a per-user BYOK provider (the tenant's own key). */
  byok: boolean;
  /** Offered as a file-store secret (single-tenant / operator deployments). */
  fileStore: boolean;
}

export const CREDENTIALS: readonly CredentialSpec[] = [
  {
    key: "anthropic",
    label: "Anthropic API key",
    hint: "Your Claude key — required to build courses. Validated when you save or test.",
    placeholder: "sk-ant-…",
    section: "llm",
    byok: true,
    fileStore: true,
  },
  {
    key: "voyage",
    label: "Voyage embeddings key",
    hint: "Enables grounded claim verification against the corpus (optional).",
    placeholder: "pa-…",
    section: "llm",
    byok: true,
    fileStore: true,
  },
  {
    key: "elevenlabs",
    label: "ElevenLabs API key",
    hint: "Narrates explainer videos in one pass when voice is on — optional; without it videos render silent.",
    placeholder: "sk_…",
    section: "voice",
    byok: true,
    fileStore: true,
  },
  {
    key: "openai",
    label: "OpenAI API key",
    hint: "Generates the AI cover image for each course (GPT Image 2) — optional; without it courses show the Typographic cover.",
    placeholder: "sk-…",
    section: "tools",
    byok: true,
    fileStore: false,
  },
  {
    key: "youtube",
    label: "YouTube API key",
    hint: "Richer video resources (duration / channel) — optional; falls back to search.",
    placeholder: "AIza…",
    section: "tools",
    byok: true,
    fileStore: true,
  },
  {
    key: "search",
    label: "Search API key (Tavily)",
    hint: "Enables research, auto-discovery, resources, and the seed feed (optional).",
    placeholder: "tvly-…",
    section: "tools",
    byok: true,
    fileStore: true,
  },
  {
    key: "supabaseUrl",
    label: "Supabase URL",
    hint: "The data-layer endpoint (grounding corpus). Operator-owned.",
    placeholder: "http://127.0.0.1:54321",
    section: "system",
    byok: false,
    fileStore: true,
  },
  {
    key: "supabaseServiceRole",
    label: "Supabase service-role key",
    hint: "Service key for the data layer (grounding corpus). Operator-owned.",
    placeholder: "sb_secret_…",
    section: "system",
    byok: false,
    fileStore: true,
  },
  {
    key: "langsmith",
    label: "LangSmith API key",
    hint: "Tracing / observability (optional). Read at startup — restart to apply.",
    placeholder: "lsv2_…",
    section: "system",
    byok: false,
    fileStore: true,
  },
];

/** The keys a given section owns, in catalog order. */
export function credentialsForSection(section: SettingsSection): CredentialSpec[] {
  return CREDENTIALS.filter((spec) => spec.section === section);
}
