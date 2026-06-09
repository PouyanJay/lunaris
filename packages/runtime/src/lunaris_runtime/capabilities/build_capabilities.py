"""Capture the per-course build tag from the active run credential scope (keyless-fallbacks T5)."""

from ..credentials import resolve_secret
from ..schema import CapabilityBuildTag, CapabilityMode
from .capability_spec import CAPABILITY_SPECS


def capture_build_capabilities() -> list[CapabilityBuildTag]:
    """Which provider each key-gated capability ran on for the current build.

    Reads the run's credential scope (``resolve_secret``): a capability whose key is present in
    the scope ran live; an absent key means it ran on its keyless fallback. Call this at finalize,
    inside the build's ``run_credentials`` scope, so the tag records the keys the build actually
    used (a keyless tenant tags every capability as a fallback; a partial one tags a mixed build).
    """
    tags: list[CapabilityBuildTag] = []
    for spec in CAPABILITY_SPECS:
        is_live = resolve_secret(spec.env_var) is not None
        tags.append(
            CapabilityBuildTag(
                capability=spec.capability,
                mode=CapabilityMode.LIVE if is_live else CapabilityMode.FALLBACK,
                provider=spec.live_label if is_live else spec.fallback_label,
            )
        )
    return tags
