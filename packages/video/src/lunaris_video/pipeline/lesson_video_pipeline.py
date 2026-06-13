from pathlib import Path

import structlog
from lunaris_runtime.schema import VideoJob

from lunaris_video.gates import RenderGate, VisualQaGate
from lunaris_video.hashing import contract_hash
from lunaris_video.models import RenderedScene, RenderedVideo
from lunaris_video.planning import ScenePlanner
from lunaris_video.protocols.lesson_source_provider_protocol import ILessonSourceProvider
from lunaris_video.protocols.render_cache_protocol import IRenderCache
from lunaris_video.protocols.video_assembler_protocol import IVideoAssembler
from lunaris_video.schemas import SceneContracts

_logger = structlog.get_logger(__name__)

_DEFAULT_TARGET_SECONDS = 75


class LessonVideoPipeline:
    """The real lesson-video pipeline (``IVideoPipeline``): lesson → contract → scenes → MP4.

    PLAN once, then per scene: Gate A (render + stack-trace repair) → Gate B (vision QA + targeted
    repair), then ASSEMBLE (concat + poster + timing). The contract hash gates the whole render
    half: an unchanged contract with cached artifacts returns immediately (skip Stage 2+). Any
    scene that cannot be made to render or pass QA raises (a ``VideoPipelineError`` subclass) — the
    worker settles the job FAILED with the evidence; a partial video is never returned.

    V1 plans lesson videos only (flat ``SceneContracts``); the chaptered overview kind arrives in
    V5 behind the same interface.
    """

    def __init__(
        self,
        *,
        lesson_provider: ILessonSourceProvider,
        planner: ScenePlanner,
        render_gate: RenderGate,
        visual_qa_gate: VisualQaGate,
        assembler: IVideoAssembler,
        cache: IRenderCache,
        workspace_root: Path,
    ) -> None:
        self._lesson_provider = lesson_provider
        self._planner = planner
        self._render_gate = render_gate
        self._visual_qa_gate = visual_qa_gate
        self._assembler = assembler
        self._cache = cache
        self._workspace_root = workspace_root

    async def produce(self, job: VideoJob) -> RenderedVideo:
        lesson = await self._lesson_provider.load(job)
        contract = await self._planner.plan(lesson, target_seconds=_target_seconds(job))
        digest = contract_hash(contract)

        cached = await self._cache.fetch(digest)
        if cached is not None:
            _logger.info("video_pipeline.cache_hit", job_id=job.id, contract_hash=digest)
            return cached

        workdir = self._workdir_for(job)
        rendered = await self._render_scenes(contract, workdir)
        video = await self._assembler.assemble(rendered, contract, workdir=workdir)
        await self._cache.store(digest, video)
        _logger.info("video_pipeline.produced", job_id=job.id, scenes=len(rendered))
        return video

    async def _render_scenes(self, contract: SceneContracts, workdir: Path) -> list[RenderedScene]:
        rendered: list[RenderedScene] = []
        for scene in contract.scenes:
            passed_render = await self._render_gate.render_scene(
                scene, topic=contract.topic, workdir=workdir
            )
            cleared = await self._visual_qa_gate.inspect_scene(
                scene, rendered=passed_render, workdir=workdir
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
