import asyncio
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext, suppress

import structlog
from lunaris_runtime.credentials import CredentialResolver, run_credentials
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
      job, and used as ``run_id`` for the lifecycle events appended to ``run_events`` (seq seeded
      from the store so a re-claim continues past a prior attempt's events, never colliding), so
      one job triangulates across queue → worker → storage → API exactly like a build run does.
    - **Errors stored on the job are user-safe.** The full exception goes to the logs; the job
      row gets only the exception class name (the row is owner-readable wire data).
    - **The render runs on the JOB OWNER's keys.** When a ``credential_resolver`` is wired (the
      cloud worker, which carries no provider keys in its env — tenant-only BYOK), each job's owner
      keys are resolved from the vault and bound as the run scope around ``produce`` — so the
      pipeline's Claude / ElevenLabs calls authenticate as the tenant, never a platform key (V7-T1).
      Without a resolver (local dev / no vault) the render reads the process env, unchanged.
    """

    def __init__(
        self,
        *,
        queue: IVideoJobQueue,
        pipeline: IVideoPipeline,
        storage: IVideoStorage,
        events: IRunEventStore,
        worker_id: str,
        credential_resolver: CredentialResolver | None = None,
        heartbeat_interval_s: float = 60.0,
    ) -> None:
        self._queue = queue
        self._pipeline = pipeline
        self._storage = storage
        self._events = events
        self._worker_id = worker_id
        self._credential_resolver = credential_resolver
        self._heartbeat_interval_s = heartbeat_interval_s

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
            rendered = await self._produce(job)
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

    async def _produce(self, job: VideoJob) -> RenderedVideo:
        """Render the job inside its owner's credential scope (V7-T1), with a heartbeat (V7-T4).

        Only the pipeline's provider calls (Claude / ElevenLabs) are scoped — infrastructure work
        (queue, storage, events) reads the process env and must never enter a tenant-only scope, so
        upload + settle stay outside it. A concurrent heartbeat extends the lease while the render
        runs, so the lease-timeout sweep can tell a live worker from a dead one (the heartbeat is
        outside the credential scope — it touches only the queue's own infra credentials)."""
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        try:
            credentials = await self._resolve_credentials(job)
            with self._credential_scope(credentials):
                return await self._pipeline.produce(job)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat(self, job_id: str) -> None:
        """Extend the job's lease every ``heartbeat_interval_s`` until cancelled (render done). A
        heartbeat failure is logged, never fatal — the loop survives so a transient blip doesn't
        abandon a render (a sustained outage just lets the lease lapse and the job requeue)."""
        while True:
            await asyncio.sleep(self._heartbeat_interval_s)
            try:
                await self._queue.heartbeat(job_id=job_id)
            except PersistenceError:
                _logger.warning("video_worker.heartbeat_failed", job_id=job_id)

    async def _resolve_credentials(self, job: VideoJob) -> Mapping[str, str] | None:
        """The job owner's BYOK keys to bind for this render, or ``None`` to read the process env.

        ``None`` when no resolver is wired (local dev / no vault) — the env fallback, unchanged.
        With a resolver the keys come from the vault (possibly an empty map: a keyed-but-unset
        tenant), which still enters the tenant-only scope so a platform env key can never leak in.
        """
        if self._credential_resolver is None:
            return None
        return await self._credential_resolver(job.user_id)

    @staticmethod
    def _credential_scope(
        credentials: Mapping[str, str] | None,
    ) -> AbstractContextManager[None]:
        """The render's credential context: the tenant keys when resolved, else a no-op (env)."""
        if credentials is None:
            return nullcontext()
        return run_credentials(credentials)

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
    """Gap-free, best-effort lifecycle events for one job (run_id = job_id).

    The seq is seeded from the store on first emit, not hard-started at 0: a job whose first worker
    was lost mid-render is re-claimed and a fresh ``_EventSequence`` is built, but the prior
    attempt's events still hold seqs 0.. under the run_id, and the DB's UNIQUE ``(run_id, seq)``
    index rejects a re-used seq. Continuing PAST the prior attempt keeps a re-claim's transcript
    from colliding (and silently vanishing — the append is best-effort) instead of restarting at 0.
    """

    def __init__(self, events: IRunEventStore, job: VideoJob) -> None:
        self._events = events
        self._run_id = job.id
        self._course_id = job.course_id
        self._owner_id = job.user_id
        self._video_kind = job.kind.value
        self._seq: int | None = None  # seeded from the store on first emit

    async def emit(self, status: VideoJobStatus, label: str) -> None:
        seq = await self._ensure_seq()
        event = RunEvent(
            run_id=self._run_id,
            course_id=self._course_id,
            seq=seq,
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
            self._seq = seq + 1
        except PersistenceError:
            # Append failures never fail the job (IRunEventStore is best-effort at the call
            # site). _seq was NOT advanced — the logged value IS the seq that failed.
            _logger.exception("video_worker.event_append_failed", seq=seq)

    async def _ensure_seq(self) -> int:
        if self._seq is None:
            try:
                latest = await self._events.latest_seq(run_id=self._run_id, owner_id=self._owner_id)
            except PersistenceError:
                # Best-effort: if the seed read fails, start at 0 (the common first-attempt case);
                # a genuine collision is then absorbed by emit, never fatal to the job.
                latest = None
            self._seq = 0 if latest is None else latest + 1
        return self._seq
