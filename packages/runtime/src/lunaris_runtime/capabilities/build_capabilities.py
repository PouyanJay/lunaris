"""Capture the per-course build tag from the active run credential scope (keyless-fallbacks T5)."""

from ..credentials import resolve_secret
from ..device_bridge import resolve_device_bridge
from ..schema import CapabilityBuildTag, CapabilityMode, CapabilityName
from .capability_spec import CAPABILITY_SPECS

# A device-compute Draft build ran the same model family as the server tier — only the compute
# location differs, so the device label is DERIVED from the spec's fallback label (swap the
# location suffix) and can never drift from it when the served model changes.
_SERVER_LOCATION_SUFFIX = "(local)"
_DEVICE_LOCATION_SUFFIX = "(your device)"


def capture_build_capabilities() -> list[CapabilityBuildTag]:
    """Which provider each key-gated capability ran on for the current build.

    Reads the run's credential scope (``resolve_secret``): a capability whose key is present in
    the scope ran live; an absent key means it ran on its keyless fallback. A keyless LLM with the
    run's device bridge in scope ran on the learner's device — only the LLM leg moves there, so
    the other capabilities keep their server fallback labels. Call this at finalize, inside the
    build's run scopes, so the tag records what the build actually used (a keyless tenant tags
    every capability as a fallback; a partial one tags a mixed build).
    """
    tags: list[CapabilityBuildTag] = []
    for spec in CAPABILITY_SPECS:
        is_live = resolve_secret(spec.env_var) is not None
        provider = spec.live_label if is_live else spec.fallback_label
        if (
            spec.capability is CapabilityName.LLM
            and not is_live
            and resolve_device_bridge() is not None
        ):
            provider = spec.fallback_label.replace(_SERVER_LOCATION_SUFFIX, _DEVICE_LOCATION_SUFFIX)
        tags.append(
            CapabilityBuildTag(
                capability=spec.capability,
                mode=CapabilityMode.LIVE if is_live else CapabilityMode.FALLBACK,
                provider=provider,
            )
        )
    return tags
