"""Video V4-T0: the build's video-enqueue gate lives entirely in ``CourseService`` (plan §V4-T0).

A build's video coordinator is scoped into the run task ONLY when video generation is on for that
build: the operator flag (the coordinator factory is wired), AND the build is keyed (not a keyless
Draft build), AND an owner is known. The harness reads the coordinator off the run-scope contextvar;
a capturing pipeline records what the run task saw, so each gate condition is asserted directly.
"""

from collections.abc import Mapping

import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.service import CourseService
from lunaris_runtime.persistence import InMemoryVideoJobQueue, InMemoryVideoStorage
from lunaris_runtime.schema import Course
from lunaris_runtime.video_build import (
    VIDEO_ENABLED_ENV,
    IVideoBuildCoordinator,
    QueueVideoBuildCoordinator,
    resolve_video_coordinator,
)

_LLM_KEY = "ANTHROPIC_API_KEY"
_OWNER = "user-a"


class _MemCourseStore:
    """A throwaway course store — the stub orchestrator only needs ``save`` to finalize a course."""

    def save(self, course: Course, *, owner_id: str | None = None) -> None: ...

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        raise FileNotFoundError(course_id)

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return False


class _CapturingPipeline:
    """A pipeline that records the video coordinator visible in run scope, then builds a real (stub)
    course so ``CourseService.create`` completes normally."""

    def __init__(self, store: object, seen: list[IVideoBuildCoordinator | None]) -> None:
        self._inner = build_stub_orchestrator(store)
        self._seen = seen

    async def run(self, topic: str, *, course_id: str, run_id: str, **kwargs: object) -> Course:
        self._seen.append(resolve_video_coordinator())
        return await self._inner.run(topic, course_id=course_id, run_id=run_id)


def _service_and_queue(
    seen: list[IVideoBuildCoordinator | None],
    *,
    video_on: bool,
    credential_resolver: object | None = None,
    config_resolver: object | None = None,
) -> tuple[CourseService, InMemoryVideoJobQueue]:
    """The service plus the queue its coordinator enqueues onto, so a gate test can prove not just
    that no coordinator was scoped but that ZERO rows actually landed on the queue."""
    queue = InMemoryVideoJobQueue()
    storage = InMemoryVideoStorage()
    factory = (
        (
            lambda owner_id, video_config: QueueVideoBuildCoordinator(
                queue=queue, storage=storage, owner_id=owner_id, video_config=video_config
            )
        )
        if video_on
        else None
    )
    service = CourseService(
        store=_MemCourseStore(),
        pipeline_factory=lambda store: _CapturingPipeline(store, seen),
        video_coordinator_factory=factory,
        credential_resolver=credential_resolver,  # type: ignore[arg-type]
        config_resolver=config_resolver,  # type: ignore[arg-type]
    )
    return service, queue


def _service(
    seen: list[IVideoBuildCoordinator | None],
    *,
    video_on: bool,
    credential_resolver: object | None = None,
    config_resolver: object | None = None,
) -> CourseService:
    service, _ = _service_and_queue(
        seen,
        video_on=video_on,
        credential_resolver=credential_resolver,
        config_resolver=config_resolver,
    )
    return service


async def _run_build(service: CourseService, *, owner_id: str | None) -> None:
    await service.create("Topic", course_id="c1", run_id="r1", owner_id=owner_id)


async def test_keyed_owned_build_with_video_on_scopes_a_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — video on (factory wired), keyed (env key), owned.
    monkeypatch.setenv(_LLM_KEY, "test-key")
    seen: list[IVideoBuildCoordinator | None] = []

    # Act
    await _run_build(_service(seen, video_on=True), owner_id=_OWNER)

    # Assert — the run task saw a coordinator: this build enqueues videos.
    assert len(seen) == 1
    assert seen[0] is not None


async def test_keyless_build_scopes_no_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — video on + owned, but NO key (a Draft build); video is keyed-only.
    monkeypatch.delenv(_LLM_KEY, raising=False)
    seen: list[IVideoBuildCoordinator | None] = []

    # Act
    await _run_build(_service(seen, video_on=True), owner_id=_OWNER)

    # Assert — no coordinator → zero jobs (the keyless variant).
    assert seen == [None]


async def test_unowned_build_scopes_no_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — video on + keyed, but no owner (auth off): a job row needs a user_id.
    monkeypatch.setenv(_LLM_KEY, "test-key")
    seen: list[IVideoBuildCoordinator | None] = []

    # Act
    await _run_build(_service(seen, video_on=True), owner_id=None)

    # Assert — no owner → no coordinator.
    assert seen == [None]


async def test_flag_off_scopes_no_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — keyed + owned, but the operator flag is OFF (no factory wired).
    monkeypatch.setenv(_LLM_KEY, "test-key")
    seen: list[IVideoBuildCoordinator | None] = []

    # Act
    await _run_build(_service(seen, video_on=False), owner_id=_OWNER)

    # Assert — the operator kill-switch means zero jobs regardless of key/owner.
    assert seen == [None]


async def test_keyed_build_via_credential_resolver_scopes_a_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — env unset, but the owner's vault carries an Anthropic key (BYOK keyed).
    monkeypatch.delenv(_LLM_KEY, raising=False)
    seen: list[IVideoBuildCoordinator | None] = []

    async def resolver(user_id: str) -> Mapping[str, str]:
        return {_LLM_KEY: "tenant-key"}

    # Act
    await _run_build(_service(seen, video_on=True, credential_resolver=resolver), owner_id=_OWNER)

    # Assert — a BYOK-keyed build enqueues videos just like an env-keyed one.
    assert seen[0] is not None


async def test_master_toggle_off_scopes_no_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — flag on + keyed + owned, but the owner turned the V6 master toggle OFF in Settings.
    monkeypatch.setenv(_LLM_KEY, "test-key")
    seen: list[IVideoBuildCoordinator | None] = []

    async def config_resolver(user_id: str) -> Mapping[str, str]:
        return {VIDEO_ENABLED_ENV: "false"}

    service, queue = _service_and_queue(seen, video_on=True, config_resolver=config_resolver)

    # Act
    await _run_build(service, owner_id=_OWNER)

    # Assert — the per-user opt-out gates enqueue just like the operator flag: no coordinator in
    # scope AND not one row landed on the queue.
    assert seen == [None]
    assert await queue.claim(worker_id="probe") is None


async def test_master_toggle_default_on_scopes_a_coordinator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — keyed + owned, the owner never touched video settings (resolver returns nothing).
    monkeypatch.setenv(_LLM_KEY, "test-key")
    seen: list[IVideoBuildCoordinator | None] = []

    async def config_resolver(user_id: str) -> Mapping[str, str]:
        return {}  # unset → master toggle defaults ON

    # Act
    await _run_build(
        _service(seen, video_on=True, config_resolver=config_resolver), owner_id=_OWNER
    )

    # Assert — the default-ON master toggle leaves video on.
    assert seen[0] is not None
