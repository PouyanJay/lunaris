from typing import Literal

from .base import CamelModel


class KeylessReadinessView(CamelModel):
    """Whether the keyless model endpoint can serve right now (keyless-fallbacks T8).

    ``status`` mirrors ``ReadinessStatus``: ``ready`` (loaded, can serve), ``provisioning`` (the
    server is waking / the model is loading), ``unreachable`` (no endpoint wired), or
    ``not_applicable`` (the caller's LLM is keyed — a hosted API, so there is no local server). The
    ``Literal`` pins the wire contract (a typo can't ship; OpenAPI emits the enum). The web polls it
    to show a "Provisioning…" state instead of a silent wait on a keyless build."""

    status: Literal["ready", "provisioning", "unreachable", "not_applicable"]
