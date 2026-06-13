from pathlib import Path

from lunaris_runtime.persistence import ICourseStore

from lunaris_video.assembly import VideoAssembler
from lunaris_video.codegen import SceneCodeGenerator
from lunaris_video.gates import FactualGate, RenderGate, VisualQaGate
from lunaris_video.grounding import LessonGroundingPacketBuilder
from lunaris_video.pipeline.contract_hash_cache import ContractHashCache
from lunaris_video.pipeline.lesson_video_pipeline import LessonVideoPipeline
from lunaris_video.pipeline.model_adapters import (
    build_text_invoke,
    build_vision_invoke,
    default_video_model,
)
from lunaris_video.planning import ScenePlanner
from lunaris_video.qa import VisionQaInspector
from lunaris_video.rendering import FrameExtractor, SceneRenderer
from lunaris_video.sourcing import CourseStoreLessonSourceProvider


def build_lesson_video_pipeline(
    *, store: ICourseStore, workspace_root: Path, model_id: str | None = None
) -> LessonVideoPipeline:
    """Wire the real lesson-video pipeline — the composition root's one call to swap in V1.

    One ``SceneCodeGenerator``/``SceneRenderer`` is shared by Gate A and Gate B (Gate B's repairs
    re-render with the same toolchain). The model is the build's strong, vision-capable tier.
    """
    model = model_id or default_video_model()
    text_invoke = build_text_invoke(model)
    codegen = SceneCodeGenerator(invoke=text_invoke)
    renderer = SceneRenderer()
    return LessonVideoPipeline(
        lesson_provider=CourseStoreLessonSourceProvider(
            store, packet_builder=LessonGroundingPacketBuilder()
        ),
        planner=ScenePlanner(invoke=text_invoke),
        factual_gate=FactualGate(),
        render_gate=RenderGate(codegen=codegen, renderer=renderer),
        visual_qa_gate=VisualQaGate(
            vision=VisionQaInspector(invoke=build_vision_invoke(model)),
            codegen=codegen,
            renderer=renderer,
            frames=FrameExtractor(),
        ),
        assembler=VideoAssembler(),
        cache=ContractHashCache(),
        workspace_root=workspace_root,
    )
