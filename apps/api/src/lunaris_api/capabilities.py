"""Which provider each key-gated capability is using right now: the live provider when its key is
set, else the keyless local fallback.

This mapping is the single source of truth for both the live settings badge (which flips to live the
moment a key is stored) and — later — the per-course build tag (which records the fallback that
produced a course). Computing both from one place keeps the two indicators consistent.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class CapabilityName(StrEnum):
    """A key-gated capability that has a keyless fallback."""

    LLM = "llm"
    EMBEDDINGS = "embeddings"
    SEARCH = "search"
    VIDEO = "video"


class CapabilityMode(StrEnum):
    """Whether a capability runs on its keyed provider or its keyless fallback."""

    LIVE = "live"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class CapabilityStatus:
    """A capability's active provider: its mode and the human label of the provider in effect."""

    capability: CapabilityName
    mode: CapabilityMode
    provider: str


# capability → (secret id that enables the live provider, live label, keyless-fallback label).
# The secret ids match KNOWN_SECRETS so presence drives the mode.
_PROVIDERS: dict[CapabilityName, tuple[str, str, str]] = {
    CapabilityName.LLM: ("anthropic", "Anthropic Claude", "Qwen3-4B (local)"),
    CapabilityName.EMBEDDINGS: ("voyage", "Voyage", "voyage-4-nano (local)"),
    CapabilityName.SEARCH: ("search", "Tavily", "DuckDuckGo"),
    CapabilityName.VIDEO: ("youtube", "YouTube", "Web search"),
}


def resolve_capabilities(is_set: Callable[[str], bool]) -> list[CapabilityStatus]:
    """Per-capability active provider, derived from which secrets are present.

    ``is_set(secret_id)`` reports whether the live provider's key is configured; when it isn't, the
    capability runs on its keyless fallback. Order follows ``_PROVIDERS`` so the UI is stable.
    """
    return [
        CapabilityStatus(
            capability=capability,
            mode=CapabilityMode.LIVE if is_set(secret_id) else CapabilityMode.FALLBACK,
            provider=live_label if is_set(secret_id) else fallback_label,
        )
        for capability, (secret_id, live_label, fallback_label) in _PROVIDERS.items()
    ]
