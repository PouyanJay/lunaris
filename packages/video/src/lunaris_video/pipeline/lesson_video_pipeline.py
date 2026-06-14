from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import structlog
from lunaris_runtime.schema import VideoJob, VideoProvenance
from lunaris_runtime.video_build import target_seconds_for

from lunaris_video.assembly import NARRATED_VIDEO_NAME, estimate_timing
from lunaris_video.errors import VideoPipelineError, VoiceUnavailableError
from lunaris_video.gates import FactualGate, RenderGate, SyncGate, VisualQaGate
from lunaris_video.hashing import contract_hash
from lunaris_video.models import RenderedScene, RenderedVideo
from lunaris_video.planning import ScenePlanner
from lunaris_video.protocols.lesson_source_provider_protocol import ILessonSourceProvider
from lunaris_video.protocols.render_cache_protocol import IRenderCache
from lunaris_video.protocols.speech_synthesizer_protocol import ISpeechSynthesizer
from lunaris_video.protocols.video_assembler_protocol import IVideoAssembler
from lunaris_video.schemas import (
    FRAMING_ONLY_SENTINEL,
    SceneContracts,
    TimingManifest,
    VideoContract,
    VoiceSpec,
)

_logger = structlog.get_logger(__name__)

# ElevenLabs "Rachel" + the high-quality multilingual model — the default course voice when the job
# config doesn't name one (one voice per course; §0). A future per-user config (V6) overrides these.
_ELEVENLABS_PROVIDER = "elevenlabs"
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
_DEFAULT_VOICE_MODEL = "eleven_multilingual_v2"

# A synthesizer provider is a thunk: it resolves the tenant's ElevenLabs key (the contextvar seam)
# at produce time and returns a synthesizer, or None when no key is available. Resolving per produce
# (not at construction) is what lets a per-job tenant credential scope be picked up later (V4/V7).
SynthesizerProvider = Callable[[], ISpeechSynthesizer | None]


def _no_synthesizer() -> ISpeechSynthesizer | None:
    """The default provider: no synthesizer, so any voice-on job fails fast (no key configured)."""
    return None


class LessonVideoPipeline:
    """The real lesson-video pipeline (``IVideoPipeline``): lesson → contract → scenes → MP4.

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

    V1 plans lesson videos only (flat ``SceneContracts``); the chaptered overview kind arrives in
    V5 behind the same interface.
    """

    def __init__(
        self,
        *,
        lesson_provider: ILessonSourceProvider,
        planner: ScenePlanner,
        factual_gate: FactualGate,
        render_gate: RenderGate,
        visual_qa_gate: VisualQaGate,
        assembler: IVideoAssembler,
        cache: IRenderCache,
        workspace_root: Path,
        model_id: str,
        synthesizer_provider: SynthesizerProvider = _no_synthesizer,
        sync_gate: SyncGate | None = None,
    ) -> None:
        self._lesson_provider = lesson_provider
        self._planner = planner
        self._factual_gate = factual_gate
        self._render_gate = render_gate
        self._visual_qa_gate = visual_qa_gate
        self._assembler = assembler
        self._cache = cache
        self._workspace_root = workspace_root
        self._model_id = model_id
        # The voice seams. The defaults make a bare pipeline silent-only; the composition root wires
        # both together for the keyed path, so a voiced produce always has a synthesizer + Gate D.
        self._synthesizer_provider = synthesizer_provider
        self._sync_gate = sync_gate

    async def produce(self, job: VideoJob) -> RenderedVideo:
        lesson = await self._lesson_provider.load(job)
        contract = await self._planner.plan(lesson, target_seconds=_target_seconds(job))
        self._factual_gate.check(contract, lesson.packet)
        digest = contract_hash(contract)

        # The voice toggle decides voiced vs silent WITHOUT re-planning — the contract above feeds
        # both paths — and the cache key the artifact lives under (silent and voiced are distinct).
        voice, synthesizer, cache_key = self._resolve_voice(job, digest)

        # Provenance is built at the source and stamped fresh per produce — even on a cache hit it
        # must carry THIS job's id/timestamp, not the job that first rendered the contract.
        provenance = self._provenance_bytes(job, contract, digest)

        cached = await self._cache.fetch(cache_key)
        if cached is not None:
            _logger.info("video_pipeline.cache_hit", job_id=job.id, contract_hash=digest)
            return replace(cached, provenance_json=provenance)

        workdir = self._workdir_for(job)
        # Audio-drives-video: resolve the timing manifest BEFORE the render so the scene code is
        # built against the exact per-beat windows — the WPM estimate (silent) or measured TTS
        # (voiced). The render half is identical either way.
        manifest, audio_dir = await self._resolve_timing(contract, voice, synthesizer, workdir)
        rendered = await self._render_scenes(contract, manifest, workdir)
        video = await self._assembler.assemble(
            rendered, contract, manifest=manifest, workdir=workdir, audio_dir=audio_dir
        )
        if voice is not None:
            # Gate D runs on the muxed video, narrated-only: each spoken beat's midpoint frame must
            # show what the narration says, or the job fails clean. _resolve_voice guarantees the
            # gate is present whenever voice is — a narrated video is never shipped unverified.
            assert self._sync_gate is not None
            await self._sync_gate.check(workdir / NARRATED_VIDEO_NAME, contract, manifest)
        await self._cache.store(cache_key, video)
        _logger.info(
            "video_pipeline.produced",
            job_id=job.id,
            scenes=len(rendered),
            narrated=voice is not None,
            grounded_claim_ids=len(_cited_claim_ids(contract)),
        )
        return replace(video, provenance_json=provenance)

    def _resolve_voice(
        self, job: VideoJob, digest: str
    ) -> tuple[VoiceSpec | None, ISpeechSynthesizer | None, str]:
        """Decide voiced vs silent for this job and the cache key its artifact lives under, without
        re-planning. Silent gives (None, None, digest). Voiced needs a synthesizer (a validated key)
        AND a sync gate (Gate D), or it fails fast: voice on without a key, or a pipeline wired for
        voice but missing Gate D, must not silently ship an unasked-for or unverified video."""
        if not _wants_voice(job):
            return None, None, digest
        synthesizer = self._synthesizer_provider()
        if synthesizer is None:
            raise VoiceUnavailableError(job.id)
        if self._sync_gate is None:
            raise VideoPipelineError(
                f"job {job.id} requested narration but the pipeline has no sync gate (Gate D)"
            )
        voice = _voice_spec(job)
        # Distinct voice or model = distinct audio, so each caches separately under the contract.
        return voice, synthesizer, f"{digest}:{voice.voice_id}:{voice.model}"

    async def _resolve_timing(
        self,
        contract: SceneContracts,
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

    def _provenance_bytes(self, job: VideoJob, contract: VideoContract, digest: str) -> bytes:
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
        )
        return provenance.model_dump_json(by_alias=True).encode()

    async def _render_scenes(
        self, contract: SceneContracts, manifest: TimingManifest, workdir: Path
    ) -> list[RenderedScene]:
        rendered: list[RenderedScene] = []
        for scene in contract.scenes:
            timing = manifest[scene.id]
            passed_render = await self._render_gate.render_scene(
                scene, topic=contract.topic, timing=timing, workdir=workdir
            )
            cleared = await self._visual_qa_gate.inspect_scene(
                scene, rendered=passed_render, timing=timing, workdir=workdir
            )
            rendered.append(cleared)
        return rendered

    def _workdir_for(self, job: VideoJob) -> Path:
        workdir = self._workspace_root / job.id
        workdir.mkdir(parents=True, exist_ok=True)
        return workdir


def _target_seconds(job: VideoJob) -> int:
    # The length snapshotted onto the job at enqueue (V5-T2) wins; absent, fall back to the kind's
    # product default — so PLAN always designs to a length, kind-aware, with no duplicated constant.
    raw = job.config.get("target_seconds")
    return int(raw) if isinstance(raw, int) else target_seconds_for(job.kind)


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
