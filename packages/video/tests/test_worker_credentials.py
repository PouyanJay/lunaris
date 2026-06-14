"""Video V7-T1: per-job vault credentials at claim time.

The cloud worker carries NO provider keys in its env (tenant-only BYOK). For each claimed job it
resolves the owner's keys from the vault and binds them as the run scope around the render, so the
pipeline's Claude / ElevenLabs calls authenticate as the tenant — exactly as a build does. The scope
is tenant-only (it never leaks a platform env key into a tenant render); with no resolver wired
(local dev, no vault) the render falls back to the process env, unchanged.
"""

import asyncio
from collections.abc import Mapping

import pytest
from lunaris_runtime.credentials import CredentialResolver, resolve_secret
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_runtime.schema import VideoJob, VideoJobStatus, VideoKind
from lunaris_video import RenderedVideo, StubVideoPipeline, VideoWorker

_OWNER = "00000000-0000-0000-0000-000000000007"
_LLM_KEY = "ANTHROPIC_API_KEY"


class _SecretSpyPipeline:
    """Records what ``resolve_secret(ANTHROPIC_API_KEY)`` returns DURING produce — i.e. what the
    render would authenticate with — then returns a real stub artifact set so the job settles."""

    def __init__(self) -> None:
        self._inner = StubVideoPipeline()
        self.seen_key: str | None = "<<unset>>"

    async def produce(self, job: VideoJob) -> RenderedVideo:
        self.seen_key = resolve_secret(_LLM_KEY)
        return await self._inner.produce(job)


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id=_OWNER,
        course_id="c1",
        lesson_id="l1",
        kind=VideoKind.LESSON,
        input_hash="h",
    )


async def _run_one(pipeline: _SecretSpyPipeline, resolver: CredentialResolver | None) -> VideoJob:
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = VideoWorker(
        queue=queue,
        pipeline=pipeline,
        storage=storage,
        events=events,
        worker_id="w",
        credential_resolver=resolver,
    )
    assert await worker.run_once() is True
    job = await queue.get(job_id="job-1")
    assert job is not None
    return job


async def test_worker_binds_the_owners_vault_keys_for_the_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the cloud posture: no provider key in env; the vault resolver supplies the owner's.
    monkeypatch.delenv(_LLM_KEY, raising=False)
    spy = _SecretSpyPipeline()

    async def resolver(owner_id: str) -> Mapping[str, str]:
        assert owner_id == _OWNER  # resolved by the JOB's owner, not a process-global key
        return {_LLM_KEY: "sk-tenant"}

    # Act
    job = await _run_one(spy, resolver)

    # Assert — the render authenticated as the tenant; the job settled READY.
    assert spy.seen_key == "sk-tenant"
    assert job.status == VideoJobStatus.READY


async def test_worker_without_a_resolver_reads_the_process_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Local dev / no vault: no resolver → no scope → resolve_secret falls back to os.environ.
    monkeypatch.setenv(_LLM_KEY, "sk-env")
    spy = _SecretSpyPipeline()

    job = await _run_one(spy, None)

    assert spy.seen_key == "sk-env"
    assert job.status == VideoJobStatus.READY


async def test_worker_scope_is_tenant_only_and_never_leaks_the_platform_env_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A platform key in env must NOT leak into a tenant render whose vault carries no such key:
    # an empty resolver result still enters the tenant-only scope, so resolve_secret returns None.
    monkeypatch.setenv(_LLM_KEY, "sk-platform")
    spy = _SecretSpyPipeline()

    async def resolver(owner_id: str) -> Mapping[str, str]:
        return {}  # the tenant set no provider keys

    job = await _run_one(spy, resolver)

    assert spy.seen_key is None  # tenant-only: the platform env key never leaks into the render
    assert job.status == VideoJobStatus.READY


async def test_concurrent_renders_never_see_each_others_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The core isolation guarantee: two owners' jobs drained by two workers AT ONCE. A barrier holds
    # both renders until both credential scopes are live, so they genuinely overlap in time — then
    # each reads its key. Contextvars are per-task, so one tenant's keys can't bleed into the other.
    monkeypatch.delenv(_LLM_KEY, raising=False)
    owner_a = "00000000-0000-0000-0000-00000000000a"
    owner_b = "00000000-0000-0000-0000-00000000000b"
    both_in_flight = asyncio.Barrier(2)

    class _OverlappingSpyPipeline:
        def __init__(self) -> None:
            self._inner = StubVideoPipeline()
            self.seen: dict[str, str | None] = {}

        async def produce(self, job: VideoJob) -> RenderedVideo:
            await both_in_flight.wait()  # both scopes are now active at the same time
            self.seen[job.user_id] = resolve_secret(_LLM_KEY)
            return await self._inner.produce(job)

    pipeline = _OverlappingSpyPipeline()

    async def resolver(owner_id: str) -> Mapping[str, str]:
        return {_LLM_KEY: f"sk-{owner_id}"}

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    for job_id, owner in (("job-a", owner_a), ("job-b", owner_b)):
        await queue.enqueue(
            VideoJob(
                id=job_id,
                user_id=owner,
                course_id="c1",
                lesson_id=job_id,
                kind=VideoKind.LESSON,
                input_hash="h",
            )
        )
    workers = [
        VideoWorker(
            queue=queue,
            pipeline=pipeline,
            storage=storage,
            events=events,
            worker_id=f"w{n}",
            credential_resolver=resolver,
        )
        for n in range(2)
    ]

    # Act — both workers claim + render concurrently.
    async with asyncio.timeout(5):
        assert await asyncio.gather(*(w.run_once() for w in workers)) == [True, True]

    # Assert — each overlapping render saw ONLY its own owner's key, never the other's.
    assert pipeline.seen == {owner_a: f"sk-{owner_a}", owner_b: f"sk-{owner_b}"}
