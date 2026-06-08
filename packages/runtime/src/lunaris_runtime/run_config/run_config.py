"""Per-run non-secret runtime config — the seam for per-tenant model selection.

The sibling of :mod:`lunaris_runtime.credentials`: same ``ContextVar`` mechanism (keyed by the
environment-variable name the runtime already reads, bound around the pipeline factory + the run
task so the task inherits a context copy), but for NON-secret config — today the model ids
(``LUNARIS_MODEL_STRONG`` / ``LUNARIS_MODEL_WORKER``) a tenant chooses for their builds.

The one behavioural difference from ``resolve_secret``: config FALLS BACK to ``os.environ`` even
inside a run scope. A model id is not a secret and carries no per-tenant billing/leak concern, so a
tenant who hasn't chosen a model uses the operator's env default (and then the code's built-in
default, applied by the caller). A secret, by contrast, is tenant-only with no env fallback in a
scope.
"""

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

# The running build's per-user config, keyed by env-var name. ``None`` means "no run scope".
_run_config: ContextVar[Mapping[str, str] | None] = ContextVar("lunaris_run_config", default=None)


def resolve_config(env_var: str) -> str | None:
    """The value for ``env_var`` for the current run: the tenant's choice if a run scope carries it,
    else the process environment. ``None`` (never an empty string) when unset everywhere.

    Falls back to ``os.environ`` even inside a scope (non-secret config → the operator's env default
    is an acceptable fallback); the caller applies the code default when this returns ``None``."""
    scope = _run_config.get()
    if scope is not None:
        return scope.get(env_var) or os.environ.get(env_var) or None
    return os.environ.get(env_var) or None


@contextmanager
def run_config(values: Mapping[str, str]) -> Iterator[None]:
    """Bind ``values`` (env-var name → value) as the current run's config for the block.

    Enter this around the pipeline factory + ``asyncio.create_task`` (alongside ``run_credentials``)
    so the run task inherits a context copy; the token-based reset restores the prior context."""
    token = _run_config.set(dict(values))
    try:
        yield
    finally:
        _run_config.reset(token)
