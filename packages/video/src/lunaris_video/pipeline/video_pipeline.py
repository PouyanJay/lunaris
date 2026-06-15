from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import structlog
from lunaris_runtime.schema import (
    DegradedScene,
    RegenerateMode,
    VideoJob,
    VideoJobStatus,
    VideoProvenance,
)
from lunaris_runtime.video_build import target_seconds_for

from lunaris_video.assembly import estimate_timing
from lunaris_video.errors import SyncGateError, VideoPipelineError
from lunaris_video.gates import FactualGate, RenderGate, SyncGate, VisualQaGate
from lunaris_video.hashing import contract_hash
from lunaris_video.models import RenderedVideo, SceneQaResult
from lunaris_video.models.lesson_source import LessonSource
from lunaris_video.planning import ScenePlanner
from lunaris_video.protocols.lesson_source_provider_protocol import ILessonSourceProvider
from lunaris_video.protocols.prior_contract_provider_protocol import IPriorContractProvider
from lunaris_video.protocols.render_cache_protocol import IRenderCache
from lunaris_video.protocols.speech_synthesizer_protocol import ISpeechSynthesizer
from lunaris_video.protocols.video_assembler_protocol import IVideoAssembler
from lunaris_video.protocols.video_pipeline_protocol import StageReporter
from lunaris_video.schemas import (
    FRAMING_ONLY_SENTINEL,
    TimingManifest,
    VideoContract,
    VoiceSpec,
)
from lunaris_video.sourcing import NullPriorContractProvider

_logger = structlog.get_logger(__name__)

# ElevenLabs "Rachel" + the high-quality multilingual model — the default course voice when the job
# config doesn't name one (one voice per course; §0). A future per-user config (V6) overrides these.
_ELEVENLABS_PROVIDER = "elevenlabs"
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
_DEFAULT_VOICE_MODEL = "eleven_multilingual_v2"

# The owner-safe, actionable reason shown when a narrated video can't be synced even after the
# plainer retry — never a raw vision critique. The two actions a user actually has: regenerate, or
# drop narration for a silent (sync-exempt) version.
_SYNC_FAILED_DETAIL = (
    "We couldn't line the narration up with the visuals, even after a simpler retry. "
    "Try regenerating, or turn off narration in Settings for a silent version."
)

# A synthesizer provider is a thunk: it resolves the tenant's ElevenLabs key (the contextvar seam)
# at produce time and returns a synthesizer, or None when no key is available. Resolving per produce
# (not at construction) is what lets a per-job tenant credential scope be picked up later (V4/V7).
SynthesizerProvider = Callable[[], ISpeechSynthesizer | None]


def _no_synthesizer() -> ISpeechSynthesizer | None:
    """The default provider: no synthesizer, so any voice-on job fails fast (no key configured)."""
    return None


async def _no_stage(_: VideoJobStatus) -> None:
    """No-op stage reporter: a producer whose caller doesn't track progress reports nowhere."""
    return None


class VideoPipeline:
    """The real video pipeline (``IVideoPipeline``): a source → contract → scenes → one MP4.

    PLAN once, then Gate C (factual: every narrated figure must be grounded in a cited claim —
    runs on the contract before any render so a smuggled figure costs no compute), then resolve the
    timing manifest (silent = WPM estimate; voiced = measured ElevenLabs synthesis), then per scene:
    Gate A (render + stack-trace repair) → Gate B (vision QA + targeted repair), then ASSEMBLE
    (concat + poster + timing, plus mux + captions when voiced), then Gate D (sync, voiced only).
    The contract hash gates the whole render half (skip Stage 2+ on a cache hit). **Silent and
    narrated render from the SAME contract — the plan is computed once; only the manifest, the mux
    and the captions differ — so the voice toggle never re-plans.** Any scene that cannot be
    grounded, rendered, synced or pass QA raises a ``VideoPipelineError`` subclass; the worker
    settles the job FAILED with the evidence and a partial video is never returned.

    One class serves all three kinds (V5): the injected ``source_provider`` decides what it grounds
    against (a lesson from the store, or a course-level grounding snapshot), and ``chaptered`` picks
    the flat plan (lesson/summary) vs the chaptered plan (the ~3-min overview). Everything below
    — gates, render, assemble — works on the ``VideoContract`` union, so the kind never leaks past
    PLAN. ``KindRoutingVideoPipeline`` maps each ``VideoKind`` to its configured instance.
    """

    def __init__(
        self,
        *,
        source_provider: ILessonSourceProvider,
        planner: ScenePlanner,
        factual_gate: FactualGate,
        render_gate: RenderGate,
        visual_qa_gate: VisualQaGate,
        assembler: IVideoAssembler,
        cache: IRenderCache,
        workspace_root: Path,
        model_id: str,
        chaptered: bool = False,
        synthesizer_provider: SynthesizerProvider = _no_synthesizer,
        sync_gate: SyncGate | None = None,
        prior_contract_provider: IPriorContractProvider | None = None,
    ) -> None:
        self._source_provider = source_provider
        self._planner = planner
        self._factual_gate = factual_gate
        self._render_gate = render_gate
        self._visual_qa_gate = visual_qa_gate
        self._assembler = assembler
        self._cache = cache
        self._workspace_root = workspace_root
        self._model_id = model_id
        # Reuses a prior contract for a RETRY / ADD_NARRATION regenerate (V6-T2); the default never
        # reuses, so a bare pipeline always plans fresh.
        self._prior_contract_provider = prior_contract_provider or NullPriorContractProvider()
        # Chaptered = the overview kind (a ~3-min topic intro), planned as chapters that concatenate
        # into one MP4; flat = a single-arc lesson/summary. A config property, not a per-job branch.
        self._chaptered = chaptered
        # The voice seams. The defaults make a bare pipeline silent-only; the composition root wires
        # both together for the keyed path, so a voiced produce always has a synthesizer + Gate D.
        self._synthesizer_provider = synthesizer_provider
        self._sync_gate = sync_gate

    async def produce(
        self, job: VideoJob, *, on_stage: StageReporter | None = None
    ) -> RenderedVideo:
        report = on_stage or _no_stage
        source = await self._source_provider.load(job)
        try:
            return await self._produce_once(job, source, report, force_simplify=False)
        except SyncGateError as exc:
            # Shipping a voiced video whose words describe what isn't on screen is worse than an
            # honest failure, so a Gate D desync is never degraded. Retry ONCE with plainer scenes
            # (far easier to sync); a second miss fails clean. The store runs only after Gate D
            # passes, so the first attempt left no cached artifact — the retry is clean.
            _logger.warning(
                "video_pipeline.sync_retry_simpler",
                job_id=job.id,
                beat_id=exc.beat_id,
                reason=exc.reason,
            )
            try:
                return await self._produce_once(job, source, report, force_simplify=True)
            except SyncGateError as retry_exc:
                raise SyncGateError(
                    retry_exc.beat_id, reason=retry_exc.reason, user_detail=_SYNC_FAILED_DETAIL
                ) from retry_exc

    async def _produce_once(
        self, job: VideoJob, source: LessonSource, report: StageReporter, *, force_simplify: bool
    ) -> RenderedVideo:
        """One full pass: plan → gates → render → assemble → (Gate D). Raises ``SyncGateError`` if
        the narrated video desyncs, which ``produce`` catches to retry plainer. ``force_simplify``
        re-plans with the simplify directive (the Gate-D retry), ignoring any reuse mode."""
        contract = await self._resolve_contract(job, source, force_simplify=force_simplify)
        self._factual_gate.check(contract, source.packet)
        digest = contract_hash(contract)

        # The voice toggle decides voiced vs silent WITHOUT re-planning — the contract above feeds
        # both paths — and the cache key the artifact lives under (silent and voiced are distinct).
        voice, synthesizer, cache_key = self._resolve_voice(job, digest)

        cached = await self._cache.fetch(cache_key)
        if cached is not None:
            # Provenance is restamped per produce (THIS job's id/timestamp), but the degrade record
            # rides on the cached bundle — a cache hit reuses the same render, so the same scenes
            # are degraded (provenance stays honest without re-rendering to recompute it).
            _logger.info("video_pipeline.cache_hit", job_id=job.id, contract_hash=digest)
            return self._stamp_provenance(cached, job, contract, digest)

        workdir = self._workdir_for(job)
        # Audio-drives-video: resolve the timing manifest BEFORE the render so the scene code is
        # built against the exact per-beat windows — the WPM estimate (silent) or measured TTS
        # (voiced). The render half is identical either way. A voiced job synthesizes narration here
        # (minutes of TTS), so it reports VOICING before; a silent job's WPM estimate is instant.
        if voice is not None:
            await report(VideoJobStatus.VOICING)
        manifest, audio_dir = await self._resolve_timing(contract, voice, synthesizer, workdir)
        await report(VideoJobStatus.RENDERING)
        # Gate D (sync) runs per scene in the render loop when voiced: each spoken beat's midpoint
        # frame must show what its narration says, or a targeted repair re-renders that scene. The
        # frame's VISUAL is identical pre/post mux, so checking the per-scene render before assembly
        # lets the repair loop re-render one scene, not re-assemble the whole video. A desync that
        # survives the repair budget raises ``SyncGateError``, which ``produce`` recovers by
        # delivering silent. _resolve_voice guarantees the gate is present whenever voice is, so a
        # voiced render passes it down; a silent render passes None and skips Gate D entirely.
        sync_gate = self._sync_gate if voice is not None else None
        qa_results = await self._render_scenes(contract, manifest, workdir, sync_gate=sync_gate)
        await report(VideoJobStatus.ASSEMBLING)
        rendered = [result.scene for result in qa_results]
        video = await self._assembler.assemble(
            rendered, contract, manifest=manifest, workdir=workdir, audio_dir=audio_dir
        )
        # Record any best-effort (degraded) scenes ON the bundle so the degrade survives the cache.
        video = replace(video, degraded_scenes=_degraded_scenes(qa_results))
        await self._cache.store(cache_key, video)
        _logger.info(
            "video_pipeline.produced",
            job_id=job.id,
            scenes=len(rendered),
            narrated=voice is not None,
            grounded_claim_ids=len(_cited_claim_ids(contract)),
            degraded_scenes=len(video.degraded_scenes),
        )
        return self._stamp_provenance(video, job, contract, digest)

    async def _resolve_contract(
        self, job: VideoJob, source: LessonSource, *, force_simplify: bool = False
    ) -> VideoContract:
        """The contract this produce renders — the regenerate menu's four entry points (V6-T2).

        ``RETRY`` / ``ADD_NARRATION`` re-render the prior job's planned contract (reused from
        storage) without re-planning — Stage 2+ only; ``ADD_NARRATION`` differs only in that the
        job's voice toggle is on. ``SIMPLER`` re-plans with the simplify directive; ``FRESH`` (or no
        regenerate) plans normally. A reuse mode whose prior contract is missing falls back to a
        fresh plan rather than failing the regenerate.

        ``force_simplify`` (the Gate-D sync retry) overrides all of that: re-plan the plainest
        scenes regardless of mode — the reused/normal contract just desynced, so reusing it would
        desync again.
        """
        mode = _regenerate_mode(job)
        if not force_simplify and mode is not None and mode.reuses_contract:
            prior = await self._prior_contract_provider.load(job)
            if prior is not None:
                _logger.info("video_pipeline.contract_reused", job_id=job.id, mode=mode.value)
                return prior
            _logger.info("video_pipeline.no_prior_contract", job_id=job.id, mode=mode.value)
        simplify = force_simplify or mode is RegenerateMode.SIMPLER
        return await self._plan(source, _target_seconds(job), simplify=simplify)

    async def _plan(
        self, source: LessonSource, target_seconds: int, *, simplify: bool
    ) -> VideoContract:
        """PLAN the contract for this pipeline's kind: chaptered for the overview, flat otherwise.
        Both share the grounding moat (the packet on ``source``) and the injected style/gates;
        ``simplify`` (the V6 Simpler regenerate) steers PLAN toward fewer, plainer scenes."""
        if self._chaptered:
            return await self._planner.plan_chaptered(
                source, target_seconds=target_seconds, simplify=simplify
            )
        return await self._planner.plan(source, target_seconds=target_seconds, simplify=simplify)

    def _resolve_voice(
        self, job: VideoJob, digest: str
    ) -> tuple[VoiceSpec | None, ISpeechSynthesizer | None, str]:
        """Decide voiced vs silent for this job and the cache key its artifact lives under, without
        re-planning. Silent gives (None, None, digest).

        The voice toggle (V6) defaults ON, but an ElevenLabs key is OPTIONAL BYOK — so "voice on +
        no key" is the common keyed-user state and must **degrade to silent (voice-ready)** per §0,
        never fail: a build of a keyed user who never added an ElevenLabs key would otherwise FAIL
        every video. A voiced render still needs the sync gate (Gate D) — a pipeline wired for voice
        but missing it is a wiring bug, not a user state, so that stays a hard error."""
        if not _wants_voice(job):
            return None, None, digest
        synthesizer = self._synthesizer_provider()
        if synthesizer is None:
            # Voice asked for but no validated key resolvable here → render silent voice-ready (the
            # WPM estimate manifest), exactly as if the toggle were off. The user can add narration
            # later (the V6 regenerate menu) with no re-plan.
            _logger.info("video_pipeline.voice_degraded_to_silent", job_id=job.id)
            return None, None, digest
        if self._sync_gate is None:
            raise VideoPipelineError(
                f"job {job.id} requested narration but the pipeline has no sync gate (Gate D)"
            )
        voice = _voice_spec(job)
        # Distinct voice or model = distinct audio, so each caches separately under the contract.
        return voice, synthesizer, f"{digest}:{voice.voice_id}:{voice.model}"

    async def _resolve_timing(
        self,
        contract: VideoContract,
        voice: VoiceSpec | None,
        synthesizer: ISpeechSynthesizer | None,
        workdir: Path,
    ) -> tuple[TimingManifest, Path | None]:
        """The manifest the render is built against, and the clip directory to mux from. Silent
        gives the WPM estimate + no audio; voiced gives measured TTS (one voice/course) + clips."""
        if voice is None or synthesizer is None:
            return estimate_timing(contract), None
        audio_dir = workdir / "audio"
        manifest = await synthesizer.synthesize(contract, voice=voice, audio_dir=audio_dir)
        return manifest, audio_dir

    def _stamp_provenance(
        self, video: RenderedVideo, job: VideoJob, contract: VideoContract, digest: str
    ) -> RenderedVideo:
        """Stamp the requesting job's provenance onto the artifact (fresh render or cache hit).

        Built at the source and per produce, so even a cache hit carries THIS job's id/timestamp,
        not the job that first rendered the contract. ``degraded_scenes`` comes off the bundle (set
        at render, preserved through the cache) so a degraded scene's record is never dropped.
        """
        provenance = VideoProvenance(
            job_id=job.id,
            course_id=job.course_id,
            lesson_id=job.lesson_id,
            kind=job.kind,
            model=self._model_id,
            contract_hash=digest,
            input_hash=job.input_hash,
            claim_ids=_cited_claim_ids(contract),
            generated_at=datetime.now(UTC).isoformat(),
            degraded_scenes=list(video.degraded_scenes),
        )
        return replace(video, provenance_json=provenance.model_dump_json(by_alias=True).encode())

    async def _render_scenes(
        self,
        contract: VideoContract,
        manifest: TimingManifest,
        workdir: Path,
        *,
        sync_gate: SyncGate | None,
    ) -> list[SceneQaResult]:
        results: list[SceneQaResult] = []
        for scene in contract.scenes:
            timing = manifest[scene.id]
            passed_render = await self._render_gate.render_scene(
                scene, topic=contract.topic, timing=timing, workdir=workdir
            )
            qa = await self._visual_qa_gate.inspect_scene(
                scene, rendered=passed_render, timing=timing, workdir=workdir
            )
            scene_render = qa.scene
            if sync_gate is not None:
                # Gate D may re-render this scene to fix a desync; any Gate-B degrade record is
                # preserved — it describes a spatial defect the timing repair does not touch.
                scene_render = await sync_gate.inspect_scene(
                    scene, rendered=qa.scene, timing=timing, workdir=workdir
                )
            results.append(
                SceneQaResult(scene=scene_render, unresolved_defects=qa.unresolved_defects)
            )
        return results

    def _workdir_for(self, job: VideoJob) -> Path:
        workdir = self._workspace_root / job.id
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir


def _target_seconds(job: VideoJob) -> int:
    # The length snapshotted onto the job at enqueue (V5-T2) wins; absent, fall back to the kind's
    # product default — so PLAN always designs to a length, kind-aware, with no duplicated constant.
    raw = job.config.get("target_seconds")
    return int(raw) if isinstance(raw, int) else target_seconds_for(job.kind)


def _regenerate_mode(job: VideoJob) -> RegenerateMode | None:
    # The regenerate mode the endpoint stamped on the job (V6-T2), or None for an ordinary build.
    # A value the enum doesn't know is treated as no regenerate (fresh plan) rather than a failure.
    regenerate = job.config.get("regenerate")
    if not isinstance(regenerate, dict):
        return None
    raw = regenerate.get("mode")
    try:
        return RegenerateMode(raw)
    except ValueError:
        return None


def _wants_voice(job: VideoJob) -> bool:
    # The voice toggle, snapshotted onto the job config at enqueue (V4). Absent/false ⇒ silent.
    return bool(job.config.get("voice"))


def _voice_spec(job: VideoJob) -> VoiceSpec:
    config = job.config
    return VoiceSpec(
        provider=_ELEVENLABS_PROVIDER,
        voice_id=str(config.get("voice_id") or _DEFAULT_VOICE_ID),
        model=str(config.get("voice_model") or _DEFAULT_VOICE_MODEL),
    )


def _degraded_scenes(results: list[SceneQaResult]) -> tuple[DegradedScene, ...]:
    # The provenance record of every scene Gate B shipped as best-effort (the 'publish anyway'
    # degrade) — a scene that passed QA cleanly contributes none. Ordered by render order.
    return tuple(
        DegradedScene(
            scene_id=result.scene.scene_id,
            issues=[defect.issue for defect in result.unresolved_defects],
        )
        for result in results
        if result.unresolved_defects
    )


def _cited_claim_ids(contract: VideoContract) -> list[str]:
    # Framing-only scenes assert no empirical fact, so they contribute no grounded claim id — only
    # the ids real scenes cite become the video's provenance.
    cited = {
        source
        for scene in contract.scenes
        for source in scene.sources
        if source != FRAMING_ONLY_SENTINEL
    }
    return sorted(cited)
