from typing import Literal

from .base import CamelModel


class KeylessReadinessView(CamelModel):
    """Whether the keyless serverless-GPU endpoint can serve right now (keyless-fallbacks T8).

    ``status`` mirrors ``ReadinessStatus``: ``ready`` (loaded, can serve), ``provisioning`` (the GPU
    is waking / the model is loading), ``unreachable`` (no endpoint wired), or ``not_applicable``
    (the caller's LLM is keyed — a hosted API, so there is no GPU). The ``Literal`` pins the wire
    contract (a typo can't ship, and OpenAPI emits the enum). The web polls this to show a
    "Provisioning GPU…" state instead of a silent wait on a keyless build's first call."""

    status: Literal["ready", "provisioning", "unreachable", "not_applicable"]
