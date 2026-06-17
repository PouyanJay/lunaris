"""Live, key-gated C4 quality eval: drive the REAL pipeline over a fixed topic set and assert the
scene-degradation rate stays under a regression ceiling.

Deselected unless ``-m eval``; needs ANTHROPIC_API_KEY and the render extra, so it self-skips on a
keyless box exactly like ``test_video_pipeline_live`` (the hermetic ``test_quality_eval`` covers the
harness aggregation in CI). This is the flywheel C1/C2/C3 are judged against: it renders the topics
that exposed the failures in prod (binary search's uncited figure, the neural-net "web of nodes", a
framing-only topic) and turns "are scenes coming out clean?" into one number.

Run it with ``-m eval`` against this file, e.g.
``uv run --env-file .env pytest -m eval packages/video/tests/test_video_quality_eval_live.py -s``.

Cost note: this renders several full lessons on live Claude (plan, Manim, render, vision QA), each
with fresh-take re-plans, so minutes per topic. It is a keyed *nightly*, not a per-commit gate.

CEILINGS (calibrate on the first real keyed run; start permissive). The prod incident showed 50 to
75 percent of scenes shipping degraded, so the regression ceiling starts at 0.75: a run that
degrades MORE than that fails. As C1/C2/C3 land and real numbers come in, tighten it.
``max_failures`` is 0 because the A1 severity-tiered factual gate (Phase 1) means these topics
should no longer hard-fail a whole video on one uncited figure.
"""

import importlib.util
import os
from pathlib import Path

import pytest
from _quality_eval import Produce, QualityStatus, TopicSpec, VideoQualityEval
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video.assembly import VideoAssembler
from lunaris_video.codegen import SceneCodeGenerator
from lunaris_video.errors import VideoPipelineError
from lunaris_video.gates import FactualGate, LengthGate, RenderGate, SyncGate, VisualQaGate
from lunaris_video.models import (
    GroundedClaim,
    GroundingPacket,
    LessonSource,
    PacketKind,
    RenderedVideo,
)
from lunaris_video.pipeline import ContractHashCache, VideoPipeline
from lunaris_video.pipeline.model_adapters import (
    build_text_invoke,
    build_vision_invoke,
    default_video_model,
)
from lunaris_video.planning import ScenePlanner
from lunaris_video.qa import SyncQaInspector, VisionQaInspector
from lunaris_video.rendering import (
    FrameExtractor,
    SceneRenderer,
    pad_scene_tail,
    probe_scene_duration,
)
from lunaris_video.voice import ElevenLabsSpeechSynthesizer

pytestmark = pytest.mark.eval

# A scene that won't clean up after the repair budget ships degraded; the ceiling guards against a
# run getting WORSE than the prod baseline. ``max_failures=0`` after the Phase-1 factual-gate flip.
_MAX_DEGRADED_SCENE_RATE = 0.75
_MAX_FAILURES = 0
# The planner is non-deterministic, so a re-plan can clear a scene a prior take couldn't — the
# product's "Fresh take" recovery. A topic that fails every take is a real failure.
_FRESH_TAKE_ATTEMPTS = 3


def _packet(*claims: GroundedClaim) -> GroundingPacket:
    return GroundingPacket(kind=PacketKind.LESSON, claims=claims)


# The fixed topic set: easy → hard, spanning the cases that exposed the prod failures. Each is a
# realistic lesson the planner grounds against. T6 parametrizes over kinds/voice on top of this.
_TOPICS: tuple[tuple[TopicSpec, LessonSource], ...] = (
    (
        TopicSpec(id="hash", label="how a hash function works (easy, conceptual)"),
        LessonSource(
            course_topic="Computer science fundamentals",
            lesson_title="How a hash function works",
            audience="curious beginners with no CS background",
            prose=(
                "A hash function takes an input of any size and returns a fixed-size string called "
                "a hash. The same input always produces the same hash, but a tiny change yields a "
                "completely different one. It is one-way: you cannot reverse a hash back into the "
                "original input."
            ),
            packet=_packet(
                GroundedClaim(
                    id="c1",
                    text="A hash function returns a fixed-size hash for an input of any size.",
                    citation_id="cite-hash",
                    source_label="Crypto 101",
                ),
                GroundedClaim(
                    id="c2",
                    text="The same input always produces the same hash; a tiny change produces a "
                    "completely different one.",
                    citation_id="cite-hash",
                    source_label="Crypto 101",
                ),
            ),
        ),
    ),
    (
        TopicSpec(id="binary_search", label="binary search (the uncited-figure hard-fail case)"),
        LessonSource(
            course_topic="Algorithms",
            lesson_title="How binary search works",
            audience="first-year CS students who know arrays",
            prose=(
                "Binary search finds a target in a sorted array by repeatedly halving the search "
                "range: compare the middle element, then keep only the half that could contain the "
                "target. Each step throws away half the remaining elements, so the work grows with "
                "the logarithm of the array size."
            ),
            packet=_packet(
                GroundedClaim(
                    id="c1",
                    text="Binary search requires the array to be sorted.",
                    citation_id="cite-clrs",
                    source_label="CLRS",
                ),
                GroundedClaim(
                    id="c2",
                    text="Binary search runs in O(log n) time because each step halves the range.",
                    citation_id="cite-clrs",
                    source_label="CLRS",
                ),
            ),
        ),
    ),
    (
        TopicSpec(id="neural_net", label="a neural network (the 'web of nodes' archetype)"),
        LessonSource(
            course_topic="Machine learning",
            lesson_title="What a neural network is",
            audience="curious newcomers with no ML background",
            prose=(
                "A neural network is layers of simple units, wired together. Each connection has a "
                "weight; each unit adds up its inputs, applies a simple function, and passes the "
                "result on. Stacking layers lets the network learn patterns too complex for one "
                "step."
            ),
            packet=_packet(
                GroundedClaim(
                    id="c1",
                    text="A neural network is organised into layers of simple units connected by "
                    "weighted edges.",
                    citation_id="cite-ml",
                    source_label="Deep Learning, Goodfellow et al.",
                ),
            ),
        ),
    ),
    (
        TopicSpec(id="framing_only", label="a framing-heavy topic with no verified claims"),
        LessonSource(
            course_topic="Study skills",
            lesson_title="Why spaced repetition helps you remember",
            audience="students who want to study smarter",
            prose=(
                "Spaced repetition revisits material at growing intervals, just before you would "
                "forget it. Each well-timed review strengthens the memory and stretches how long "
                "it lasts, so the same total study time sticks far better than cramming."
            ),
            packet=_packet(),  # no claims → every scene must be framing-only
        ),
    ),
)


class _TopicLessonProvider:
    """An ``ILessonSourceProvider`` that returns the lesson keyed by the driving job's id, so one
    pipeline instance can render the whole topic set."""

    def __init__(self, lessons: dict[str, LessonSource]) -> None:
        self._lessons = lessons

    async def load(self, job: VideoJob) -> LessonSource:
        return self._lessons[job.id]


def _build_pipeline(
    model: str,
    lessons: dict[str, LessonSource],
    tmp_path: Path,
    *,
    voiced: bool = False,
    chaptered: bool = False,
) -> VideoPipeline:
    codegen = SceneCodeGenerator(invoke=build_text_invoke(model))
    renderer = SceneRenderer(timeout_s=300)
    frames = FrameExtractor()
    # The voiced path wires the full sync stack: ElevenLabs narration, Gate D (per-beat sync repair)
    # and Gate 1 (the length gate WITH the C3 auto-padder) — so the voiced eval exercises C3 live.
    voice_kwargs = {}
    if voiced:
        voice_kwargs = {
            "synthesizer_provider": lambda: ElevenLabsSpeechSynthesizer(
                api_key=os.environ["ELEVENLABS_API_KEY"]
            ),
            "sync_gate": SyncGate(
                vision=SyncQaInspector(invoke=build_vision_invoke(model)),
                frames=frames,
                codegen=codegen,
                renderer=renderer,
            ),
            "length_gate": LengthGate(probe=probe_scene_duration, pad=pad_scene_tail),
        }
    return VideoPipeline(
        source_provider=_TopicLessonProvider(lessons),
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
        chaptered=chaptered,
        **voice_kwargs,
    )


def _drive(pipeline: VideoPipeline, *, kind: VideoKind, voiced: bool) -> Produce:
    """A produce thunk over ``pipeline``: build a job for the topic and render it, allowing the
    product's 'Fresh take' re-plans on a gate failure (a topic that fails every take is a real
    failure for the taxonomy)."""

    async def produce(topic: TopicSpec) -> RenderedVideo:
        job = VideoJob(
            id=topic.id,
            user_id="00000000-0000-0000-0000-000000000001",
            course_id="course-eval",
            lesson_id=topic.id,
            kind=kind,
            input_hash="h",
            config={"voice": True} if voiced else {},
        )
        last: VideoPipelineError | None = None
        for _ in range(_FRESH_TAKE_ATTEMPTS):
            try:
                return await pipeline.produce(job)
            except VideoPipelineError as exc:
                last = exc
        assert last is not None  # _FRESH_TAKE_ATTEMPTS is positive, so a failure was recorded
        raise last

    return produce


@pytest.mark.parametrize("voiced", [False, True], ids=["silent", "voiced"])
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.skipif(
    importlib.util.find_spec("manim") is None, reason="render extra not installed (make video-deps)"
)
async def test_quality_eval_over_the_topic_set_stays_under_the_ceiling(
    tmp_path, capsys, voiced
) -> None:
    # Arrange — the topic set through one real pipeline, silent and (with an ElevenLabs key) voiced,
    # so the eval covers BOTH narration modes. Voiced additionally exercises Gate D + the C3 padder.
    if voiced and not os.getenv("ELEVENLABS_API_KEY"):
        pytest.skip("the voiced eval needs ELEVENLABS_API_KEY")
    model = default_video_model()
    lessons = {spec.id: lesson for spec, lesson in _TOPICS}
    pipeline = _build_pipeline(model, lessons, tmp_path, voiced=voiced)
    produce = _drive(pipeline, kind=VideoKind.LESSON, voiced=voiced)

    # Act
    report = await VideoQualityEval().run([spec for spec, _ in _TOPICS], produce)

    # Report — the per-topic and aggregate picture, always printed so a keyed run is legible.
    with capsys.disabled():
        print(
            f"\nC4 quality eval: produced={report.produced} degraded={report.degraded} "
            f"failed={report.failed} | scenes={report.total_scenes} "
            f"degraded_scenes={report.degraded_scenes} "
            f"rate={report.degraded_scene_rate:.2f}"
        )
        print(f"  degraded_by_kind={report.degraded_by_kind} failures={report.failures_by_kind}")
        for result in report.results:
            print(
                f"  - {result.topic_id}: {result.status.value} "
                f"({result.degraded_scene_count}/{result.scene_count} degraded)"
            )

    # Assert — the regression gate: no whole-video hard-fails, degradation under the ceiling.
    assert report.produced >= 1, f"nothing shipped: {report.failures_by_kind}"
    assert not any(
        result.failure_kind is not None and result.failure_kind.value == "infrastructure"
        for result in report.results
    ), "an infrastructure failure means a harness/wiring bug, not a quality signal"
    assert report.meets_ceiling(
        max_degraded_scene_rate=_MAX_DEGRADED_SCENE_RATE, max_failures=_MAX_FAILURES
    ), (
        f"quality regressed: rate={report.degraded_scene_rate:.2f} "
        f"(ceiling {_MAX_DEGRADED_SCENE_RATE}), failed={report.failed}"
    )
    # Sanity: at least one topic actually exercised the pipeline end-to-end.
    assert any(result.status is not QualityStatus.FAILED for result in report.results)


# A course-overview source for the chaptered (overview) kind — the third VideoKind. No verified
# claims, so every scene is framing-only (an overview tours the course, it asserts no figures).
_OVERVIEW = LessonSource(
    course_topic="Algorithms",
    lesson_title="Course overview: searching and sorting",
    audience="first-year CS students",
    prose=(
        "This course tours how computers search and sort data: why order matters, how a few simple "
        "strategies (divide-and-conquer, comparison, halving) underpin the fast algorithms, and "
        "where each one shines. By the end you will know which tool fits which problem."
    ),
    packet=GroundingPacket(kind=PacketKind.OVERVIEW),
)


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY")
@pytest.mark.skipif(
    importlib.util.find_spec("manim") is None, reason="render extra not installed (make video-deps)"
)
async def test_quality_eval_covers_the_chaptered_overview_kind(tmp_path, capsys) -> None:
    # Arrange — the overview kind plans CHAPTERED (the third VideoKind), so the eval must score it
    # too: the harness counts scenes across chapters and the ceiling holds for the longer format.
    model = default_video_model()
    topic = TopicSpec(id="overview", label="chaptered course overview")
    pipeline = _build_pipeline(model, {topic.id: _OVERVIEW}, tmp_path, chaptered=True)
    produce = _drive(pipeline, kind=VideoKind.OVERVIEW, voiced=False)

    # Act
    report = await VideoQualityEval().run([topic], produce)

    # Report
    with capsys.disabled():
        result = report.results[0]
        print(
            f"\nC4 overview eval: {result.status.value} "
            f"({result.degraded_scene_count}/{result.scene_count} degraded) "
            f"rate={report.degraded_scene_rate:.2f}"
        )

    # Assert — the chaptered overview shipped, was scored across its chapters, and stayed under the
    # ceiling (a multi-chapter video should have several scenes).
    assert report.failed == 0, f"the overview hard-failed: {report.failures_by_kind}"
    assert report.results[0].scene_count >= 3  # chapters x scenes, counted across the contract
    assert report.meets_ceiling(
        max_degraded_scene_rate=_MAX_DEGRADED_SCENE_RATE, max_failures=_MAX_FAILURES
    )
