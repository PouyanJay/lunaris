import asyncio
from collections.abc import Mapping
from contextlib import AbstractContextManager, nullcontext, suppress

import structlog
from lunaris_runtime.credentials import CredentialResolver, run_credentials
from lunaris_runtime.logging.correlation import bind_run_id, clear_correlation
from lunaris_runtime.persistence import (
    CoverArtifactPaths,
    ICourseStore,
    ICoverJobQueue,
    ICoverStorage,
    PersistenceError,
)
from lunaris_runtime.schema import CoverArtifact, CoverJob, CoverJobStatus

from lunaris_covers.errors import CoverPipelineError
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_covers.protocols.cover_pipeline_protocol import ICoverPipeline, StageReporter

_logger = structlog.get_logger(__name__)


class _CoverCancelledError(Exception):
    """Internal signal: the owner stopped this job mid-render, so the worker aborted the render.

    Raised by ``_produce`` ONLY when the cancel-watcher fired (the job row went CANCELLED, or
    vanished) — distinct from a plain ``asyncio.CancelledError`` (a worker shutdown), which still
    propagates so the supervisor can drain. ``_process`` catches it and stops without settling: the
    row is already CANCELLED and no image was uploaded, so no compute is spent and nothing is
    published (mirrors ``VideoWorker``'s ``_VideoCancelledError``)."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"cover job {job_id!r} cancelled by its owner")
        self.job_id = job_id


class CoverWorker:
    """The cover worker loop: poll → claim → produce → upload → settle. One job at a time.

    Mirrors ``VideoWorker`` end to end — the core loop (T0) plus the lease heartbeat and cancel-
    watcher (T6). Its contract:

    - **It never raises.** A job-level error settles that job FAILED; an infrastructure error is
      logged and absorbed — the next poll retries. A crash-loop must never be one bad job away.
    - **job_id is the run-scope.** Bound into structlog contextvars for every log line inside the
      job, so one cover triangulates across queue → worker → storage → API like a build run does.
    - **Errors stored on the job are user-safe.** The full exception goes to the logs; the job row
      gets only an owner-safe reason.
    - **The render runs on the JOB OWNER's keys.** When a ``credential_resolver`` is wired (the
      cloud worker carries no provider keys — tenant-only BYOK), the owner's OpenAI/Anthropic keys
      are resolved from the vault and bound as the run scope around ``produce`` — so the pipeline's
      provider calls authenticate as the tenant, never a platform key. Without a resolver (local
      dev) the render reads the process env, unchanged. Infrastructure work (queue/storage/course
      store) always uses the worker's own service-role env, outside the tenant scope.
    """

    def __init__(
        self,
        *,
        queue: ICoverJobQueue,
        pipeline: ICoverPipeline,
        storage: ICoverStorage,
        course_store: ICourseStore,
        worker_id: str,
        credential_resolver: CredentialResolver | None = None,
        heartbeat_interval_s: float = 60.0,
        cancel_poll_interval_s: float = 5.0,
    ) -> None:
        self._queue = queue
        self._pipeline = pipeline
        self._storage = storage
        self._course_store = course_store
        self._worker_id = worker_id
        self._credential_resolver = credential_resolver
        self._heartbeat_interval_s = heartbeat_interval_s
        # Tighter than the heartbeat so a stopped render aborts promptly — the cloud worker has no
        # direct channel from the API; this DB poll IS the cancellation signal.
        self._cancel_poll_interval_s = cancel_poll_interval_s

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
            _logger.exception("cover_worker.claim_failed", worker_id=self._worker_id)
            return False
        if job is None:
            return False

        bind_run_id(job.id, worker_id=self._worker_id, course_id=job.course_id)
        try:
            await self._process(job)
        except Exception:
            # The settle path itself failed (infrastructure). The lease stays; a future requeue
            # sweep re-queues the job. Absorb — the loop survives anything.
            _logger.exception("cover_worker.job_unsettled", job_id=job.id)
        finally:
            clear_correlation()
        return True

    async def _process(self, job: CoverJob) -> None:
        _logger.info(
            "cover_worker.job_claimed", style=job.style_preset.value, attempts=job.attempts
        )
        try:
            rendered = await self._produce(job)
            await self._upload(job, rendered)
        except _CoverCancelledError:
            # The owner stopped this job mid-render: the row is already CANCELLED and the render was
            # aborted (no more compute, nothing uploaded). Do NOT settle (complete/fail would be a
            # sticky no-op anyway) — just stop.
            _logger.info("cover_worker.job_cancelled", job_id=job.id)
            return
        except Exception as exc:
            # A render/upload failure is the job's own fault → settle FAILED (no retry of a bad
            # render). CANCELLED settles stick (the queue guards it), so an owner stop still wins.
            _logger.exception("cover_worker.job_failed", failure_class=type(exc).__name__)
            await self._queue.fail(job_id=job.id, error=_user_error(exc))
            return

        # Produce + upload succeeded. Fold the cover onto the course payload, then settle READY. An
        # infrastructure failure here (course store / queue backend down) is NOT a render failure:
        # it propagates out to run_once, which leaves the job in-flight so the lease sweep requeues
        # it — rather than marking a job READY whose Course.cover never got written (the queue's
        # "job state must never be silently wrong" invariant). At-least-once: a requeue re-produces.
        artifact = CoverArtifact(
            status=CoverJobStatus.READY, job_id=job.id, provenance=rendered.provenance
        )
        await self._attach_to_course(job, artifact)
        await self._queue.complete(job_id=job.id)
        _logger.info("cover_worker.job_ready", job_id=job.id)

    async def _produce(self, job: CoverJob) -> RenderedCover:
        """Render the job with a lease heartbeat and a cancel-watcher running alongside (T6).

        The render runs as its own task so the watcher can cancel it the moment the owner stops the
        job — no compute is spent on a stopped cover. The heartbeat extends the lease while the
        render runs, so the lease-timeout sweep can tell a live worker from a dead one. Both run
        outside the credential scope (they touch only the queue's own infra creds).

        A watcher-fired cancel is re-raised as ``_CoverCancelledError`` so ``_process`` aborts
        without settling; an ``asyncio.CancelledError`` the watcher did NOT cause (a worker
        shutdown) is left untouched so the supervisor can still drain."""
        heartbeat = asyncio.create_task(self._heartbeat(job.id))
        render = asyncio.create_task(self._render(job))
        # The watcher sets this BEFORE cancelling the render (synchronously, no await between), so
        # by the time the render task's CancelledError reaches the except below the flag is already
        # set — that is how an owner stop is told apart from a shutdown cancel.
        cancelled = asyncio.Event()
        watcher = asyncio.create_task(self._watch_for_cancel(job.id, render, cancelled))
        try:
            return await render
        except asyncio.CancelledError:
            if cancelled.is_set():
                raise _CoverCancelledError(job.id) from None
            raise  # a shutdown cancel, not an owner stop — let it propagate
        finally:
            watcher.cancel()
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await watcher
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _render(self, job: CoverJob) -> RenderedCover:
        """The pipeline render itself, inside the owner's credential scope. Only the pipeline's
        provider calls (Claude / OpenAI) are scoped; infrastructure work (queue/storage/course
        store) stays on the worker's own env, so upload + settle stay outside it."""
        credentials = await self._resolve_credentials(job)
        with self._credential_scope(credentials):
            return await self._pipeline.produce(job, on_stage=self._stage_reporter(job))

    async def _watch_for_cancel(
        self, job_id: str, render: "asyncio.Task[RenderedCover]", cancelled: asyncio.Event
    ) -> None:
        """Poll the job row; the moment the owner stops it (status CANCELLED) or it vanishes, cancel
        the render task so no compute is wasted. Marks ``cancelled`` first so ``_produce`` can tell
        an owner stop from a shutdown cancel. A transient read blip is retried next tick (the
        heartbeat owns lease health); the watcher never fails the render itself."""
        while True:
            await asyncio.sleep(self._cancel_poll_interval_s)
            try:
                job = await self._queue.get(job_id=job_id)
            except PersistenceError:
                continue
            if job is None or job.status is CoverJobStatus.CANCELLED:
                cancelled.set()
                render.cancel()
                return

    async def _heartbeat(self, job_id: str) -> None:
        """Extend the job's lease every ``heartbeat_interval_s`` until cancelled (render done). A
        heartbeat failure is logged, never fatal — the loop survives so a transient blip doesn't
        abandon a render (a sustained outage just lets the lease lapse and the job requeue)."""
        while True:
            await asyncio.sleep(self._heartbeat_interval_s)
            try:
                await self._queue.heartbeat(job_id=job_id)
            except PersistenceError:
                _logger.warning("cover_worker.heartbeat_failed", job_id=job_id)

    def _stage_reporter(self, job: CoverJob) -> StageReporter:
        async def report(stage: CoverJobStatus) -> None:
            # Best-effort: a flaky progress write must never fail the render. CancelledError still
            # propagates so a worker shutdown isn't swallowed mid-render.
            try:
                await self._queue.update_status(job_id=job.id, status=stage)
            except Exception:
                _logger.warning("cover_worker.stage_report_failed", stage=stage.value)

        return report

    async def _upload(self, job: CoverJob, rendered: RenderedCover) -> None:
        await self._queue.update_status(job_id=job.id, status=CoverJobStatus.UPLOADING)
        paths = CoverArtifactPaths.for_job(job)
        await self._storage.upload(
            path=paths.image, data=rendered.image, content_type=rendered.content_type
        )
        # Dual-theme covers: the LIGHT rendition is a second object, uploaded only when the pipeline
        # produced one (``provenance.has_light_variant`` mirrors this). A dark-only cover uploads
        # just the one image, exactly like a pre-dual-theme cover.
        if rendered.image_light is not None:
            await self._storage.upload(
                path=paths.image_light,
                data=rendered.image_light,
                content_type=rendered.content_type,
            )
        # Structural-provenance contract (CLAUDE.md): its own artifact so the API threads it onto
        # the wire independently of the image.
        await self._storage.upload(
            path=paths.provenance,
            data=rendered.provenance.model_dump_json(by_alias=True).encode(),
            content_type="application/json",
        )

    async def _attach_to_course(self, job: CoverJob, artifact: CoverArtifact) -> None:
        """Fold the finished cover onto the course payload (``Course.cover``) so every surface reads
        it as course material. Covers generate async (post-build), so — unlike video, folded at
        build finalize — the worker writes it here. A course deleted mid-generation is a benign skip
        (``FileNotFoundError`` — the image still uploaded, the job still settles READY). A genuine
        backend failure (``PersistenceError``) is NOT swallowed: it propagates so the caller leaves
        the job in-flight for the lease sweep to requeue, rather than settling a job READY whose
        ``Course.cover`` never got written.

        **Concurrency (course-cover-images T11 AD).** The load + merge + save run in one
        ``to_thread`` hop with no ``await`` between, so within this call they are effectively atomic
        relative to the event loop, and the load re-reads the LATEST course — a concurrent write
        that landed *before* this load is preserved (its fields ride through the ``model_copy``).
        The residual race is only a writer that saves the full Course *between* this load and this
        save (e.g. a lesson-regenerate): last-writer-wins could drop the just-attached cover. This
        is a **pre-existing systemic gap** — NO Course writer uses optimistic concurrency — not
        specific to covers (the worker is merely the first background Course writer to surface it).
        The correct fix is a Course version column + compare-and-set (or a dedicated ``cover``
        column outside the payload JSONB) applied across every writer; that is a Course-persistence
        initiative tracked separately, out of scope for this feature. The cover is re-derivable
        (regenerate) and the at-least-once requeue recovers a lost attach, so the window is fine."""

        def _write() -> None:
            course = self._course_store.load(job.course_id, owner_id=job.user_id)
            self._course_store.save(
                course.model_copy(update={"cover": artifact}), owner_id=job.user_id
            )

        try:
            await asyncio.to_thread(_write)
        except FileNotFoundError:
            _logger.info("cover_worker.course_gone", course_id=job.course_id)

    async def _resolve_credentials(self, job: CoverJob) -> Mapping[str, str] | None:
        """The job owner's BYOK keys to bind for this render, or ``None`` to read the env."""
        if self._credential_resolver is None:
            return None
        return await self._credential_resolver(job.user_id)

    @staticmethod
    def _credential_scope(credentials: Mapping[str, str] | None) -> AbstractContextManager[None]:
        if credentials is None:
            return nullcontext()
        return run_credentials(credentials)


def _user_error(exc: Exception) -> str:
    """The owner-readable failure reason for the job row. A ``CoverPipelineError`` may carry an
    actionable ``user_detail``; without one — including any infrastructure error — only the
    exception class name is surfaced, so the full exception stays in the logs."""
    if isinstance(exc, CoverPipelineError) and exc.user_detail:
        return exc.user_detail
    return f"cover generation failed ({type(exc).__name__})"
