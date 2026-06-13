"""Full-pipeline real-render smoke (acceptance #1, minus the LLM): a lesson runs through the REAL
LessonVideoPipeline — real Manim renders, real ffmpeg frame extraction + concat — and produces a
real ≥3-scene MP4. Only the model seams are stubbed (the LLM authoring is the T5 live eval).
Self-skips where the render extra is absent."""

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from _stubs import FakeLessonProvider, StubInvokeModel
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video.assembly import VideoAssembler
from lunaris_video.gates import RenderGate, VisualQaGate
from lunaris_video.pipeline import ContractHashCache, LessonVideoPipeline
from lunaris_video.planning import ScenePlanner
from lunaris_video.qa import VisionQaInspector
from lunaris_video.rendering import FrameExtractor, SceneRenderer
from lunaris_video.schemas import SceneContract, SceneContracts

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)


class _SceneFromContractCodegen:
    """Emits a trivial but valid Manim scene whose class matches the contract — stands in for the
    LLM so the REAL renderer/assembler path is exercised end to end."""

    async def generate(self, scene: SceneContract, *, topic: str) -> str:
        return (
            "from manim import *\n"
            "from style_tokens import *\n\n\n"
            f"class {scene.scene_class_name}(Scene):\n"
            "    def construct(self):\n"
            f'        t = Text("{scene.id}", font_size=28, color=INK, font=FONT)\n'
            "        self.add(t)\n"
            "        self.wait(0.3)\n"
            "        self.play(FadeOut(t), run_time=0.2)\n"
        )

    async def repair(self, scene: SceneContract, *, source: str, error_tail: str) -> str:
        return await self.generate(scene, topic="")

    async def repair_visual(self, scene: SceneContract, *, source: str, defects) -> str:
        return await self.generate(scene, topic="")


class _PassingVision:
    async def __call__(self, prompt: str, frames: list[bytes]) -> str:
        return json.dumps({"passed": True, "defects": []})


def _three_scene_draft(make_lesson_contract: Callable[..., SceneContracts]) -> str:
    contract = make_lesson_contract().model_dump(mode="json")
    keys = ("topic", "audience", "visual_archetypes_used", "asset_strategy", "scenes")
    return json.dumps({k: contract[k] for k in keys})


def _job() -> VideoJob:
    return VideoJob(
        id="smoke-job",
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="h",
    )


async def test_a_lesson_renders_a_multi_scene_mp4(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange — the fixture contract has three scenes; only the model seams are stubbed.
    codegen = _SceneFromContractCodegen()
    renderer = SceneRenderer(timeout_s=180)
    pipeline = LessonVideoPipeline(
        lesson_provider=FakeLessonProvider(),
        planner=ScenePlanner(invoke=StubInvokeModel([_three_scene_draft(make_lesson_contract)])),
        render_gate=RenderGate(codegen=codegen, renderer=renderer),
        visual_qa_gate=VisualQaGate(
            vision=VisionQaInspector(invoke=_PassingVision()),
            codegen=codegen,
            renderer=renderer,
            frames=FrameExtractor(),
        ),
        assembler=VideoAssembler(),
        cache=ContractHashCache(),
        workspace_root=tmp_path,
    )

    # Act
    video = await pipeline.produce(_job())

    # Assert — a real concatenated MP4 from ≥3 scenes, a real poster, and a 3-scene timing manifest.
    assert video.mp4[4:8] == b"ftyp"
    assert video.poster[:3] == b"\xff\xd8\xff"
    timing = json.loads(video.timing_json)
    assert len(timing) == 3
    contracts = json.loads(video.contracts_json)
    assert len(contracts["scenes"]) == 3
