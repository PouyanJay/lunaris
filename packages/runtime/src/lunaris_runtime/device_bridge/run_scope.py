"""Per-run device-bridge context — the seam that routes a build's LLM calls to the browser.

The sibling of :mod:`lunaris_runtime.credentials` / :mod:`lunaris_runtime.run_config`: the same
``ContextVar`` mechanism, bound around the pipeline factory + the run task so the task inherits a
context copy. ``build_chat_model`` checks it on the keyless path: a bridge in scope means this
Draft build's completions are served by the learner's device, not the keyless server endpoint.
Concurrent builds each see only their own bridge; no global state is mutated.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .bridge import DeviceBridge

# The running build's device bridge. ``None`` means "no device-compute scope" → the keyless path
# uses the server fallback model, byte-for-byte the prior behaviour.
_run_bridge: ContextVar[DeviceBridge | None] = ContextVar("lunaris_device_bridge", default=None)


def resolve_device_bridge() -> DeviceBridge | None:
    """The current run's device bridge, or ``None`` when this build's compute is not the device."""
    return _run_bridge.get()


@contextmanager
def run_device_bridge(bridge: DeviceBridge) -> Iterator[None]:
    """Bind ``bridge`` as the current run's device bridge for the block.

    Enter this around the pipeline factory + ``asyncio.create_task`` (alongside
    ``run_credentials``/``run_config``) so the run task inherits a context copy; the token-based
    reset restores the prior context on exit."""
    token = _run_bridge.set(bridge)
    try:
        yield
    finally:
        _run_bridge.reset(token)
