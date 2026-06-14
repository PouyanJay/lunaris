import { useEffect, useState } from "react";

import { type CredentialStatus, fetchCredentials } from "../../lib/credentials";
import { CredentialField } from "./CredentialField";
import styles from "./Settings.module.css";

interface CredentialsPanelProps {
  apiBaseUrl: string;
}

/** The per-user BYOK providers. These are the tenant's own LLM/search/video keys (the platform's
 *  Supabase/observability keys stay operator-owned), kept in lockstep with the API's BYOK_PROVIDERS. */
const PROVIDERS = [
  {
    provider: "anthropic",
    label: "Anthropic API key",
    hint: "Your Claude key — required to build courses. Validated when you save or test.",
    placeholder: "sk-ant-…",
  },
  {
    provider: "voyage",
    label: "Voyage embeddings key",
    hint: "Enables grounded claim verification against the corpus (optional).",
    placeholder: "pa-…",
  },
  {
    provider: "search",
    label: "Search API key (Tavily)",
    hint: "Enables research, auto-discovery, resources, and the seed feed (optional).",
    placeholder: "tvly-…",
  },
  {
    provider: "youtube",
    label: "YouTube API key",
    hint: "Richer video resources (duration / channel) — optional; falls back to search.",
    placeholder: "AIza…",
  },
  {
    provider: "elevenlabs",
    label: "ElevenLabs API key",
    hint: "Narrates explainer videos in one pass when voice is on — optional; without it videos render silent.",
    placeholder: "sk_…",
  },
] as const;

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; statuses: CredentialStatus[] };

/** The BYOK keys surface (Phase 2): each tenant manages their OWN provider keys via the authed
 *  per-user credentials API. Keys are write-only — only set/unset + last4 is ever shown. */
export function CredentialsPanel({ apiBaseUrl }: CredentialsPanelProps) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchCredentials(apiBaseUrl, controller.signal)
      .then((statuses) => setState({ status: "ready", statuses }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Could not load your keys.",
        });
      });
    return () => controller.abort();
  }, [apiBaseUrl]);

  function onChanged(updated: CredentialStatus) {
    setState((prev) =>
      prev.status === "ready"
        ? {
            status: "ready",
            statuses: prev.statuses.map((s) => (s.provider === updated.provider ? updated : s)),
          }
        : prev,
    );
  }

  if (state.status === "loading") {
    return <p className={styles.muted}>Loading your keys…</p>;
  }
  if (state.status === "error") {
    return (
      <p className={styles.error} role="alert">
        {state.message}
      </p>
    );
  }

  const byProvider = new Map(state.statuses.map((s) => [s.provider, s]));
  return (
    <>
      <div className={styles.fields}>
        {PROVIDERS.map((field) => (
          <CredentialField
            key={field.provider}
            apiBaseUrl={apiBaseUrl}
            provider={field.provider}
            label={field.label}
            hint={field.hint}
            placeholder={field.placeholder}
            status={byProvider.get(field.provider)}
            onChanged={onChanged}
          />
        ))}
      </div>
      <p className={styles.note}>
        These are your own provider keys, encrypted on the server and never sent back to the browser
        — only whether they&rsquo;re set and the last four characters are shown. Builds you run use
        these keys.
      </p>
    </>
  );
}
