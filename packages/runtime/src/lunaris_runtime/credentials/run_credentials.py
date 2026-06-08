"""Per-run provider-credential context — the seam for per-tenant BYOK key injection.

The live adapters (Claude/Voyage/Tavily/YouTube) historically read their key straight from
``os.environ``. In a multi-tenant deployment a build must run on the *current user's* keys, not the
process-global platform keys. This module holds the running build's keys in a ``ContextVar`` keyed
by the same environment-variable name the adapters already use, so injection is a one-line swap at
each read site (``os.environ.get(name)`` → ``resolve_secret(name)``) with no key threaded through
every call.

Two properties make it correct and safe:

- **Tenant-only.** While a run scope is active, ``resolve_secret`` returns ONLY a key the scope
  carries — it never falls back to ``os.environ``. A tenant who has not set a given provider key
  gets ``None`` (the capability degrades honestly), and the platform's own key can never leak into,
  or be billed by, a tenant build. With no scope active (admin/eval/CLI/tests) it reads
  ``os.environ`` — byte-for-byte the prior behaviour.
- **Concurrency-safe, no global mutation.** Each build runs in its own ``asyncio.Task``; contextvars
  are copied into a task at creation, so entering :func:`run_credentials` around the factory and
  ``create_task`` hands the task its own private copy of the keys. Concurrent builds for different
  users never see each other's keys, and the process environment is never written.

The value is never logged here; the structlog redaction processor covers the key names regardless.
"""

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar

# The running build's provider keys, keyed by env-var name (e.g. ``ANTHROPIC_API_KEY``). ``None``
# means "no run scope" → reads fall through to ``os.environ``.
_run_secrets: ContextVar[Mapping[str, str] | None] = ContextVar("lunaris_run_secrets", default=None)


def resolve_secret(env_var: str) -> str | None:
    """The value for ``env_var`` for the current run: the scoped key if a run scope is active, else
    the process environment. Returns ``None`` (never an empty string) when unset.

    Inside a scope this is tenant-only — it does NOT fall back to ``os.environ``, so an unset tenant
    key degrades honestly and a platform key never leaks into a tenant build."""
    scope = _run_secrets.get()
    if scope is not None:
        # ``or None`` so a present-but-blank value reads as unset (parity with the env branch); the
        # resolver never stores a blank, so this is belt-and-suspenders.
        return scope.get(env_var) or None
    return os.environ.get(env_var) or None


@contextmanager
def run_credentials(secrets: Mapping[str, str]) -> Iterator[None]:
    """Bind ``secrets`` (env-var name → key) as the current run's credentials for the block.

    Enter this around the pipeline factory + ``asyncio.create_task`` so the run task inherits a
    context copy carrying the keys; the token-based reset restores the prior context on exit (the
    parent context never keeps the keys, so they don't leak across an async generator's yields)."""
    token = _run_secrets.set(dict(secrets))
    try:
        yield
    finally:
        _run_secrets.reset(token)
