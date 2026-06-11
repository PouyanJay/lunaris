from lunaris_runtime.run_config import resolve_config

_DEFAULT_WORKER = "claude-haiku-4-5-20251001"
_DEFAULT_STRONG = "claude-opus-4-8"


def _worker_model(override: str | None = None) -> str:
    """The bulk extraction/judging/authoring tier: explicit override → run config → default."""
    return override or resolve_config("LUNARIS_MODEL_WORKER") or _DEFAULT_WORKER


def _strong_model(override: str | None = None) -> str:
    """The planner/architect/assessor tier: explicit override → run config → default."""
    return override or resolve_config("LUNARIS_MODEL_STRONG") or _DEFAULT_STRONG
