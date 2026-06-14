"""Worker-loop tests: claim → produce → upload → settle, against the in-memory queue/storage
doubles and a real stub pipeline. The loop's contract: it never raises (job-level errors settle
the job; infrastructure errors are logged and retried next poll), every artifact lands under the
{user_id}/{course_id}/{job_id}/ path convention, the job's lifecycle is appended to run_events
under run_id = job_id, and the job_id is bound into structlog contextvars while the job runs."""

import asyncio

import pytest
import structlog
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    PersistenceError,
)
from lunaris_runtime.schema import (
    RunEventKind,
    VideoJob,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)
from lunaris_video import RenderedVideo, StubVideoPipeline, VideoWorker

_OWNER = "00000000-0000-0000-0000-000000000001"


def _job(job_id: str = "job-1") -> VideoJob:
    return VideoJob(
        id=job_id,
        user_id=_OWNER,
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


def _worker(
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    pipeline: object | None = None,
) -> VideoWorker:
    return VideoWorker(
        queue=queue,
        pipeline=pipeline or StubVideoPipeline(),
        storage=storage,
        events=events,
        worker_id="worker-test",
    )


async def test_run_once_on_an_empty_queue_does_nothing() -> None:
    # Arrange
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    worker = _worker(queue, storage, events)

    # Act / Assert — nothing claimed, nothing uploaded, nothing logged to any run.
    assert await worker.run_once() is False
    assert storage.paths() == []
    assert await events.list_for_run(run_id="job-1") == []


async def test_run_once_processes_a_job_end_to_end() -> None:
    # Arrange
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events)

    # Act
    processed = await worker.run_once()

    # Assert — the walking skeleton's spine: claim → produce → upload → ready.
    assert processed is True
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY
    prefix = f"{_OWNER}/course-1/job-1"
    mp4_path, poster_path = f"{prefix}/final.mp4", f"{prefix}/poster.jpg"
    contracts_path, timing_path = f"{prefix}/scene_contracts.json", f"{prefix}/timing.json"
    provenance_path = f"{prefix}/provenance.json"
    assert sorted(storage.paths()) == sorted(
        [mp4_path, poster_path, contracts_path, timing_path, provenance_path]
    )
    assert storage.content_type(mp4_path) == "video/mp4"
    assert storage.content_type(poster_path) == "image/jpeg"
    assert storage.content_type(contracts_path) == "application/json"
    assert storage.content_type(provenance_path) == "application/json"
    assert storage.read(mp4_path)[4:8] == b"ftyp"
    assert storage.read(poster_path)[:3] == b"\xff\xd8\xff"
    # The stub still carries real provenance under the job's run_id (the spine traces everything).
    provenance = VideoProvenance.model_validate_json(storage.read(provenance_path))
    assert provenance.job_id == "job-1"
    assert provenance.input_hash == _job().input_hash


async def test_a_narrated_video_uploads_a_captions_track() -> None:
    # Arrange — a narrated render carries WebVTT captions; a silent one (the stub) carries none (the
    # exact-path-set assertion in test_run_once_processes_a_job_end_to_end proves silent uploads 0).
    class _NarratedPipeline:
        async def produce(self, job: VideoJob) -> RenderedVideo:
            return RenderedVideo(
                mp4=b"\x00\x00\x00\x18ftyp" + b"x" * 2000,
                poster=b"\xff\xd8\xff" + b"x" * 600,
                contracts_json=b"{}",
                timing_json=b"{}",
                captions=b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello.\n",
            )

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events, pipeline=_NarratedPipeline())

    # Act
    assert await worker.run_once() is True

    # Assert — the captions ride under the job prefix with the WebVTT content type.
    captions_path = f"{_OWNER}/course-1/job-1/captions.vtt"
    assert captions_path in storage.paths()
    assert storage.content_type(captions_path) == "text/vtt"
    assert storage.read(captions_path).startswith(b"WEBVTT")


async def test_run_once_appends_the_job_lifecycle_to_run_events() -> None:
    # Arrange
    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events)

    # Act
    await worker.run_once()

    # Assert — the job's transcript lives under run_id = job_id, gap-free from 0, owner-stamped.
    recorded = await events.list_for_run(run_id="job-1", owner_id=_OWNER)
    assert [event.seq for event in recorded] == list(range(len(recorded)))
    assert all(event.kind == RunEventKind.PROGRESS for event in recorded)
    assert all(event.course_id == "course-1" for event in recorded)
    statuses = [event.payload.get("status") for event in recorded]
    assert statuses[0] == "planning"  # claimed
    assert statuses[-1] == "ready"  # settled


async def test_run_once_binds_the_job_id_into_log_context_while_working() -> None:
    # Arrange — a pipeline double that captures the structlog contextvars active DURING the job.
    captured: dict[str, object] = {}

    class _CapturingPipeline:
        async def produce(self, job: VideoJob) -> RenderedVideo:
            captured.update(structlog.contextvars.get_contextvars())
            return RenderedVideo(
                mp4=b"\x00\x00\x00\x18ftyp" + b"x" * 2000,
                poster=b"\xff\xd8\xff" + b"x" * 600,
                contracts_json=b"{}",
                timing_json=b"{}",
            )

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events, pipeline=_CapturingPipeline())

    # Act
    await worker.run_once()

    # Assert — every log line inside the job carries the correlation id; cleared afterwards.
    assert captured.get("run_id") == "job-1"
    assert captured.get("worker_id") == "worker-test"
    leftover = structlog.contextvars.get_contextvars()
    assert "run_id" not in leftover
    assert "worker_id" not in leftover
    assert "course_id" not in leftover


async def test_a_pipeline_failure_settles_the_job_failed_without_raising() -> None:
    # Arrange
    class _ExplodingPipeline:
        async def produce(self, job: VideoJob) -> RenderedVideo:
            raise RuntimeError("manim exploded: /tmp/secret/path leaked")

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events, pipeline=_ExplodingPipeline())

    # Act — the worker absorbs the failure; the loop must survive.
    processed = await worker.run_once()

    # Assert — settled FAILED with a user-safe error (no internals leaked), failure event logged.
    assert processed is True
    job = await queue.get(job_id="job-1")
    assert job is not None
    assert job.status == VideoJobStatus.FAILED
    assert job.error is not None
    assert "secret" not in job.error and "/tmp" not in job.error
    recorded = await events.list_for_run(run_id="job-1", owner_id=_OWNER)
    assert recorded[0].payload.get("status") == "planning"
    assert recorded[-1].payload.get("status") == "failed"
    assert [event.seq for event in recorded] == list(range(len(recorded)))
    assert storage.paths() == []  # nothing half-uploaded presented as done


async def test_an_infrastructure_failure_never_escapes_the_loop() -> None:
    # Arrange — settling the job blows up too (DB gone mid-job): the worker logs and moves on.
    class _BrokenQueue(InMemoryVideoJobQueue):
        async def complete(self, *, job_id: str) -> None:
            raise PersistenceError("db is gone")

        async def fail(self, *, job_id: str, error: str) -> None:
            raise PersistenceError("db is still gone")

    queue, storage, events = _BrokenQueue(), InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events)

    # Act / Assert — run_once absorbs even the settle failure.
    assert await worker.run_once() is True


async def test_run_forever_drains_then_stops_on_cancel() -> None:
    # Arrange — the queue signals when the loop settles the job (no polling, no sleeps).
    settled = asyncio.Event()

    class _SignallingQueue(InMemoryVideoJobQueue):
        async def complete(self, *, job_id: str) -> None:
            await super().complete(job_id=job_id)
            settled.set()

    queue, storage, events = _SignallingQueue(), InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events)

    # Act — the loop drains the queue, then idles; cancellation stops it cleanly.
    task = asyncio.create_task(worker.run_forever(poll_interval_seconds=0.001))
    async with asyncio.timeout(5):
        await settled.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assert
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY
