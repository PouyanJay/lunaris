from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import structlog
from lunaris_runtime.schema import VideoJob, VideoProvenance

from lunaris_video.assembly import estimate_timing
from lunaris_video.gates import FactualGate, RenderGate, VisualQaGate
from lunaris_video.hashing import contract_hash
from lunaris_video.models import RenderedScene, RenderedVideo
from lunaris_video.planning import ScenePlanner
from lunaris_video.protocols.lesson_source_provider_protocol import ILessonSourceProvider
from lunaris_video.protocols.render_cache_protocol import IRenderCache
from lunaris_video.protocols.video_assembler_protocol import IVideoAssembler
from lunaris_video.schemas import (
    FRAMING_ONLY_SENTINEL,
    SceneContracts,
    TimingManifest,
    VideoContract,
)

_logger = structlog.get_logger(__name__)

_DEFAULT_TARGET_SECONDS = 75


class LessonVideoPipeline:
    """The real lesson-video pipeline (``IVideoPipeline``): lesson → contract → scenes → MP4.

    PLAN once, then Gate C (factual: every narrated figure must be grounded in a cited claim —
    runs on the contract before any render so a smuggled figure costs no compute), then per scene:
    Gate A (render + stack-trace repair) → Gate B (vision QA + targeted repair), then ASSEMBLE
    (concat + poster + timing). The contract hash gates the whole render half: an unchanged contract
    with cached artifacts returns immediately (skip Stage 2+). Any scene that cannot be grounded,
    rendered or pass QA raises (a ``VideoPipelineError`` subclass) — the worker settles the job
    FAILED with the evidence; a partial video is never returned.

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

    async def produce(self, job: VideoJob) -> RenderedVideo:
        lesson = await self._lesson_provider.load(job)
        contract = await self._planner.plan(lesson, target_seconds=_target_seconds(job))
        self._factual_gate.check(contract, lesson.packet)
        digest = contract_hash(contract)

        # Provenance is built at the source and stamped fresh per produce — even on a cache hit it
        # must carry THIS job's id/timestamp, not the job that first rendered the contract.
        provenance = self._provenance_bytes(job, contract, digest)

        cached = await self._cache.fetch(digest)
        if cached is not None:
            _logger.info("video_pipeline.cache_hit", job_id=job.id, contract_hash=digest)
            return replace(cached, provenance_json=provenance)

        workdir = self._workdir_for(job)
        # Audio-drives-video: resolve the timing manifest BEFORE the render so the scene code is
        # built against the exact per-beat windows. V3 silent path = the WPM estimate; the voiced
        # path swaps a measured manifest in here (V3-T5) — the render half is identical either way.
        manifest = estimate_timing(contract)
        rendered = await self._render_scenes(contract, manifest, workdir)
        video = await self._assembler.assemble(
            rendered, contract, manifest=manifest, workdir=workdir
        )
        await self._cache.store(digest, video)
        _logger.info(
            "video_pipeline.produced",
            job_id=job.id,
            scenes=len(rendered),
            grounded_claim_ids=len(_cited_claim_ids(contract)),
        )
        return replace(video, provenance_json=provenance)

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
    raw = job.config.get("target_seconds")
    return int(raw) if isinstance(raw, int) else _DEFAULT_TARGET_SECONDS


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
