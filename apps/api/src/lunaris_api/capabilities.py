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
from lunaris_runtime.schema import CapabilityMode, CapabilityName, ComputeKind


@dataclass(frozen=True)
class CapabilityStatus:
    """A capability's active provider: its mode, the human label of the provider in effect, and —
    for a keyless fallback that runs on the local model server — whether it's on GPU or CPU."""

    capability: CapabilityName
    mode: CapabilityMode
    provider: str
    compute: ComputeKind | None = None


def resolve_capabilities(
    is_set: Callable[[str], bool], *, compute: ComputeKind
) -> list[CapabilityStatus]:
    """Per-capability active provider, derived from which secrets are present.

    ``is_set(secret_id)`` reports whether the live provider's key is configured; when it isn't, the
    capability runs on its keyless fallback. ``compute`` is where the local inference runs
    (GPU/CPU), attached only to a fallback that actually runs on that inference server (the LLM) — a
    live capability or a keyless web service (search/video) carries no compute. Order follows
    ``CAPABILITY_SPECS`` so the UI is stable.
    """
    statuses: list[CapabilityStatus] = []
    for spec in CAPABILITY_SPECS:
        # Resolve presence once — ``is_set`` may hit the vault, so avoid calling it twice per row.
        live = is_set(spec.secret_id)
        on_inference = not live and spec.runs_on_local_inference
        statuses.append(
            CapabilityStatus(
                capability=spec.capability,
                mode=CapabilityMode.LIVE if live else CapabilityMode.FALLBACK,
                provider=spec.live_label if live else spec.fallback_label,
                compute=compute if on_inference else None,
            )
        )
    return statuses
