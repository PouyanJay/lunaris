"""Playback revalidates one exact current clip using real artifacts and measured MP4 bytes."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import pytest
from lunaris_api.live.corpus.video_inventory import StudioVideoInventory
from lunaris_api.live.corpus.video_media import SignedVideoMedia
from lunaris_live.corpus.video.models.verification_request import ClipVerificationRequest
from lunaris_live.corpus.video.schemas.clip import VideoClip
from lunaris_runtime.persistence.memory_video_job_queue import InMemoryVideoJobQueue
from lunaris_runtime.schema import VideoJob
from test_corpus_video_inventory import Courses, SignedStorage, fixture, mp4


@dataclass
class Revalidation:
    adapter: StudioVideoInventory
    courses: Courses
    queue: InMemoryVideoJobQueue
    storage: SignedStorage
    clip: VideoClip
    requests: list[httpx.Request]
    bodies: list[bytes]


@pytest.fixture
async def stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Revalidation]:
    queue, storage = await fixture()
    requests: list[httpx.Request] = []
    bodies = [mp4()]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=bodies[0])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        courses = Courses()
        adapter = StudioVideoInventory(
            courses, queue, storage, SignedVideoMedia(storage, client=client)
        )
        inventory = await adapter.load("course1", owner_id="owner1", run_id="seed")
        requests.clear()
        storage.reads.clear()

        async def reject_listing(**kwargs: object) -> list[VideoJob]:
            pytest.fail("targeted clip verification must not list unrelated course slots")

        monkeypatch.setattr(queue, "list_for_course", reject_listing)
        yield Revalidation(adapter, courses, queue, storage, inventory.clips[0], requests, bodies)


async def test_verifies_only_requested_movie_with_exact_evidence(stack: Revalidation) -> None:
    assert await stack.adapter.verify(
        ClipVerificationRequest("course1", stack.clip, "owner1", "play")
    )
    assert [request.url.path for request in stack.requests] == ["/owner1/course1/job1/final.mp4"]
    assert len(stack.storage.reads) == 3


@pytest.mark.parametrize(
    "variant",
    [
        "foreign_owner",
        "foreign_course",
        "missing_job",
        "not_ready",
        "replaced",
        "changed_hash",
        "changed_mp4",
        "unpublished",
    ],
)
async def test_stale_or_foreign_clip_is_not_verified(stack: Revalidation, variant: str) -> None:
    course_id, owner = "course1", "owner1"
    if variant == "foreign_owner":
        owner = "other"
    elif variant == "foreign_course":
        course_id = "other"
    elif variant == "missing_job":
        await stack.queue.delete_for_course(course_id="course1", owner_id="owner1")
    elif variant == "not_ready":
        job = await stack.queue.get(job_id="job1", owner_id="owner1")
        await stack.queue.enqueue(job)
    elif variant == "replaced":
        job = await stack.queue.get(job_id="job1", owner_id="owner1")
        newer = job.model_copy(update={"id": "job2", "created_at": None})
        await stack.queue.enqueue(newer)
        await stack.queue.complete(job_id="job2", contract_hash=job.contract_hash)
    elif variant == "changed_hash":
        stack.courses.course.modules[0].lessons[0].segments.activate.prose = "Changed lesson"
    elif variant == "changed_mp4":
        stack.bodies[0] = mp4() + b"\x00\x00\x00\x08free"
    else:
        stack.courses.course = stack.courses.course.model_copy(update={"status": "review"})
    assert not await stack.adapter.verify(
        ClipVerificationRequest(course_id, stack.clip, owner, "play")
    )
    if variant != "changed_mp4":
        assert stack.requests == []


async def test_replacement_while_inspecting_refuses_previous_clip(
    stack: Revalidation, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = stack.queue.find_latest_ready
    calls = 0

    async def changed_latest(**kwargs: object) -> VideoJob | None:
        nonlocal calls
        calls += 1
        job = await original(**kwargs)
        if calls >= 3 and job is not None:
            return job.model_copy(update={"id": "replacement"})
        return job

    monkeypatch.setattr(stack.queue, "find_latest_ready", changed_latest)
    assert not await stack.adapter.verify(
        ClipVerificationRequest("course1", stack.clip, "owner1", "play")
    )
    assert len(stack.requests) == 1


async def test_cancel_during_inspection_does_not_continue_to_final_check(
    stack: Revalidation, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, blocked = asyncio.Event(), asyncio.Event()
    original = stack.storage.download

    async def blocked_download(*, path: str) -> bytes:
        entered.set()
        await blocked.wait()
        return await original(path=path)

    monkeypatch.setattr(stack.storage, "download", blocked_download)
    task = asyncio.create_task(
        stack.adapter.verify(ClipVerificationRequest("course1", stack.clip, "owner1", "play"))
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert stack.requests == []
