from collections.abc import Callable
from pathlib import Path

from lunaris_runtime.credentials import resolve_secret
from lunaris_runtime.persistence import ICourseStore, IVideoStorage
from lunaris_runtime.schema import VideoKind

from lunaris_video.assembly import VideoAssembler
from lunaris_video.codegen import SceneCodeGenerator
from lunaris_video.gates import FactualGate, LengthGate, RenderGate, SyncGate, VisualQaGate
from lunaris_video.grounding import CourseGroundingPacketBuilder
from lunaris_video.pipeline.contract_hash_cache import ContractHashCache
from lunaris_video.pipeline.kind_routing_video_pipeline import KindRoutingVideoPipeline
from lunaris_video.pipeline.model_adapters import (
    VIDEO_MAX_OUTPUT_TOKENS,
    build_text_invoke,
    build_vision_invoke,
    default_video_model,
)
from lunaris_video.pipeline.video_pipeline import VideoPipeline
from lunaris_video.planning import ScenePlanner
from lunaris_video.protocols.lesson_source_provider_protocol import ILessonSourceProvider
from lunaris_video.protocols.prior_contract_provider_protocol import IPriorContractProvider
from lunaris_video.protocols.speech_synthesizer_protocol import ISpeechSynthesizer
from lunaris_video.qa import SyncQaInspector, VisionQaInspector
from lunaris_video.rendering import (
    FrameExtractor,
    SceneRenderer,
    pad_scene_tail,
    probe_scene_duration,
)
from lunaris_video.sourcing import (
    CourseStoreLessonSourceProvider,
    CourseVideoSourceProvider,
    StoragePriorContractProvider,
)
from lunaris_video.voice import ElevenLabsSpeechSynthesizer

_ELEVENLABS_KEY_ENV = "ELEVENLABS_API_KEY"

# A factory closure that wires one VideoPipeline over the shared toolchain, varying only the source
# provider (what it grounds against) and whether it plans a chaptered overview.
_PipelineMaker = Callable[[ILessonSourceProvider, bool], VideoPipeline]


def build_video_pipeline(
    *,
    store: ICourseStore,
    workspace_root: Path,
    model_id: str | None = None,
    storage: IVideoStorage | None = None,
) -> KindRoutingVideoPipeline:
    """Wire the worker's real pipeline — one per kind behind a kind router (V5).

    The composition root's single call: a LESSON pipeline grounded on the course store, and SUMMARY
    (flat) + OVERVIEW (chaptered) pipelines grounded on the per-job grounding snapshot — all sharing
    one model/codegen/render/QA toolchain (V4: sharing a pipeline's stateless tools across workers
    is safe; only each ContractHashCache is per-pipeline). The router dispatches each job by kind.
    ``storage`` (the artifact store) wires the prior-contract reuse for the regenerate menu (V6-T2)
    and the upstream-sibling context the lesson planner builds on (the video dependency map);
    omitted, regenerate jobs simply re-plan and a lesson plans without its prerequisites' context.
    """
    prior_contract_provider = StoragePriorContractProvider(storage) if storage is not None else None
    make = _pipeline_maker(
        workspace_root=workspace_root,
        model_id=model_id,
        prior_contract_provider=prior_contract_provider,
    )
    packet_builder = CourseGroundingPacketBuilder()
    lesson_source = CourseStoreLessonSourceProvider(
        store, packet_builder=packet_builder, video_storage=storage
    )
    course_source = CourseVideoSourceProvider(packet_builder=packet_builder)
    return KindRoutingVideoPipeline(
        pipelines={
            VideoKind.LESSON: make(lesson_source, False),
            VideoKind.SUMMARY: make(course_source, False),
            VideoKind.OVERVIEW: make(course_source, True),
        }
    )


def _pipeline_maker(
    *,
    workspace_root: Path,
    model_id: str | None,
    prior_contract_provider: IPriorContractProvider | None,
) -> _PipelineMaker:
    """Build the shared toolchain once and return a maker for per-kind ``VideoPipeline``s.

    One ``SceneCodeGenerator``/``SceneRenderer``/``FrameExtractor``/planner/vision-invoke is shared
    across every pipeline and gate (Gate B's repairs re-render with the same toolchain; Gate D
    samples with the same extractor). The model is the build's strong, vision-capable tier. Voice is
    keyed-only: the synthesizer provider resolves the tenant's ElevenLabs key per produce
    (the contextvar seam) and returns ``None`` when absent, so a voice-on job without a key fails
    fast and a silent build never pays.
    """
    model = model_id or default_video_model()
    # The planner (chaptered overview especially) + codegen emit large responses; raise the output
    # ceiling so a big contract is not truncated by the provider default (the prod EOF failure).
    text_invoke = build_text_invoke(model, max_tokens=VIDEO_MAX_OUTPUT_TOKENS)
    vision_invoke = build_vision_invoke(model)
    codegen = SceneCodeGenerator(invoke=text_invoke)
    renderer = SceneRenderer()
    frames = FrameExtractor()
    planner = ScenePlanner(invoke=text_invoke)

    def synthesizer_provider() -> ISpeechSynthesizer | None:
        key = resolve_secret(_ELEVENLABS_KEY_ENV)
        return ElevenLabsSpeechSynthesizer(api_key=key) if key else None

    def make(source_provider: ILessonSourceProvider, chaptered: bool) -> VideoPipeline:
        return VideoPipeline(
            source_provider=source_provider,
            planner=planner,
            factual_gate=FactualGate(),
            render_gate=RenderGate(codegen=codegen, renderer=renderer),
            visual_qa_gate=VisualQaGate(
                vision=VisionQaInspector(invoke=vision_invoke),
                codegen=codegen,
                renderer=renderer,
                frames=frames,
            ),
            assembler=VideoAssembler(),
            cache=ContractHashCache(),
            workspace_root=workspace_root,
            model_id=model,
            chaptered=chaptered,
            synthesizer_provider=synthesizer_provider,
            sync_gate=SyncGate(
                vision=SyncQaInspector(invoke=vision_invoke),
                frames=frames,
                codegen=codegen,
                renderer=renderer,
            ),
            length_gate=LengthGate(probe=probe_scene_duration, pad=pad_scene_tail),
            prior_contract_provider=prior_contract_provider,
        )

    return make
