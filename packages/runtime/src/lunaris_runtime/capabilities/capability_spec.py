"""The single source of truth mapping each key-gated capability to its providers.

Both indicators the keyless-fallbacks journey adds read from this one table, so they never drift:

- the **live settings badge** (``apps/api``) — derived from whether the secret is *stored* (the
  operator file store or the tenant's vault), flipping the instant a key is saved; and
- the **per-course build tag** (:func:`capture_build_capabilities`) — derived from whether the key
  is present in the *run's credential scope* at finalize, recording which provider built a course.

The two read different presence signals (stored vs. in-scope) but share the capability set, the
secret/env identifiers, and the human provider labels — which all live here, named once.
"""

from dataclasses import dataclass

from ..schema.enums import CapabilityName


@dataclass(frozen=True)
class CapabilitySpec:
    """One capability's keyed provider and its keyless fallback, with the ids that detect presence.

    ``secret_id`` is the web/API contract id the secret store and BYOK vault report (drives the live
    badge); ``env_var`` is the environment-variable name the runtime adapters read, resolved through
    the run credential scope (drives the per-course build tag). ``live_label`` / ``fallback_label``
    are the human provider names shown for each mode.
    """

    capability: CapabilityName
    secret_id: str
    env_var: str
    live_label: str
    fallback_label: str
    # Whether the keyless fallback runs on the local model-inference server (the GPU/CPU-bound one),
    # vs. a keyless web service (e.g. DuckDuckGo). Only inference-backed fallbacks carry a compute
    # (GPU/CPU) badge in the Draft UI. The LLM is GPU-acceleratable today; embeddings stay CPU.
    runs_on_local_inference: bool = False


# Order is the stable UI order for both indicators. ``secret_id`` matches the API's KNOWN_SECRETS,
# and ``env_var`` is the variable that same secret populates, so a stored key and an in-scope key
# resolve to the same provider label.
CAPABILITY_SPECS: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        capability=CapabilityName.LLM,
        secret_id="anthropic",
        env_var="ANTHROPIC_API_KEY",
        live_label="Anthropic Claude",
        fallback_label="Qwen2.5-3B (local)",
        runs_on_local_inference=True,
    ),
    CapabilitySpec(
        capability=CapabilityName.EMBEDDINGS,
        secret_id="voyage",
        env_var="EMBEDDINGS_API_KEY",
        live_label="Voyage",
        fallback_label="BGE-large (local)",
    ),
    CapabilitySpec(
        capability=CapabilityName.SEARCH,
        secret_id="search",
        env_var="SEARCH_API_KEY",
        live_label="Tavily",
        fallback_label="DuckDuckGo",
    ),
    CapabilitySpec(
        capability=CapabilityName.VIDEO,
        secret_id="youtube",
        env_var="YOUTUBE_API_KEY",
        live_label="YouTube",
        fallback_label="Web search",
    ),
)
