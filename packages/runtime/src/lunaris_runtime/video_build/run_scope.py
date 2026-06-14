"""Per-run video-build context — the seam the build harness reads to enqueue lesson videos.

The sibling of :mod:`lunaris_runtime.credentials` / :mod:`lunaris_runtime.run_config` /
:mod:`lunaris_runtime.device_bridge`: the same ``ContextVar`` mechanism, bound around the pipeline
factory + the run task so the task inherits a context copy. The agent harness reads it (the
authoring loop on a cleared module; finalize at publish); ``None`` means video generation is off for
this build — the composition root sets a coordinator only when the operator flag is on, the build is
keyed, and an owner is known, so the harness never re-derives the gate.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from .coordinator_protocol import IVideoBuildCoordinator

# The running build's video coordinator. ``None`` means "no video-build scope" → the harness
# enqueues nothing, byte-for-byte the prior (video-off) behaviour.
_run_coordinator: ContextVar[IVideoBuildCoordinator | None] = ContextVar(
    "lunaris_video_build", default=None
)


def resolve_video_coordinator() -> IVideoBuildCoordinator | None:
    """The current run's video-build coordinator, or ``None`` when video generation is off."""
    return _run_coordinator.get()


@contextmanager
def run_video_coordinator(coordinator: IVideoBuildCoordinator) -> Iterator[None]:
    """Bind ``coordinator`` as the current run's video-build coordinator for the block.

    Enter this around the pipeline factory + ``asyncio.create_task`` (alongside
    ``run_credentials``/``run_config``/``run_device_bridge``) so the run task inherits a context
    copy; the token-based reset restores the prior context on exit."""
    token = _run_coordinator.set(coordinator)
    try:
        yield
    finally:
        _run_coordinator.reset(token)
