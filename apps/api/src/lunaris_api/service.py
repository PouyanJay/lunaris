import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractContextManager, nullcontext

import structlog
from lunaris_agent import CoursePipeline, LessonRegenerator
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.persistence import (
    ICourseStore,
    IRunEventStore,
    IRunStore,
    OwnerScopedCourseStore,
)
from lunaris_runtime.run_config import run_config
from lunaris_runtime.schema import (
    AgentEvent,
    Clarification,
    Course,
    CourseRun,
    DiscoveryDepth,
    ProgressEvent,
    RunEvent,
    RunStatus,
)

from .progress_sink import QueueAgentSink, QueueProgressSink, StreamItem
from .run_event_recorder import RunEventRecorder
from .run_registry import RunRegistry

logger = structlog.get_logger()

# Bounds for the run-history list, shared with the GET /api/runs router so the HTTP validation and
# the service-layer clamp stay in lockstep (single source of truth).
RUNS_LIMIT_DEFAULT = 50
RUNS_LIMIT_MIN = 1
RUNS_LIMIT_MAX = 200

# Builds the per-run course pipeline (stub / live orchestrator / deep agent) from the shared store.
PipelineFactory = Callable[[ICourseStore], CoursePipeline]

# Resolves a user's BYOK provider keys for a run: user_id → {env-var name: key} for the keys they've
# set (absent providers omitted). Wired from the CredentialVault when BYOK is configured; None when
# BYOK is off (then builds run on the process environment — the admin/single-user/test path).
CredentialResolver = Callable[[str], Awaitable[Mapping[str, str]]]

# Resolves a user's non-secret runtime config for a run: user_id → {env-var name: value} for the
# config keys they've set (absent keys omitted → the run-config env/default fallback). Same shape as
# CredentialResolver but a distinct concept (non-secret model selection); None when config is not
# per-user (auth off) → builds read the process env, today's behaviour.
ConfigResolver = Callable[[str], Awaitable[Mapping[str, str]]]

# The one provider key a build cannot run without: every pipeline tier calls Claude. When BYOK is on
# and the caller hasn't set it, the build is refused up front rather than failing mid-stream. Other
# keys (embeddings/search/youtube) are optional — their absence degrades the capability honestly.
_REQUIRED_KEY_ENV = "ANTHROPIC_API_KEY"

# A streamed item: a ("progress", ProgressEvent) stage, an ("agent", AgentEvent) transcript beat,
# or the terminal ("course", Course). Internal to the service<->router contract; the kind string
# maps directly to the SSE event name.
_StreamItem = tuple[str, ProgressEvent | AgentEvent | Course]


class CourseServiceError(Exception):
    """Base for CourseService domain errors."""


class LessonRegenerationUnsupportedError(CourseServiceError):
    """Raised when the active pipeline cannot regenerate a single lesson (e.g. the deep agent)."""


class RunHistoryUnavailableError(CourseServiceError):
    """Raised when the run-history backend can't be read (Supabase unreachable, table missing).

    Reads, unlike the best-effort writes, surface their failure rather than degrade to an empty
    list (which would lie "no runs yet"); the router maps this to a 503."""


class InvalidCourseIdError(CourseServiceError):
    """Raised when a course_id isn't the safe shape (alphanumeric, ``-``, ``_``). Guards the
    filesystem path against traversal before it becomes ``<id>.json``. Router → 400."""


class CourseDeletionConflictError(CourseServiceError):
    """Raised when deleting a course whose run is still building — cancel it first. Router → 409."""


class CourseNotFoundError(CourseServiceError):
    """Raised when deleting a course with no stored file and no run-history row. Router → 404."""


class RunNotCancellableError(CourseServiceError):
    """Raised when cancelling a run that isn't in-flight (unknown or already done). Router → 404."""


class CourseBuildCancelledError(CourseServiceError):
    """Raised by ``create()`` when its build was explicitly cancelled mid-flight. Converts the
    asyncio ``CancelledError`` (a BaseException that would escape Starlette's exception middleware
    and drop the connection with no response) into a domain error the router maps to a 409."""


class ProviderKeyRequiredError(CourseServiceError):
    """Raised when a BYOK tenant starts a build without their required (Anthropic) key set.

    Only fires when BYOK is configured (a credential resolver is wired) and the build is owned: the
    tenant pays their own LLM bill, so a build can't fall back to the platform key. Router → 400 so
    the web can prompt the user to set their key in Settings. Never carries the key value."""


# A safe course_id is a non-empty run of [A-Za-z0-9_-] — no path separators, dots, or ``..`` that
# could escape the course directory when the id becomes ``<id>.json``. Real ids are uuid4().hex.
_SAFE_COURSE_ID = re.compile(r"[A-Za-z0-9_-]+")


def _is_safe_course_id(course_id: str) -> bool:
    return _SAFE_COURSE_ID.fullmatch(course_id) is not None


class CourseService:
    """Application service over the course pipeline — the API's only door to the agent.

    Builds a course pipeline per run via the injected factory (stub / live orchestrator / deep
    agent) and persists through the shared ``ICourseStore``, so the HTTP layer stays free of
    pipeline wiring.
    """

    def __init__(
        self,
        store: ICourseStore,
        pipeline_factory: PipelineFactory,
        run_store: IRunStore | None = None,
        registry: RunRegistry | None = None,
        event_store: IRunEventStore | None = None,
        *,
        credential_resolver: CredentialResolver | None = None,
        config_resolver: ConfigResolver | None = None,
    ) -> None:
        self._store = store
        self._factory = pipeline_factory
        # Resolves the owner's BYOK keys per run (None when BYOK is off → builds use the process
        # environment).
        self._credential_resolver = credential_resolver
        # Resolves the owner's non-secret config (model selection) per run (None when config isn't
        # per-user → builds read the process env / code defaults).
        self._config_resolver = config_resolver
        # Best-effort: a failed history write must never propagate and break a build (mirrors how
        # the progress/agent sinks default to a no-op for batch callers).
        self._run_store = run_store
        # The replayable build-event log (build-timeline Phase B). Best-effort like the run store;
        # None for callers that don't persist a transcript (batch / tests that don't replay).
        self._event_store = event_store
        # In-flight task registry for cancellation. In production a process-wide singleton is
        # injected (so the cancel request and the build request share it). The lone-instance default
        # is unreachable by cancel requests — fine for callers that never cancel (batch / tests).
        self._registry = registry or RunRegistry()

    def _store_for(self, owner_id: str | None) -> ICourseStore:
        """The course store the pipeline writes through, scoped to the owner (Phase 2).

        A scoped caller gets an ``OwnerScopedCourseStore`` so a plain ``store.save(course)`` deep in
        the harness stamps their ``user_id`` without threading owner_id into the agent. ``None``
        (auth off) returns the shared store unwrapped — byte-for-byte today's behavior.
        """
        if owner_id is None:
            return self._store
        return OwnerScopedCourseStore(self._store, owner_id)

    async def _resolve_run_credentials(self, owner_id: str | None) -> Mapping[str, str] | None:
        """The owner's BYOK keys to bind for this run, or ``None`` to run on the process env.

        ``None`` when the build is unowned (auth off) OR no resolver is wired (BYOK off) — both keep
        today's behaviour: the adapters read ``os.environ``. With BYOK on and an owned build, the
        keys are decrypted from the vault; a missing required (Anthropic) key refuses the build
        (``ProviderKeyRequiredError``) so the tenant never silently falls back to the platform key.
        """
        if owner_id is None or self._credential_resolver is None:
            return None
        credentials = await self._credential_resolver(owner_id)
        if _REQUIRED_KEY_ENV not in credentials:
            # Raise bare — the exception carries no owner_id/value, so it can't leak the user id or
            # a key into ``str(exc)`` / logs; the router supplies the only user-visible message.
            raise ProviderKeyRequiredError
        return credentials

    @staticmethod
    def _credential_scope(credentials: Mapping[str, str] | None) -> AbstractContextManager[None]:
        """The run's credential context: the tenant keys when present, else a no-op (env fallback).

        Enter it around the pipeline factory + ``asyncio.create_task`` so the run task inherits a
        context copy carrying the keys; the parent context never retains them (no leak across an
        async generator's yields)."""
        if credentials is None:
            return nullcontext()
        return run_credentials(credentials)

    async def _resolve_run_config(self, owner_id: str | None) -> Mapping[str, str] | None:
        """The owner's non-secret config (model selection) to bind for this run, or ``None`` to read
        the process env / code defaults. ``None`` when the build is unowned (auth off) or no config
        resolver is wired. Unlike credentials there is no required key — every config has a default,
        so an unset value degrades to the env/code default, never a refusal."""
        if owner_id is None or self._config_resolver is None:
            return None
        return await self._config_resolver(owner_id)

    @staticmethod
    def _config_scope(config: Mapping[str, str] | None) -> AbstractContextManager[None]:
        """The run's config context: the tenant's model choices when present, else a no-op. Entered
        alongside ``_credential_scope`` around the factory + create_task."""
        if config is None:
            return nullcontext()
        return run_config(config)

    async def assert_build_credentials(self, *, owner_id: str | None) -> None:
        """Pre-flight the BYOK requirement before a streamed build starts: raises (router → 400)
        when the required key is missing, returns nothing, binds nothing.

        The SSE response commits its status + headers before the body, so a missing-key refusal must
        surface here rather than mid-stream. ``stream`` resolves again at build time (cheap) to bind
        the keys — kept separate so the decrypted values stay inside the service, never passed back
        through the router."""
        await self._resolve_run_credentials(owner_id)

    async def create(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        clarification: Clarification | None = None,
        discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD,
        owner_id: str | None = None,
    ) -> Course:
        # Resolve the owner's BYOK keys (refuses up front if the required key is missing) before any
        # run is recorded, so a refused build leaves no history row, plus their model config.
        credentials = await self._resolve_run_credentials(owner_id)
        config = await self._resolve_run_config(owner_id)
        await self._record_start(run_id=run_id, course_id=course_id, topic=topic, owner_id=owner_id)
        # Run the pipeline in a registered task so a separate request can cancel this build (the
        # await-full path has no SSE consumer to interrupt). The task is awaited here, so cancelling
        # it raises CancelledError at this await without cancelling the request coroutine itself.
        # The credential + config scopes wrap the factory + create_task so the task inherits the
        # tenant's keys + model choices (a context copy); the adapters then read them, not the env.
        with self._credential_scope(credentials), self._config_scope(config):
            pipeline = self._factory(self._store_for(owner_id))
            task = asyncio.create_task(
                pipeline.run(
                    topic,
                    course_id=course_id,
                    run_id=run_id,
                    clarification=clarification,
                    discovery_depth=discovery_depth,
                )
            )
            self._registry.register(run_id, task, course_id, owner_id)
        try:
            course = await task
        except asyncio.CancelledError:
            if self._registry.was_cancelled(run_id):
                # Convert to a domain error: a raw CancelledError (BaseException) would escape
                # Starlette and drop the connection with no response. The router maps this → 409.
                await self._record_cancelled(course_id, owner_id=owner_id)
                raise CourseBuildCancelledError(run_id) from None
            # Not a registry cancel — this request coroutine itself is being torn down; let it go.
            await self._record_failure(course_id, owner_id=owner_id)
            raise
        except Exception:
            await self._record_failure(course_id, owner_id=owner_id)
            raise
        finally:
            self._registry.discard(run_id)
        await self._record_finish(course, owner_id=owner_id)
        return course

    async def stream(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        clarification: Clarification | None = None,
        discovery_depth: DiscoveryDepth = DiscoveryDepth.STANDARD,
        owner_id: str | None = None,
    ) -> AsyncIterator[_StreamItem]:
        """Run the pipeline, yielding each progress/agent event as it happens, then the course.

        The pipeline runs in a background task feeding one shared queue (coarse ``progress`` stages
        and fine-grained ``agent`` transcript beats, interleaved in emission order); we forward each
        item as it lands and, once the run completes, drain any tail and yield the finished
        course-object. The run task is always cancelled on early exit (a disconnected client) so a
        dropped SSE stream never leaks a running pipeline.

        A pipeline failure is logged here with ``run_id`` (so a truncated stream is still
        triangulatable across layers) and re-raised; the client-visible error frame is a
        later refinement. On client disconnect the consumer is cancelled mid-build — the run is
        recorded FAILED on the way out so it is never left stuck RUNNING in history.
        """
        queue: asyncio.Queue[StreamItem] = asyncio.Queue()
        run_task: asyncio.Task[Course] | None = None
        # Tracks whether a terminal status (COMPLETED/FAILED) was recorded. A client disconnect
        # throws GeneratorExit/CancelledError (both BaseException, NOT Exception) at the suspended
        # ``yield``, bypassing the ``except Exception`` below; the ``finally`` uses this flag to
        # record FAILED for an interrupted run instead of leaving it stuck RUNNING.
        recorded = False
        # Persists each forwarded beat to the replayable build log: buffered, flushed in best-effort
        # batches at phase boundaries (so a crash mid-build still replays up to the last boundary),
        # capped per run, and drained in the ``finally`` below. Never blocks a yield.
        recorder = RunEventRecorder(
            self._event_store, run_id=run_id, course_id=course_id, owner_id=owner_id
        )
        # Resolve the owner's BYOK keys (refuses up front if the required key is missing). The route
        # also pre-flights this via ``assert_build_credentials`` so the refusal is a clean 400
        # before the SSE commits; resolving again here keeps the decrypted keys inside the service.
        credentials = await self._resolve_run_credentials(owner_id)
        config = await self._resolve_run_config(owner_id)
        await self._record_start(run_id=run_id, course_id=course_id, topic=topic, owner_id=owner_id)
        try:
            # The credential + config scopes wrap only the factory + create_task (no yields inside),
            # so the run task inherits the tenant's keys + model choices as a context copy while the
            # generator's own context — the one live across each yield — never retains them.
            with self._credential_scope(credentials), self._config_scope(config):
                pipeline = self._factory(self._store_for(owner_id))
                run_task = asyncio.create_task(
                    pipeline.run(
                        topic,
                        course_id=course_id,
                        run_id=run_id,
                        progress=QueueProgressSink(queue),
                        agent=QueueAgentSink(queue),
                        clarification=clarification,
                        discovery_depth=discovery_depth,
                    )
                )
                self._registry.register(
                    run_id, run_task, course_id, owner_id
                )  # cancellable by a separate request (scoped to the owner)
            while True:
                next_event_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {next_event_task, run_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if next_event_task in done:
                    item = next_event_task.result()  # already a (kind, payload) tuple
                    await recorder.record(item)
                    yield item
                    continue
                # The run finished: cancel the pending get, flush any queued tail, stop.
                next_event_task.cancel()
                while not queue.empty():
                    item = queue.get_nowait()
                    await recorder.record(item)
                    yield item
                break
            if run_task.cancelled():
                # Explicitly cancelled via the registry — record CANCELLED and end the stream
                # cleanly (no terminal course frame), distinct from the disconnect→FAILED path. The
                # cancel handler also records CANCELLED (disconnect-proof); a repeat write of the
                # same terminal status is idempotent — kept for the consumer-survives-cancel case.
                await self._record_cancelled(course_id, owner_id=owner_id)
                recorded = True
                return
            course = run_task.result()  # .result() propagates a pipeline failure here
            await self._record_finish(course, owner_id=owner_id)
            recorded = True
            yield ("course", course)
        except Exception:
            logger.error("course_stream_failed", course_id=course_id, run_id=run_id, exc_info=True)
            await self._record_failure(course_id, owner_id=owner_id)
            recorded = True
            raise
        finally:
            # Drain the buffered build-log tail on every terminal path (success, failure, cancel,
            # or disconnect) so a run's last batch is persisted; best-effort, safe to await here
            # (no ``yield`` in ``finally``).
            await recorder.flush()
            # Capture intent before discard clears it, so a disconnect that races ahead of the
            # post-loop cancelled-branch still lands CANCELLED for an explicitly cancelled run.
            cancelled = self._registry.was_cancelled(run_id)
            self._registry.discard(run_id)
            if run_task is not None and not run_task.done():
                run_task.cancel()
            if not recorded:
                # The consumer was cancelled before the run reached a terminal event, so neither
                # branch above ran — the run would otherwise stay stuck RUNNING in history. Record a
                # terminal status on the way out: CANCELLED for an explicit cancel (the Terminate
                # control), else FAILED for a plain client disconnect. Awaiting here is safe during
                # async-gen finalization (we don't ``yield`` in ``finally``); both writes are
                # best-effort (never raise).
                if cancelled:
                    event = "run_recorded_cancelled_on_disconnect"
                    await self._record_cancelled(course_id, owner_id=owner_id)
                else:
                    event = "run_recorded_failed_on_disconnect"
                    await self._record_failure(course_id, owner_id=owner_id)
                logger.info(event, course_id=course_id, run_id=run_id)

    def get(self, course_id: str, *, owner_id: str | None = None) -> Course | None:
        # An unsafe id can't name a stored course (ids are uuid4().hex); treat it as not-found
        # rather than let it reach path_for — the same traversal guard delete_course applies.
        if not _is_safe_course_id(course_id):
            return None
        try:
            return self._store.load(course_id, owner_id=owner_id)
        except FileNotFoundError:
            return None

    async def regenerate_lesson(
        self, course_id: str, lesson_id: str, *, run_id: str, owner_id: str | None = None
    ) -> Course | None:
        """Re-author one lesson of an existing course and return the updated course.

        Returns ``None`` if the course or lesson is unknown. Raises the unsupported error if the
        active pipeline can't regenerate a single lesson (e.g. the deep-agent builder), or
        ``ProviderKeyRequiredError`` when a BYOK tenant's required key is unset. Like a full build,
        the re-author runs in the owner's credential scope so it uses the tenant's own keys.
        """
        if not _is_safe_course_id(course_id):
            return None  # unsafe id can't name a stored course → not-found (router → 404)
        pipeline = self._factory(self._store_for(owner_id))
        # Support check before the credential check: an unsupported pipeline is a 501 regardless of
        # keys, and constructing it above touches no key (the clients are lazy).
        if not isinstance(pipeline, LessonRegenerator):
            raise LessonRegenerationUnsupportedError(type(pipeline).__name__)
        credentials = await self._resolve_run_credentials(owner_id)
        config = await self._resolve_run_config(owner_id)
        with self._credential_scope(credentials), self._config_scope(config):
            return await pipeline.regenerate_lesson(course_id, lesson_id, run_id=run_id)

    async def delete_course(self, course_id: str, *, owner_id: str | None = None) -> None:
        """Delete a course and its per-course assets: the stored course-object + run-history row.

        Guards (one door for all callers): rejects an unsafe id before touching the filesystem;
        refuses to delete a course whose run is still building (cancel it first); raises not-found
        if neither asset exists. Otherwise idempotent — clearing a stray file or row alone succeeds.

        Scoped to ``owner_id`` (Phase 2): every asset delete is owner-filtered, so a user deleting
        another's course finds nothing (not-found) and never touches the other user's data.
        """
        if not _is_safe_course_id(course_id):
            raise InvalidCourseIdError(course_id)
        await self._ensure_not_running(course_id, owner_id=owner_id)
        await self._purge_course_assets(course_id, owner_id=owner_id)

    async def _ensure_not_running(self, course_id: str, *, owner_id: str | None = None) -> None:
        """Block deleting a course whose build is still in progress. With no run store wired there's
        no run history and so no live build to protect, so the guard is intentionally skipped."""
        if self._run_store is None:
            return
        run = await self._run_store.get(course_id=course_id, owner_id=owner_id)
        if run is not None and run.status == RunStatus.RUNNING:
            raise CourseDeletionConflictError(course_id)

    async def _purge_course_assets(self, course_id: str, *, owner_id: str | None = None) -> None:
        """Remove the stored course + run row + build-event log; not-found if neither existed."""
        # Off-load the (possibly network-backed) delete so the event loop isn't blocked.
        course_deleted = await asyncio.to_thread(
            lambda: self._store.delete(course_id, owner_id=owner_id)
        )
        row_deleted = (
            await self._run_store.delete(course_id=course_id, owner_id=owner_id)
            if self._run_store is not None
            else False
        )
        # Guard before the secondary purge: not-found is keyed on the authoritative assets (the
        # course + run row); the event-log I/O should only fire for a course that actually existed.
        if not course_deleted and not row_deleted:
            raise CourseNotFoundError(course_id)
        events_purged = await self._purge_event_log(course_id, owner_id=owner_id)
        logger.info(
            "course_deleted",
            course_id=course_id,
            course_deleted=course_deleted,
            row_deleted=row_deleted,
            events_purged=events_purged,
        )

    async def _purge_event_log(self, course_id: str, *, owner_id: str | None = None) -> int:
        """Best-effort: a purge failure must never block the user's delete (the build-event log is
        non-authoritative operational data)."""
        if self._event_store is None:
            return 0
        try:
            return await self._event_store.delete_for_course(course_id=course_id, owner_id=owner_id)
        except Exception:
            logger.warning("run_events_purge_failed", course_id=course_id, exc_info=True)
            return 0

    async def list_runs(
        self, *, limit: int = RUNS_LIMIT_DEFAULT, owner_id: str | None = None
    ) -> list[CourseRun]:
        """Return an empty list when no run store is wired (batch / no-history callers), so the
        endpoint degrades gracefully instead of failing. ``limit`` is clamped to a sane range for
        direct callers; the HTTP router already validates it upstream.
        """
        if self._run_store is None:
            return []
        bounded = max(RUNS_LIMIT_MIN, min(limit, RUNS_LIMIT_MAX))
        try:
            return await self._run_store.list_recent(limit=bounded, owner_id=owner_id)
        except Exception as exc:
            # A configured backend that fails to read is a real outage — surface it (vs. a silent
            # empty list, which would lie "no runs yet"). Logged with the run_id from contextvars so
            # the failure is triangulatable across layers; the router maps it to a recoverable 503.
            logger.warning("run_history_list_failed", limit=bounded, exc_info=True)
            raise RunHistoryUnavailableError("Run history backend is unavailable") from exc

    async def list_run_events(self, run_id: str, *, owner_id: str | None = None) -> list[RunEvent]:
        """Return a run's persisted build log in emission order (for timeline replay).

        Empty when no event store is wired or the run left no trace (a course built before Phase B,
        or one whose log writes all failed) — the UI renders a "no build record" state, not an
        error. Scoped to ``owner_id`` (Phase 2): another user's transcript reads as empty, so a
        guessed ``run_id`` discloses nothing. A configured store that fails to *read* is a real
        outage → a ``RunHistoryUnavailableError`` (router → 503), mirroring ``list_runs`` (a silent
        empty list would lie "never built").
        """
        if self._event_store is None:
            return []
        try:
            return await self._event_store.list_for_run(run_id=run_id, owner_id=owner_id)
        except Exception as exc:
            logger.warning("run_events_list_failed", run_id=run_id, exc_info=True)
            raise RunHistoryUnavailableError("Build event log is unavailable") from exc

    async def cancel_run(self, run_id: str, *, owner_id: str | None = None) -> None:
        """Request cancellation of an in-flight run, and record CANCELLED here.

        Signalling the task isn't enough: the Terminate control drops the SSE right after, so the
        stream coroutine's teardown can be cut off by the disconnect before it writes the terminal
        status — leaving the run stuck RUNNING. Recording it from this stable request (which isn't
        torn down) is disconnect-proof; the stream's later write is the same status (idempotent).
        Raises RunNotCancellableError (router → 404) when nothing is in-flight."""
        course_id = self._registry.cancel(run_id, owner_id)
        if course_id is None:
            raise RunNotCancellableError(run_id)
        await self._record_cancelled(course_id, owner_id=owner_id)
        logger.info("run_cancel_requested", run_id=run_id)

    async def _record_start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None:
        """Record the run as ``RUNNING`` — best-effort (a history failure never breaks a build)."""
        if self._run_store is None:
            return
        try:
            await self._run_store.start(
                run_id=run_id, course_id=course_id, topic=topic, owner_id=owner_id
            )
        except Exception:
            logger.warning(
                "run_history_start_failed", course_id=course_id, run_id=run_id, exc_info=True
            )

    async def _record_finish(self, course: Course, *, owner_id: str | None = None) -> None:
        """Mark the run COMPLETED with the artifact's KC/module counts — best-effort."""
        if self._run_store is None:
            return
        try:
            await self._run_store.finish(
                course_id=course.id,
                status=RunStatus.COMPLETED,
                kc_count=len(course.graph.nodes),
                module_count=len(course.modules),
                owner_id=owner_id,
            )
        except Exception:
            logger.warning("run_history_finish_failed", course_id=course.id, exc_info=True)

    async def _record_failure(self, course_id: str, *, owner_id: str | None = None) -> None:
        """Mark the run FAILED — best-effort (a no-op if the start row was never written)."""
        if self._run_store is None:
            return
        try:
            await self._run_store.finish(
                course_id=course_id,
                status=RunStatus.FAILED,
                kc_count=0,
                module_count=0,
                owner_id=owner_id,
            )
        except Exception:
            logger.warning("run_history_mark_failed_error", course_id=course_id, exc_info=True)

    async def _record_cancelled(self, course_id: str, *, owner_id: str | None = None) -> None:
        """Mark the run CANCELLED — best-effort (a no-op if the start row was never written)."""
        if self._run_store is None:
            return
        try:
            await self._run_store.finish(
                course_id=course_id,
                status=RunStatus.CANCELLED,
                kc_count=0,
                module_count=0,
                owner_id=owner_id,
            )
        except Exception:
            logger.warning("run_history_mark_cancelled_error", course_id=course_id, exc_info=True)
