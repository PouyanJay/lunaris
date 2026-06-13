"""LessonVideoPipeline tests: the real orchestration (PLAN → Gate A → Gate B → ASSEMBLE) wired
from real planner/gates with stubbed leaf seams, plus the contract-hash cache that skips the whole
render half on an unchanged contract. Fakes stand in only for I/O leaves (model, renderer, vision,
frames, assembler, lesson source)."""

import json
from pathlib import Path

from _stubs import FakeLessonProvider, StubInvokeModel
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video.gates import RenderGate, VisualQaGate
from lunaris_video.models import RenderedScene, RenderedVideo, RenderResult
from lunaris_video.pipeline import ContractHashCache, LessonVideoPipeline
from lunaris_video.planning import ScenePlanner
from lunaris_video.schemas import QaVerdict, SceneContract, VideoContract

_SCENE_SOURCE = "from manim import *\nfrom style_tokens import *\n\n\nclass S1Problem(Scene):\n    def construct(self):\n        pass\n"  # noqa: E501


def _job() -> VideoJob:
    return VideoJob(
        id="job-1",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="hash-1",
    )


class _SpyRenderer:
    """Writes a fake per-scene MP4 and counts renders — the cache assertion's instrument."""

    def __init__(self) -> None:
        self.renders = 0

    async def render(self, scene_file: Path, scene_class_name: str) -> "RenderResult":
        self.renders += 1
        mp4 = scene_file.parent / f"{scene_class_name}.mp4"
        mp4.write_bytes(b"fake-mp4")
        return RenderResult(succeeded=True, mp4_path=mp4, error_tail="")


class _CleanVision:
    async def inspect(self, frames: list[bytes], scene: SceneContract) -> QaVerdict:
        return QaVerdict(passed=True)


class _FakeFrames:
    async def extract(self, mp4_path: Path) -> list[bytes]:
        return [b"f30", b"f60", b"f90"]


class _SpyAssembler:
    def __init__(self) -> None:
        self.calls = 0

    async def assemble(
        self, scenes: list[RenderedScene], contract: VideoContract, *, workdir: Path
    ) -> RenderedVideo:
        self.calls += 1
        return RenderedVideo(
            mp4=b"\x00\x00\x00\x18ftyp" + b"x" * 2000,
            poster=b"\xff\xd8\xff" + b"x" * 600,
            contracts_json=contract.model_dump_json().encode(),
            timing_json=b"{}",
        )


def _draft_json(make_lesson_contract) -> str:
    contract = make_lesson_contract().model_dump(mode="json")
    keys = ("topic", "audience", "visual_archetypes_used", "asset_strategy")
    draft = {k: contract[k] for k in keys}
    # One scene, so the spy renderer count is unambiguous.
    draft["scenes"] = [contract["scenes"][0]]
    return json.dumps(draft)


class _CodegenStub:
    """A codegen seam that always returns valid scene source (Gate A/B never need to repair)."""

    async def generate(self, scene: SceneContract, *, topic: str) -> str:
        return _SCENE_SOURCE

    async def repair(self, scene: SceneContract, *, source: str, error_tail: str) -> str:
        return _SCENE_SOURCE

    async def repair_visual(self, scene: SceneContract, *, source: str, defects) -> str:
        return _SCENE_SOURCE


def _pipeline(
    invoke: StubInvokeModel,
    renderer: _SpyRenderer,
    assembler: _SpyAssembler,
    cache: ContractHashCache,
    workspace: Path,
) -> LessonVideoPipeline:
    codegen = _CodegenStub()
    return LessonVideoPipeline(
        lesson_provider=FakeLessonProvider(),
        planner=ScenePlanner(invoke=invoke),
        render_gate=RenderGate(codegen=codegen, renderer=renderer),
        visual_qa_gate=VisualQaGate(
            vision=_CleanVision(), codegen=codegen, renderer=renderer, frames=_FakeFrames()
        ),
        assembler=assembler,
        cache=cache,
        workspace_root=workspace,
    )


async def test_produce_runs_the_pipeline_and_returns_the_assembled_video(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act
    video = await pipeline.produce(_job())

    # Assert — the real flow ran end to end: a scene rendered, the assembler bundled it, and the
    # returned artifact carries the planned contract (the planner sets the topic).
    assert renderer.renders == 1
    assert assembler.calls == 1
    assert video.mp4[4:8] == b"ftyp"
    assert b"How merge sort works" in video.contracts_json


async def test_an_unchanged_contract_hits_the_cache_and_skips_rendering(
    make_lesson_contract, tmp_path: Path
) -> None:
    # Arrange — the SAME planner output both runs (the stub repeats its reply) → same hash.
    invoke = StubInvokeModel([_draft_json(make_lesson_contract)])
    renderer, assembler, cache = _SpyRenderer(), _SpyAssembler(), ContractHashCache()
    pipeline = _pipeline(invoke, renderer, assembler, cache, tmp_path)

    # Act — produce twice.
    first = await pipeline.produce(_job())
    second = await pipeline.produce(_job())

    # Assert — second produce skipped Stage 2+: no extra render, no extra assemble, same artifact.
    assert renderer.renders == 1
    assert assembler.calls == 1
    assert second is first
