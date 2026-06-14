import asyncio
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass

import structlog
from lunaris_agent import CoursePipeline, LessonRegenerator
from lunaris_runtime.capabilities import CAPABILITY_SPECS
from lunaris_runtime.credentials import run_credentials
from lunaris_runtime.device_bridge import BridgeLimits, DeviceBridge, run_device_bridge
from lunaris_runtime.persistence import (
    ICourseStore,
    IRunEventStore,
    IRunStore,
    OwnerScopedCourseStore,
    PersistenceError,
)
from lunaris_runtime.run_config import run_config
from lunaris_runtime.schema import (
    AgentEvent,
    CapabilityName,
    Clarification,
    Course,
    CourseRun,
    DiscoveryDepth,
    ProgressEvent,
    RunEvent,
    RunStatus,
)
from lunaris_runtime.video_build import IVideoBuildCoordinator, run_video_coordinator

from .device_bridge_registry import DeviceBridgeRegistry
from .draft_throttle import DraftReservation, KeylessBuildThrottle
from .progress_sink import QueueAgentSink, QueueProgressSink, StreamItem
from .run_event_recorder import RunEventRecorder
from .run_registry import RunRegistry
from .schemas.compute import ComputeChoice

logger = structlog.get_logger()

# The env var whose presence means the LLM ran live (else keyless Draft) — read once from the shared
# capability table so the throttle's keyless check and the live badge agree on what "keyed" means.
_LLM_KEY_ENV = next(s.env_var for s in CAPABILITY_SPECS if s.capability is CapabilityName.LLM)
# The per-day cap bucket for a build with no owner (auth off / single-user instance).
_LOCAL_OWNER_KEY = "__local__"

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

# Builds the per-run video-build coordinator for an owner (explainer-video V4): owner_id → the
# coordinator that enqueues the build's lesson videos. Wired ONLY when the operator flag
# VIDEO_GENERATION_ENABLED is on (its presence is the operator gate); None otherwise → no videos.
VideoCoordinatorFactory = Callable[[str], IVideoBuildCoordinator]

# A streamed item: a ("progress", ProgressEvent) stage, an ("agent", AgentEvent) transcript beat,
# or the terminal ("course", Course). Internal to the service<->router contract; the kind string
# maps directly to the SSE event name.
_StreamItem = tuple[str, ProgressEvent | AgentEvent | Course]


@dataclass(frozen=True)
class BuildAdmission:
    """The outcome of admitting a build (keyless-fallbacks T6): the resolved run credentials and,
    for a throttled keyless build, the held Draft slot to release when the build's task ends.

    Computed once by :meth:`CourseService.admit_build` so a refusal is a real HTTP status before the
    response starts (the SSE path can't surface a 429 once it has begun streaming). ``reservation``
    is ``None`` for a keyed build or when no throttle is wired — those are never rationed.
    ``device_bridge`` is the run's registered completion bridge when this is a keyless build whose
    learner chose device compute, else ``None`` (server compute / keyed — today's behaviour)."""

    credentials: Mapping[str, str] | None
    reservation: DraftReservation | None
    device_bridge: DeviceBridge | None = None


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
        video_coordinator_factory: VideoCoordinatorFactory | None = None,
        throttle: KeylessBuildThrottle | None = None,
        bridge_registry: DeviceBridgeRegistry | None = None,
        bridge_limits: BridgeLimits | None = None,
    ) -> None:
        self._store = store
        self._factory = pipeline_factory
        # Admission control for keyless (Draft) builds (T6): operator switch + per-tenant per-day
        # cap + concurrency limit. None (the default) leaves keyless builds unthrottled — today's.
        self._throttle = throttle
        # Resolves the owner's BYOK keys per run (None when BYOK is off → builds use the process
        # environment).
        self._credential_resolver = credential_resolver
        # Resolves the owner's non-secret config (model selection) per run (None when config isn't
        # per-user → builds read the process env / code defaults).
        self._config_resolver = config_resolver
        # Builds the per-run video-build coordinator (explainer-video V4). None when the operator
        # kill-switch VIDEO_GENERATION_ENABLED is off → builds enqueue no videos (today's path).
        self._video_coordinator_factory = video_coordinator_factory
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
        # In-flight device bridges (device-compute Draft builds). The same process-wide singleton
        # the bridge router reads, so the tab's polls find the bridge this service registers. None
        # (the default) means device compute is unavailable — admission falls back to the server.
        self._bridge_registry = bridge_registry
        # The bridge's time bounds (tab liveness, per-completion ceiling), operator-tunable via
        # Settings; None → the code defaults.
        self._bridge_limits = bridge_limits

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
        keys are decrypted from the vault and returned as-is, including an empty map. A missing key
        no longer refuses the build: the run scope then carries no key for that provider, so the
        adapter falls back to its keyless local provider (a "Draft" build) rather than 400-ing.
        """
        if owner_id is None or self._credential_resolver is None:
            return None
        return await self._credential_resolver(owner_id)

    @staticmethod
    def _is_keyless_llm(credentials: Mapping[str, str] | None) -> bool:
        """Whether this build will run the LLM keyless (a Draft build) — mirrors ``resolve_secret``:
        a scoped tenant with no Anthropic key, or no scope and no key in the process env."""
        if credentials is not None:
            return not credentials.get(_LLM_KEY_ENV)
        return not os.environ.get(_LLM_KEY_ENV)

    async def admit_build(
        self,
        owner_id: str | None,
        *,
        compute: ComputeChoice = ComputeChoice.SERVER,
        run_id: str | None = None,
    ) -> BuildAdmission:
        """Resolve the run's credentials and, for a throttled keyless build, reserve a Draft slot.

        Call this BEFORE recording or streaming a build, so a refusal is a real HTTP status rather
        than a half-open SSE stream. Raises the throttle's ``Draft*`` errors when the keyless build
        is refused; the router maps them to 403/429. A keyed build (or no throttle) reserves nothing
        — only the slow keyless runtime is rationed. Release ``reservation`` when the build's task
        ends.

        ``compute=DEVICE`` on a keyless build registers a device bridge under ``run_id`` — by the
        time the caller holds the response's ``X-Run-Id``, the tab can already poll it. A keyed
        build ignores the choice (it always runs hosted), mirroring the explain tiers.
        """
        credentials = await self._resolve_run_credentials(owner_id)
        keyless = self._is_keyless_llm(credentials)
        reservation: DraftReservation | None = None
        if self._throttle is not None and keyless:
            reservation = self._throttle.reserve(owner_id or _LOCAL_OWNER_KEY)
        bridge: DeviceBridge | None = None
        if (
            compute is ComputeChoice.DEVICE
            and keyless
            and run_id is not None
            and self._bridge_registry is not None
        ):
            bridge = DeviceBridge(run_id=run_id, limits=self._bridge_limits)
            self._bridge_registry.register(run_id, bridge, owner_id)
            logger.info("device_bridge_registered", run_id=run_id)
        return BuildAdmission(
            credentials=credentials, reservation=reservation, device_bridge=bridge
        )

    def _release(self, reservation: DraftReservation | None) -> None:
        """Free a held Draft slot (no-op when the build was keyed / unthrottled).

        A non-None reservation can only have come from this service's throttle, so the throttle is
        present whenever there's a slot to free — assert the invariant rather than no-op."""
        if reservation is None:
            return
        assert self._throttle is not None, "a Draft reservation is held but no throttle is wired"
        self._throttle.release(reservation)

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

    def _video_coordinator_for(
        self, owner_id: str | None, credentials: Mapping[str, str] | None
    ) -> IVideoBuildCoordinator | None:
        """The build's video-enqueue coordinator, or ``None`` when video generation is off for it.

        The whole V4 enqueue gate in one place (plan §V4-T0): the operator flag (the factory is
        wired only when ``VIDEO_GENERATION_ENABLED`` is on), AND the build is **keyed** (video needs
        Claude + a vision model — never a keyless Draft build), AND an **owner** is known (a
        ``video_jobs`` row needs a ``user_id``; auth-off single-user builds get no videos). The
        harness then only checks the coordinator's presence — it never re-derives this gate."""
        if self._video_coordinator_factory is None or owner_id is None:
            return None
        if self._is_keyless_llm(credentials):
            return None
        return self._video_coordinator_factory(owner_id)

    @staticmethod
    def _video_scope(
        coordinator: IVideoBuildCoordinator | None,
    ) -> AbstractContextManager[None]:
        """The run's video-build context: the coordinator when video is on for this build, else a
        no-op. Entered alongside the credential + config scopes around the factory + create_task so
        the run task inherits it (the harness reads it via ``resolve_video_coordinator``)."""
        if coordinator is None:
            return nullcontext()
        return run_video_coordinator(coordinator)

    @staticmethod
    def _bridge_scope(bridge: DeviceBridge | None) -> AbstractContextManager[None]:
        """The run's device-bridge context: routes the build's LLM calls to the learner's tab when
        a bridge was admitted, else a no-op. Entered alongside the credential + config scopes."""
        if bridge is None:
            return nullcontext()
        return run_device_bridge(bridge)

    def _close_bridge(self, run_id: str, bridge: DeviceBridge | None) -> None:
        """Remove the bridge once the run task ends, so the tab's next poll 404s (its stop signal)
        regardless of whether any client is still connected. Must run in the task's done-callback,
        not the stream generator's teardown — a client disconnect leaves the build alive.
        Idempotent, like ``RunRegistry.discard``."""
        if bridge is None or self._bridge_registry is None:
            return
        self._bridge_registry.discard(run_id)
        # Defensive: completions awaited by the run task itself have unwound with it, but any
        # parked by a child task the harness spawned must not outlive the run.
        bridge.fail_pending("the build ended")
        logger.info("device_bridge_closed", run_id=run_id)

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
        # Admit the build first (resolves the owner's BYOK keys; for a keyless Draft build, reserves
        # a slot or refuses) before any run is recorded, so a refused build leaves no history row.
        admission = await self.admit_build(owner_id)
        credentials = admission.credentials
        config = await self._resolve_run_config(owner_id)
        video_coordinator = self._video_coordinator_for(owner_id, credentials)
        await self._record_start(run_id=run_id, course_id=course_id, topic=topic, owner_id=owner_id)
        # Run the pipeline in a registered task so a separate request can cancel this build (the
        # await-full path has no SSE consumer to interrupt). The task is awaited here, so cancelling
        # it raises CancelledError at this await without cancelling the request coroutine itself.
        # The credential + config + video scopes wrap the factory + create_task so the task inherits
        # the tenant's keys + model choices + video coordinator (a context copy); the harness then
        # reads them, not the env. No bridge scope here: device compute is stream-only (admit_build
        # above gets no compute / run_id), so an await-full build always runs server-side.
        with (
            self._credential_scope(credentials),
            self._config_scope(config),
            self._video_scope(video_coordinator),
        ):
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
            # The await-full build's task has ended here (awaited above) — free its Draft slot.
            self._release(admission.reservation)
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
        admission: BuildAdmission | None = None,
    ) -> AsyncIterator[_StreamItem]:
        """Run the pipeline, yielding each progress/agent event as it happens, then the course.

        The pipeline runs in a background task feeding one shared queue (coarse ``progress`` stages
        and fine-grained ``agent`` transcript beats, interleaved in emission order); we forward each
        item as it lands and, once the run completes, drain any tail and yield the finished
        course-object.

        The build is a **durable background task** that records its own terminal status when
        ``pipeline.run()`` finishes (see ``_run_recording_status``), so a course that completes
        after the client has navigated away is still recorded COMPLETED — not left stuck RUNNING. A
        client disconnect therefore does NOT cancel the build; only an explicit Terminate
        (``cancel_run``, from a stable request that records CANCELLED) does. This generator is a
        pure viewer: it forwards events and the final course frame to a still-connected client and
        re-raises a pipeline failure (logged with ``run_id``) for the client error frame.
        """
        queue: asyncio.Queue[StreamItem] = asyncio.Queue()
        # Persists each forwarded beat to the replayable build log: buffered, flushed in best-effort
        # batches at phase boundaries (so a crash mid-build still replays up to the last boundary),
        # capped per run, and drained in the ``finally`` below. Never blocks a yield.
        recorder = RunEventRecorder(
            self._event_store, run_id=run_id, course_id=course_id, owner_id=owner_id
        )
        # Admission (resolved BYOK keys + any held Draft slot) is normally computed by the router
        # via admit_build, so a 403/429 refusal precedes the response; a direct caller passes None
        # and we admit here. A missing key is not a refusal — the adapter falls back to keyless.
        if admission is None:
            admission = await self.admit_build(owner_id)
        credentials = admission.credentials
        config = await self._resolve_run_config(owner_id)
        video_coordinator = self._video_coordinator_for(owner_id, credentials)
        await self._record_start(run_id=run_id, course_id=course_id, topic=topic, owner_id=owner_id)
        # The credential + config + video + bridge scopes wrap only the factory + create_task (no
        # yields inside), so the run task inherits the tenant's keys + model choices + video
        # coordinator + device bridge as a context copy while the generator's own context — the one
        # live across each yield — never retains them. The terminal status is recorded by the task
        # itself (_run_recording_status), disconnect-proof.
        with (
            self._credential_scope(credentials),
            self._config_scope(config),
            self._video_scope(video_coordinator),
            self._bridge_scope(admission.device_bridge),
        ):
            pipeline = self._factory(self._store_for(owner_id))
            run_task = asyncio.create_task(
                self._run_recording_status(
                    pipeline.run(
                        topic,
                        course_id=course_id,
                        run_id=run_id,
                        progress=QueueProgressSink(queue),
                        agent=QueueAgentSink(queue),
                        clarification=clarification,
                        discovery_depth=discovery_depth,
                    ),
                    course_id=course_id,
                    run_id=run_id,
                    owner_id=owner_id,
                )
            )
            self._registry.register(
                run_id, run_task, course_id, owner_id
            )  # cancellable by a separate request (scoped to the owner)
        # Free the Draft slot when the durable build task ends — NOT when this generator is torn
        # down (a client disconnect leaves the build running, so the slot tracks the task lifetime).
        if admission.reservation is not None:
            run_task.add_done_callback(lambda _: self._release(admission.reservation))
        # Same lifetime for the device bridge: the tab's next poll after the run ends must 404 (its
        # signal to stop), however the run ended.
        if admission.device_bridge is not None:
            run_task.add_done_callback(
                lambda _: self._close_bridge(run_id, admission.device_bridge)
            )
        next_event_task: asyncio.Task[StreamItem] | None = None
        try:
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
            # The run task already recorded its own terminal status; the generator only surfaces the
            # result to a still-connected client.
            if run_task.cancelled():
                return  # explicit Terminate (cancel_run recorded CANCELLED) — no course frame
            course = run_task.result()  # .result() propagates a pipeline failure here
            yield ("course", course)
        except Exception:
            logger.error("course_stream_failed", course_id=course_id, run_id=run_id, exc_info=True)
            raise
        finally:
            # Flush the buffered build-log tail (best-effort, safe to await — no ``yield`` here).
            # The build task is intentionally NOT cancelled on a client disconnect: it runs to
            # completion as a durable background job and records its own terminal status, so a
            # course finished after the client left is COMPLETED rather than stuck RUNNING. Only an
            # explicit Terminate (cancel_run) cancels it.
            await recorder.flush()
            # Cancel the pending queue.get() so the abandoned read doesn't keep the queue (and the
            # events the background build is still producing) alive after the generator is gone.
            if next_event_task is not None and not next_event_task.done():
                next_event_task.cancel()

    async def _run_recording_status(
        self, coro: Awaitable[Course], *, course_id: str, run_id: str, owner_id: str | None
    ) -> Course:
        """Run a build to completion and record its terminal status — disconnect-proof.

        The build runs as a background task that outlives any SSE consumer, so the terminal status
        is written HERE when ``pipeline.run()`` finishes (COMPLETED on success, FAILED on error),
        not by the stream generator (which may be abandoned when the client navigates away). An
        explicit Terminate cancels the task; ``cancel_run`` already records CANCELLED from its
        stable request, so a CancelledError is re-raised without overwriting it. The registry entry
        is discarded here (not in the generator) so a background build stays cancellable until it
        actually ends. History writes are best-effort (a failure never breaks the build)."""
        try:
            course = await coro
        except asyncio.CancelledError:
            # Explicit Terminate cancels via the registry, which records CANCELLED from its stable
            # request — don't overwrite it. A cancel from anywhere else (loop shutdown, a future
            # caller) isn't covered there, so record FAILED rather than leave the run stuck RUNNING.
            if not self._registry.was_cancelled(run_id):
                await self._record_failure(course_id, owner_id=owner_id)
            raise
        except Exception:
            await self._record_failure(course_id, owner_id=owner_id)
            raise
        else:
            await self._record_finish(course, owner_id=owner_id)
            return course
        finally:
            # Discard here (not in the generator) so a background build stays cancellable until it
            # actually ends; the was_cancelled read above runs first, before this clears it.
            self._registry.discard(run_id)

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
        active pipeline can't regenerate a single lesson (e.g. the deep-agent builder). Like a full
        build, the re-author runs in the owner's credential scope so it uses the tenant's own keys
        (or the keyless fallbacks when a key is unset).
        """
        if not _is_safe_course_id(course_id):
            return None  # unsafe id can't name a stored course → not-found (router → 404)
        pipeline = self._factory(self._store_for(owner_id))
        # Support check first: an unsupported pipeline is a 501 regardless of keys, and constructing
        # it above touches no key (the clients are lazy).
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
        except PersistenceError:
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
        except PersistenceError as exc:
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
        except PersistenceError as exc:
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
        except PersistenceError:
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
        except PersistenceError:
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
        except PersistenceError:
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
        except PersistenceError:
            logger.warning("run_history_mark_cancelled_error", course_id=course_id, exc_info=True)
