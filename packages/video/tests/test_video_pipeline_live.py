"""Live, key-gated acceptance: the REAL pipeline renders a real lesson on live Claude.

Deselected unless ``-m eval``; needs ANTHROPIC_API_KEY and the render extra. Drives the full
LessonVideoPipeline with real model adapters — Claude plans the scene contracts, writes the Manim,
and judges the frames (Gate B) — and asserts a real multi-scene MP4 comes out. This is the V1
acceptance criterion "key-gated live eval renders a real lesson": no scripted model, real renders.

Run: ``uv run --env-file .env pytest -m eval packages/video/tests/test_video_pipeline_live.py -s``
"""

import importlib.util
import json
import os

import pytest
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video.assembly import VideoAssembler
from lunaris_video.codegen import SceneCodeGenerator
from lunaris_video.errors import VideoPipelineError
from lunaris_video.gates import FactualGate, RenderGate, SyncGate, VisualQaGate
from lunaris_video.models import GroundedClaim, GroundingPacket, LessonSource, PacketKind
from lunaris_video.pipeline import ContractHashCache, LessonVideoPipeline
from lunaris_video.pipeline.model_adapters import (
    build_text_invoke,
    build_vision_invoke,
    default_video_model,
)
from lunaris_video.planning import ScenePlanner
from lunaris_video.qa import SyncQaInspector, VisionQaInspector
from lunaris_video.rendering import FrameExtractor, SceneRenderer
from lunaris_video.voice import ElevenLabsSpeechSynthesizer

pytestmark = pytest.mark.eval

# A conceptual lesson with visually-friendly scenes (a metaphor, a simple flow) rather than a dense
# data layout — gives Gate B a fair chance to pass on a real model. Coherent title + prose, plus a
# grounding packet so the live eval exercises the full V2 path: the model cites these verified
# claims and Gate C checks every narrated figure against them.
_PACKET = GroundingPacket(
    kind=PacketKind.LESSON,
    claims=(
        GroundedClaim(
            id="c1",
            text="A hash function returns a fixed-size hash for an input of any size.",
            citation_id="cite-hash",
            source_label="Crypto 101",
        ),
        GroundedClaim(
            id="c2",
            text="The same input always produces the same hash, and a tiny change "
            "produces a completely different one.",
            citation_id="cite-hash",
            source_label="Crypto 101",
        ),
        GroundedClaim(
            id="c3",
            text="A hash cannot be reversed back into the original input.",
            citation_id="cite-hash",
            source_label="Crypto 101",
        ),
    ),
)
_LESSON = LessonSource(
    course_topic="Computer science fundamentals",
    lesson_title="How a hash function works",
    audience="curious beginners with no CS background",
    prose=(
        "A hash function takes an input of any size and returns a fixed-size string of "
        "characters, called a hash. The same input always produces the same hash, but even a "
        "tiny change to the input produces a completely different hash. It is a one-way street: "
        "you cannot reverse a hash back into the original input. Hashes let computers compare "
        "and look up data quickly without storing the original, which is why they power password "
        "checks, file fingerprints, and fast lookups."
    ),
    packet=_PACKET,
)

# The product's "Fresh take" recovery: the planner is non-deterministic, so a re-plan can clear a
# scene Gate B couldn't converge on. The eval allows a small budget of fresh attempts, mirroring
# the regenerate menu (V4) — a build never ships a video that failed every fresh take.
_FRESH_TAKE_ATTEMPTS = 3
# The WPM estimate over a multi-scene lesson's beats; conservatively below the 60-90s target so
# model-dependent beat brevity doesn't make it flaky, but high enough to catch a degenerate plan.
_MIN_TOTAL_SECONDS = 30.0


class _FixedLessonProvider:
    async def load(self, job: VideoJob) -> LessonSource:
        return _LESSON


async def _produce_with_fresh_takes(
    pipeline: LessonVideoPipeline, job: VideoJob, *, attempts: int
) -> tuple[object, list[str]]:
    """Produce, re-planning on a gate failure (the product's 'Fresh take') up to ``attempts``.

    Returns (video-or-None, failure-messages). A model never ships a video that failed every fresh
    take — the caller asserts a video resulted; the failures explain it if none did.
    """
    failures: list[str] = []
    for attempt in range(1, attempts + 1):
        try:
            return await pipeline.produce(job), failures
        except VideoPipelineError as exc:
            failures.append(f"attempt {attempt}: {exc}")
    return None, failures


def _job(job_id: str = "live-eval-job", *, voice: bool = False) -> VideoJob:
    return VideoJob(
        id=job_id,
        user_id="00000000-0000-0000-0000-000000000001",
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="h",
        config={"voice": True} if voice else {},
    )


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.skipif(
    importlib.util.find_spec("manim") is None, reason="render extra not installed (make video-deps)"
)
async def test_a_real_lesson_renders_on_live_claude(tmp_path, capsys) -> None:
    # Arrange — the real pipeline with live model adapters.
    model = default_video_model()
    codegen = SceneCodeGenerator(invoke=build_text_invoke(model))
    renderer = SceneRenderer(timeout_s=300)
    pipeline = LessonVideoPipeline(
        lesson_provider=_FixedLessonProvider(),
        planner=ScenePlanner(invoke=build_text_invoke(model)),
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
        workspace_root=tmp_path,
        model_id=model,
    )

    # Act — render the lesson, allowing fresh-take re-plans on a gate failure.
    video, failures = await _produce_with_fresh_takes(
        pipeline, _job(), attempts=_FRESH_TAKE_ATTEMPTS
    )

    # Assert — a real, multi-scene, Gate-B-passed silent MP4 of a sensible length, with the
    # regeneration manifests.
    assert video is not None, "no fresh take produced a video:\n" + "\n".join(failures)
    assert video.mp4[4:8] == b"ftyp"
    assert video.poster[:3] == b"\xff\xd8\xff"
    contracts = json.loads(video.contracts_json)
    assert len(contracts["scenes"]) >= 3
    timing = json.loads(video.timing_json)
    assert len(timing) == len(contracts["scenes"])
    total = sum(scene["total_s"] for scene in timing.values())
    assert total >= _MIN_TOTAL_SECONDS  # a real lesson, not a degenerate few-second stub
    with capsys.disabled():
        scenes, kb = len(contracts["scenes"]), len(video.mp4) // 1024
        print(f"\nlive video: {scenes} scenes, ~{total:.1f}s, {kb} KB")
        for failure in failures:
            print(f"  (fresh take needed) {failure}")


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.skipif(not os.getenv("ELEVENLABS_API_KEY"), reason="needs ELEVENLABS_API_KEY")
@pytest.mark.skipif(
    importlib.util.find_spec("manim") is None, reason="render extra not installed (make video-deps)"
)
async def test_a_real_lesson_renders_narrated_on_live_claude_and_elevenlabs(
    tmp_path, capsys
) -> None:
    # Arrange — the real voiced pipeline: live Claude plans/codes/QAs, ElevenLabs narrates, the
    # render is timing-driven by measured audio, the assembler muxes + captions, Gate D syncs.
    model = default_video_model()
    codegen = SceneCodeGenerator(invoke=build_text_invoke(model))
    renderer = SceneRenderer(timeout_s=300)
    frames = FrameExtractor()
    pipeline = LessonVideoPipeline(
        lesson_provider=_FixedLessonProvider(),
        planner=ScenePlanner(invoke=build_text_invoke(model)),
        factual_gate=FactualGate(),
        render_gate=RenderGate(codegen=codegen, renderer=renderer),
        visual_qa_gate=VisualQaGate(
            vision=VisionQaInspector(invoke=build_vision_invoke(model)),
            codegen=codegen,
            renderer=renderer,
            frames=frames,
        ),
        assembler=VideoAssembler(),
        cache=ContractHashCache(),
        workspace_root=tmp_path,
        model_id=model,
        synthesizer_provider=lambda: ElevenLabsSpeechSynthesizer(
            api_key=os.environ["ELEVENLABS_API_KEY"]
        ),
        sync_gate=SyncGate(
            vision=SyncQaInspector(invoke=build_vision_invoke(model)), frames=frames
        ),
    )

    # Act — narrated-in-one-pass, allowing fresh-take re-plans on a gate failure.
    video, failures = await _produce_with_fresh_takes(
        pipeline, _job("live-eval-voiced", voice=True), attempts=_FRESH_TAKE_ATTEMPTS
    )

    # Assert — a real, multi-scene, narrated MP4: the timing is MEASURED (clips, not the estimate),
    # a valid WebVTT track with cues shipped, and the video came out only because Gate D passed.
    assert video is not None, "no fresh take produced a narrated video:\n" + "\n".join(failures)
    assert video.mp4[4:8] == b"ftyp"
    contracts = json.loads(video.contracts_json)
    assert len(contracts["scenes"]) >= 3
    timing = json.loads(video.timing_json)
    assert any(beat["audio"] for scene in timing.values() for beat in scene["beats"]), (
        "narrated timing must carry measured clips, not the silent estimate"
    )
    total = sum(scene["total_s"] for scene in timing.values())
    assert total >= _MIN_TOTAL_SECONDS  # a real lesson, not a degenerate few-second stub
    assert video.captions is not None
    assert video.captions.startswith(b"WEBVTT") and b"-->" in video.captions
    with capsys.disabled():
        scenes, caption_bytes = len(contracts["scenes"]), len(video.captions)
        print(f"\nlive narrated: {scenes} scenes, ~{total:.1f}s, captions {caption_bytes} B")
