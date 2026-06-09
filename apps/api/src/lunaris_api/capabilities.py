"""Which provider each key-gated capability is using right now: the live provider when its key is
set, else the keyless local fallback.

This is the live settings badge's view (it flips to live the moment a key is stored). It and the
per-course build tag (``lunaris_runtime.capabilities.capture_build_capabilities``) both read the one
shared capability table (``CAPABILITY_SPECS``) so the two indicators can never drift — they differ
only in the presence signal: this reads whether a secret is *stored*, the tag reads whether a key is
present in the build's *run credential scope*.
"""

from collections.abc import Callable
from dataclasses import dataclass

from lunaris_runtime.capabilities import CAPABILITY_SPECS
from lunaris_runtime.schema import CapabilityMode, CapabilityName


@dataclass(frozen=True)
class CapabilityStatus:
    """A capability's active provider: its mode and the human label of the provider in effect."""

    capability: CapabilityName
    mode: CapabilityMode
    provider: str


def resolve_capabilities(is_set: Callable[[str], bool]) -> list[CapabilityStatus]:
    """Per-capability active provider, derived from which secrets are present.

    ``is_set(secret_id)`` reports whether the live provider's key is configured; when it isn't, the
    capability runs on its keyless fallback. Order follows ``CAPABILITY_SPECS`` so the UI is stable.
    """
    statuses: list[CapabilityStatus] = []
    for spec in CAPABILITY_SPECS:
        # Resolve presence once — ``is_set`` may hit the vault, so avoid calling it twice per row.
        live = is_set(spec.secret_id)
        statuses.append(
            CapabilityStatus(
                capability=spec.capability,
                mode=CapabilityMode.LIVE if live else CapabilityMode.FALLBACK,
                provider=spec.live_label if live else spec.fallback_label,
            )
        )
    return statuses
