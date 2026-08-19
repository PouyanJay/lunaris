"""What the process remembers about the compiles it launched and walked away from (P2c T2)."""

import asyncio
from contextlib import suppress

import pytest
from lunaris_api.live.launched_compiles import LaunchedCompiles
from lunaris_live.graph import GraphCompilationError


async def _failing() -> None:
    raise GraphCompilationError("the model gave up")


async def _succeeding() -> str:
    return "a map"


async def _running() -> None:
    await asyncio.sleep(10)


async def test_a_failure_stays_readable_until_it_is_forgotten() -> None:
    """Non-destructive on read (found in review: a poll that read it and could not act consumed
    it), and let go on ``forget``, once the session that owns it has closed and said so."""
    launched = LaunchedCompiles()
    task = asyncio.create_task(_failing())  # type: ignore[arg-type]
    launched.remember("g1", task)  # type: ignore[arg-type]
    with suppress(GraphCompilationError):
        await task

    assert launched.failure_of("g1") == "the model gave up"
    assert launched.failure_of("g1") == "the model gave up"
    launched.forget("g1")
    assert launched.failure_of("g1") is None


async def test_a_success_leaves_nothing_behind() -> None:
    """The common case must not leak (found in review: a finished task retains the whole map)."""
    launched = LaunchedCompiles()
    task = asyncio.create_task(_succeeding())  # type: ignore[arg-type]
    launched.remember("g-ok", task)  # type: ignore[arg-type]
    await task

    assert launched.compiling("g-ok") is None
    assert launched.failure_of("g-ok") is None


async def test_a_compile_still_running_or_never_launched_here_is_not_a_failure() -> None:
    launched = LaunchedCompiles()
    task = asyncio.create_task(_running())  # type: ignore[arg-type]
    launched.remember("g-running", task)  # type: ignore[arg-type]
    try:
        assert launched.compiling("g-running") is task
        assert launched.failure_of("g-running") is None
        assert launched.failure_of("g-elsewhere") is None
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    # A cancelled compile is a failure the session can name.
    assert launched.failure_of("g-running") == "The compile was cancelled."


async def test_the_failures_kept_are_bounded() -> None:
    from lunaris_api.live import launched_compiles as module

    launched = LaunchedCompiles()
    for i in range(module._MAX_FAILURES + 5):
        task = asyncio.create_task(_failing())  # type: ignore[arg-type]
        launched.remember(f"g{i}", task)  # type: ignore[arg-type]
        with suppress(GraphCompilationError):
            await task
    assert launched.failure_of("g0") is None, "the oldest failure was evicted"
    assert launched.failure_of(f"g{module._MAX_FAILURES + 4}") is not None


@pytest.mark.parametrize("graph_id", ["g-retry"])
async def test_a_relaunch_under_the_same_id_is_the_one_remembered(graph_id: str) -> None:
    launched = LaunchedCompiles()
    first = asyncio.create_task(_running())  # type: ignore[arg-type]
    launched.remember(graph_id, first)  # type: ignore[arg-type]
    second = asyncio.create_task(_running())  # type: ignore[arg-type]
    launched.remember(graph_id, second)  # type: ignore[arg-type]
    first.cancel()
    with suppress(asyncio.CancelledError):
        await first
    try:
        # The first's ending must not evict the second's entry.
        assert launched.compiling(graph_id) is second
    finally:
        second.cancel()
        with suppress(asyncio.CancelledError):
            await second
