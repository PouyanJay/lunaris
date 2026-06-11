"""The device bridge's time bounds — how long a build will wait on the learner's tab."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeLimits:
    """Time bounds for one run's bridge, injected from the operator's config.

    ``liveness_s`` bounds tab SILENCE: the long-poll itself holds ~25s, so the bound must sit
    well above one poll window — 75s means roughly three missed polls before the build is failed
    as disconnected (tab closed / laptop asleep). ``completion_timeout_s`` bounds one ANSWER:
    on-device generation legitimately runs minutes (it mirrors the keyless server tier's 900s),
    so it only catches a wedged engine whose tab is still dutifully polling.
    """

    liveness_s: float = 75.0
    completion_timeout_s: float = 900.0
