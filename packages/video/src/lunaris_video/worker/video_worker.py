import asyncio

import structlog
from lunaris_runtime.logging.correlation import bind_run_id, clear_correlation
from lunaris_runtime.persistence import (
    IRunEventStore,
    IVideoJobQueue,
    IVideoStorage,
    PersistenceError,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import (
    RunEvent,
    RunEventKind,
    VideoArtifact,
    VideoJob,
    VideoJobStatus,
    VideoProvenance,
)

from lunaris_video.models.rendered_video import RenderedVideo
from lunaris_video.protocols.video_pipeline_protocol import IVideoPipeline
from lunaris_video.schemas import TimingManifest

_logger = structlog.get_logger(__name__)


class VideoWorker:
    """The video worker loop: poll → claim → produce → upload → settle. One job at a time.

    The same loop runs everywhere — in-process under ``make run`` locally, as a dedicated
    container in cloud (plan §1.1); deployment is the only variable. Its contract:

    - **It never raises.** A job-level error settles that job FAILED; an infrastructure error
      (queue/storage down) is logged and absorbed — the next poll retries. A worker crash-loop
      must never be one bad job away.
    - **job_id is the run-scope.** Bound into structlog contextvars for every log line inside the
      job, and used as ``run_id`` for the lifecycle events appended to ``run_events`` (gap-free
      seq from 0), so one job triangulates across queue → worker → storage → API exactly like a
      build run does.
    - **Errors stored on the job are user-safe.** The full exception goes to the logs; the job
      row gets only the exception class name (the row is owner-readable wire data).
    """

    def __init__(
        self,
        *,
        queue: IVideoJobQueue,
        pipeline: IVideoPipeline,
        storage: IVideoStorage,
        events: IRunEventStore,
        worker_id: str,
    ) -> None:
        self._queue = queue
        self._pipeline = pipeline
        self._storage = storage
        self._events = events
        self._worker_id = worker_id

    async def run_forever(self, *, poll_interval_seconds: float = 2.0) -> None:
        """Drain the queue forever; idle-poll when empty. Cancellation is the stop signal."""
        while True:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(poll_interval_seconds)

    async def run_once(self) -> bool:
        """Claim and fully process at most one job. Returns whether a job was claimed."""
        try:
            job = await self._queue.claim(worker_id=self._worker_id)
        except PersistenceError:
            _logger.exception("video_worker.claim_failed", worker_id=self._worker_id)
            return False
        if job is None:
            return False

        bind_run_id(job.id, worker_id=self._worker_id, course_id=job.course_id)
        try:
            await self._process(job)
        except Exception:
            # The settle path itself failed (infrastructure). The lease stays; a future requeue
            # sweep re-queues the job. Absorb — the loop survives anything.
            _logger.exception("video_worker.job_unsettled", job_id=job.id)
        finally:
            clear_correlation()
        return True

    async def _process(self, job: VideoJob) -> None:
        sequence = _EventSequence(self._events, job)
        await sequence.emit(VideoJobStatus.PLANNING, "claimed — producing video")
        _logger.info("video_worker.job_claimed", kind=job.kind.value, attempts=job.attempts)

        try:
            rendered = await self._pipeline.produce(job)
            artifact = _build_artifact(job, rendered)
            await self._upload_artifacts(job, rendered, artifact)
        except Exception as exc:
            # Full detail to the logs; only the class name to the owner-readable job row.
            _logger.exception("video_worker.job_failed")
            await self._queue.fail(
                job_id=job.id, error=f"video generation failed ({type(exc).__name__})"
            )
            await sequence.emit(VideoJobStatus.FAILED, "video generation failed")
            return

        # Write the planned contract fingerprint back onto the job row — the durable cross-process
        # regeneration cache key (V4-T1; V1 deferred it). None when the producer built none.
        contract_hash = artifact.provenance.contract_hash if artifact.provenance else None
        await self._queue.complete(job_id=job.id, contract_hash=contract_hash)
        await sequence.emit(VideoJobStatus.READY, "video ready")
        _logger.info("video_worker.job_ready", job_id=job.id)

    async def _upload_artifacts(
        self, job: VideoJob, rendered: RenderedVideo, artifact: VideoArtifact
    ) -> None:
        paths = VideoArtifactPaths.for_job(job)
        await self._storage.upload(path=paths.mp4, data=rendered.mp4, content_type="video/mp4")
        await self._storage.upload(
            path=paths.poster, data=rendered.poster, content_type="image/jpeg"
        )
        # The contract + timing manifest are what regeneration and a later re-voice need (plan
        # §8.2) — kept alongside the playable artifacts under the same job prefix.
        await self._storage.upload(
            path=paths.contracts, data=rendered.contracts_json, content_type="application/json"
        )
        await self._storage.upload(
            path=paths.timing, data=rendered.timing_json, content_type="application/json"
        )
        # WebVTT captions ride only on a narrated video — a silent one writes none rather than an
        # empty track (the API then offers no captions URL, and the player adds no track).
        if rendered.captions is not None:
            await self._storage.upload(
                path=paths.captions, data=rendered.captions, content_type="text/vtt"
            )
        # Structural-provenance contract (CLAUDE.md): persisted as its own artifact so the API can
        # thread it onto the wire independently of the playback artifacts. A producer that built no
        # provenance writes none rather than a bogus empty object.
        if rendered.provenance_json:
            await self._storage.upload(
                path=paths.provenance,
                data=rendered.provenance_json,
                content_type="application/json",
            )
        # The finished VideoArtifact (status + provenance + narrated + duration), built at the
        # source so the build's finalize folds it into the lesson with a single read (V4-T1).
        await self._storage.upload(
            path=paths.artifact,
            data=artifact.model_dump_json(by_alias=True).encode(),
            content_type="application/json",
        )


def _build_artifact(job: VideoJob, rendered: RenderedVideo) -> VideoArtifact:
    """The finished video as it rides in the course payload, built at the source (V4-T1).

    Provenance comes from what the pipeline produced (``None`` for a producer that built none);
    ``narrated`` + ``duration_s`` are read off the timing manifest — the one source of truth for
    playback metadata, so ``artifact.json`` and the GET endpoint agree without extra work."""
    provenance = (
        VideoProvenance.model_validate_json(rendered.provenance_json)
        if rendered.provenance_json
        else None
    )
    manifest = TimingManifest.model_validate_json(rendered.timing_json)
    return VideoArtifact(
        kind=job.kind,
        status=VideoJobStatus.READY,
        job_id=job.id,
        provenance=provenance,
        narrated=manifest.is_voiced,
        duration_s=manifest.total_s,
    )


class _EventSequence:
    """Gap-free, best-effort lifecycle events for one job (run_id = job_id)."""

    def __init__(self, events: IRunEventStore, job: VideoJob) -> None:
        self._events = events
        self._run_id = job.id
        self._course_id = job.course_id
        self._owner_id = job.user_id
        self._video_kind = job.kind.value
        self._seq = 0

    async def emit(self, status: VideoJobStatus, label: str) -> None:
        event = RunEvent(
            run_id=self._run_id,
            course_id=self._course_id,
            seq=self._seq,
            kind=RunEventKind.PROGRESS,
            payload={
                "event": "video_job",
                "jobId": self._run_id,
                "videoKind": self._video_kind,
                "status": status.value,
                "label": label,
            },
        )
        try:
            await self._events.append(events=[event], owner_id=self._owner_id)
            self._seq += 1
        except PersistenceError:
            # Append failures never fail the job (IRunEventStore is best-effort at the call
            # site). _seq was NOT incremented — the logged value IS the seq that failed.
            _logger.exception("video_worker.event_append_failed", seq=self._seq)
