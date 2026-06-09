"""Shared fixtures for the API test suite."""

import asyncio
from collections.abc import Callable, Iterator

import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_runtime.schema import Course, ProgressEvent, ProgressStage


@pytest.fixture(autouse=True)
def _reset_keyless_throttle() -> Iterator[None]:
    """The keyless-build throttle (T6) is a process-wide singleton, so its per-day Draft-build
    counts persist across tests in the shared process. Clear it around each test so one test's
    keyless builds can't exhaust another's per-day cap (a flaky 429 that depends on test order)."""
    from lunaris_api import dependencies

    dependencies._get_keyless_build_throttle.cache_clear()
    yield
    dependencies._get_keyless_build_throttle.cache_clear()


class ReleasablePipeline:
    """A pipeline that emits one progress beat, parks on a release ``Event``, then builds a real
    course via the stub orchestrator. Lets a test drop the SSE consumer *before* the build finishes
    and then release it — reproducing a build that completes after the client has navigated away.
    """

    def __init__(self, store: object, release: asyncio.Event) -> None:
        self._inner = build_stub_orchestrator(store)
        self._release = release

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: object | None = None,
        agent: object | None = None,
        clarification: object | None = None,
        discovery_depth: object | None = None,
    ) -> Course:
        if progress is not None:
            await progress.emit(
                ProgressEvent(stage=ProgressStage.RUN_STARTED, label="Starting", run_id=run_id)
            )
        await self._release.wait()  # the consumer disconnects while we're parked here
        return await self._inner.run(
            topic,
            course_id=course_id,
            run_id=run_id,
            progress=progress,
            agent=agent,
            clarification=clarification,
            discovery_depth=discovery_depth,
        )


@pytest.fixture
def releasable_build() -> tuple[Callable[[object], ReleasablePipeline], asyncio.Event]:
    """A gated pipeline factory + its release event, for testing a disconnect mid-build.

    Returns ``(factory, release)``: pass ``factory`` to ``CourseService`` so the build parks until
    the test calls ``release.set()`` — deterministic, no timing/sleep needed.
    """
    release = asyncio.Event()
    return (lambda store: ReleasablePipeline(store, release)), release
