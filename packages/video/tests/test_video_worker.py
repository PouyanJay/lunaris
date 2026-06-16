"""Worker-loop tests: claim → produce → upload → settle, against the in-memory queue/storage
doubles and a real stub pipeline. The loop's contract: it never raises (job-level errors settle
the job; infrastructure errors are logged and retried next poll), every artifact lands under the
{user_id}/{course_id}/{job_id}/ path convention, the job's lifecycle is appended to run_events
under run_id = job_id, and the job_id is bound into structlog contextvars while the job runs."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
import structlog
from lunaris_runtime.logging import configure_logging
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    PersistenceError,
)
from lunaris_runtime.schema import (
    RunEventKind,
    VideoArtifact,
    VideoJob,
    VideoJobStatus,
    VideoKind,
    VideoProvenance,
)
from lunaris_video import RenderedVideo, StubVideoPipeline, VideoWorker
from lunaris_video.errors import FactualGateError, SceneRenderError, VideoPipelineError

_OWNER = "00000000-0000-0000-0000-000000000001"


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]


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
    # V4-T1: the planned contract fingerprint is written back onto the job row (regen cache key).
    assert job.contract_hash == "stub"
    prefix = f"{_OWNER}/course-1/job-1"
    mp4_path, poster_path = f"{prefix}/final.mp4", f"{prefix}/poster.jpg"
    contracts_path, timing_path = f"{prefix}/scene_contracts.json", f"{prefix}/timing.json"
    provenance_path, artifact_path = f"{prefix}/provenance.json", f"{prefix}/artifact.json"
    assert sorted(storage.paths()) == sorted(
        [mp4_path, poster_path, contracts_path, timing_path, provenance_path, artifact_path]
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
    # V4-T1: the finished VideoArtifact is written at the source — what finalize folds in.
    artifact = VideoArtifact.model_validate_json(storage.read(artifact_path))
    assert artifact.status == VideoJobStatus.READY
    assert artifact.provenance is not None and artifact.provenance.job_id == "job-1"
    assert artifact.narrated is False  # the stub is silent


async def test_the_worker_reflects_pipeline_stages_on_the_job_and_the_log() -> None:
    # Arrange — the pipeline reports its stages; the worker must reflect each on the job row (the
    # status poll → the reader's progress bar) AND append it to the run_events log (the canvas).
    class _StagedPipeline:
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
            assert on_stage is not None
            await on_stage(VideoJobStatus.RENDERING)
            await on_stage(VideoJobStatus.ASSEMBLING)
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
    worker = _worker(queue, storage, events, pipeline=_StagedPipeline())

    # Act
    await worker.run_once()

    # Assert — the lifecycle log walks planning (claim) → rendering → assembling → ready, gap-free,
    # and the job row ends READY (the terminal settle wins over the last stage).
    recorded = await events.list_for_run(run_id="job-1", owner_id=_OWNER)
    assert [e.payload.get("status") for e in recorded] == [
        "planning",
        "rendering",
        "assembling",
        "ready",
    ]
    assert [e.seq for e in recorded] == [0, 1, 2, 3]
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY


async def test_a_narrated_video_uploads_a_captions_track() -> None:
    # Arrange — a narrated render carries WebVTT captions; a silent one (the stub) carries none (the
    # exact-path-set assertion in test_run_once_processes_a_job_end_to_end proves silent uploads 0).
    class _NarratedPipeline:
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
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


async def test_a_requeued_job_does_not_collide_run_events_seqs() -> None:
    # Arrange — run_events has a UNIQUE (run_id, seq) index; a video job's lifecycle is logged under
    # run_id = job_id, gap-free from 0. A worker lost mid-render (KEDA scale / deploy / OOM) leaves
    # the job in-flight with its planning event (seq 0) on record; the lease sweep requeues it and a
    # SECOND worker re-claims it. The re-claim must NOT restart seq at 0 and collide.
    now = datetime(2026, 1, 1, tzinfo=UTC)
    clock = [now]
    queue = InMemoryVideoJobQueue(clock=lambda: clock[0])
    storage, events = InMemoryVideoStorage(), InMemoryRunEventStore()
    await queue.enqueue(_job())

    # Attempt 1: the worker claims, emits its planning event, then is lost mid-render (produce hangs
    # until the worker task is cancelled — the job is never settled).
    started = asyncio.Event()

    class _LostMidRender:
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
            started.set()
            await asyncio.Event().wait()  # never resolves — the worker dies here
            raise AssertionError("unreachable")  # pragma: no cover

    worker = _worker(queue, storage, events, pipeline=_LostMidRender())
    task = asyncio.create_task(worker.run_once())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [e.seq for e in await events.list_for_run(run_id="job-1")] == [0]  # planning, abandoned

    # The lease expires; the sweep requeues the in-flight job for another worker.
    clock[0] = now + timedelta(seconds=120)
    await queue.sweep_stale_leases(lease_seconds=60, max_attempts=5)

    # Attempt 2: a healthy worker re-claims and runs it to completion.
    assert await _worker(queue, storage, events).run_once() is True

    # Assert — the re-claim continued PAST the abandoned attempt's seq 0 (no collision dropped its
    # events): every seq is unique and the 'ready' settle event survived to the log.
    recorded = await events.list_for_run(run_id="job-1", owner_id=_OWNER)
    seqs = [e.seq for e in recorded]
    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))  # no duplicate (run_id, seq)
    assert recorded[-1].payload.get("status") == "ready"  # the re-claim's settle landed


async def test_event_seq_seed_falls_back_to_zero_when_the_store_read_fails() -> None:
    # Arrange — seeding the seq reads latest_seq; if that read hiccups, the lifecycle log is
    # best-effort, so the worker still emits (from 0) and the job still settles READY.
    class _SeedReadFailsStore(InMemoryRunEventStore):
        async def latest_seq(self, *, run_id: str, owner_id: str | None = None) -> int | None:
            raise PersistenceError("seed read failed")

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        _SeedReadFailsStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events)

    # Act / Assert — the unreadable seed never fails the job; it completes and logs from seq 0.
    assert await worker.run_once() is True
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.READY
    recorded = await events.list_for_run(run_id="job-1", owner_id=_OWNER)
    assert [e.seq for e in recorded] == list(range(len(recorded)))
    assert recorded[0].seq == 0


async def test_run_once_binds_the_job_id_into_log_context_while_working() -> None:
    # Arrange — a pipeline double that captures the structlog contextvars active DURING the job.
    captured: dict[str, object] = {}

    class _CapturingPipeline:
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
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
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
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


@pytest.mark.parametrize(
    ("exc", "expected_kind", "expected_scene"),
    [
        (
            FactualGateError("S2_mechanism", unsupported=["42%"], detail="smuggled figure"),
            "factual",
            "S2_mechanism",
        ),
        (SceneRenderError("S1_hook", attempts=4, error_tail="boom"), "render", "S1_hook"),
        (ValueError("source does not parse: unterminated string literal"), "codegen_parse", None),
        (VideoPipelineError("some pipeline failure"), "pipeline", None),
        (RuntimeError("queue exploded"), "infrastructure", None),
    ],
)
async def test_job_failed_logs_a_structured_failure_taxonomy(
    exc: Exception,
    expected_kind: str,
    expected_scene: str | None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange — each exception class the pipeline can raise maps to a queryable failure_kind, so the
    # failure taxonomy is a first-class structured read (no more az/KQL spelunking, E1). The exact
    # class rides alongside (failure_class) so a coarse kind is always disambiguable, and a scene_id
    # is captured when the error carries one. Read off stdout JSON (not structlog's capture_logs):
    # the agent package exercises this module logger under the cached JSON pipeline, so by the time
    # this test runs the logger is frozen and capture_logs cannot intercept it — reading the
    # configured stdout sink is order-independent (the apps/api recorder tests do the same).
    configure_logging(json_output=True)

    class _ExplodingPipeline:
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
            raise exc

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events, pipeline=_ExplodingPipeline())

    # Act
    assert await worker.run_once() is True

    # Assert — exactly one job_failed event, carrying the taxonomy fields.
    failed = [e for e in _json_log_lines(capsys) if e.get("event") == "video_worker.job_failed"]
    assert len(failed) == 1
    assert failed[0]["failure_kind"] == expected_kind
    assert failed[0]["failure_class"] == type(exc).__name__
    assert failed[0]["scene_id"] == expected_scene


async def test_an_actionable_failure_reason_reaches_the_job_row() -> None:
    # Arrange — a VideoPipelineError carrying a user_detail. The owner-readable row gets the
    # actionable line; the internal cause (which may include a vision critique) never does.
    class _DesyncPipeline:
        async def produce(self, job: VideoJob, *, on_stage=None) -> RenderedVideo:
            raise VideoPipelineError(
                "internal: scene render exhausted its budget",
                user_detail="We couldn't generate this video. Try regenerating it.",
            )

    queue, storage, events = (
        InMemoryVideoJobQueue(),
        InMemoryVideoStorage(),
        InMemoryRunEventStore(),
    )
    await queue.enqueue(_job())
    worker = _worker(queue, storage, events, pipeline=_DesyncPipeline())

    # Act
    assert await worker.run_once() is True

    # Assert — the actionable reason is on the row; the internal cause is not (logs only).
    job = await queue.get(job_id="job-1")
    assert job is not None and job.status == VideoJobStatus.FAILED
    assert job.error == "We couldn't generate this video. Try regenerating it."
    assert "internal" not in (job.error or "")


async def test_an_infrastructure_failure_never_escapes_the_loop() -> None:
    # Arrange — settling the job blows up too (DB gone mid-job): the worker logs and moves on.
    class _BrokenQueue(InMemoryVideoJobQueue):
        async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
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
        async def complete(self, *, job_id: str, contract_hash: str | None = None) -> None:
            await super().complete(job_id=job_id, contract_hash=contract_hash)
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
