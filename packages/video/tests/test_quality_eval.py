"""Hermetic tests for the C4 quality-eval harness (`_quality_eval`).

The harness drives a ``produce`` thunk (the pipeline seam) over a topic set and aggregates a
``QualityReport``. These tests stub the thunk so the aggregation logic — the part that must stay
green in CI — is exercised without a live model or render; the real pipeline is driven by the
key-gated ``test_video_quality_eval_live`` (added in T2).
"""

import json

import pytest
import structlog
from _quality_eval import QualityStatus, TopicSpec, VideoQualityEval
from lunaris_runtime.schema import DegradedScene
from lunaris_video.errors import FactualGateError
from lunaris_video.models import RenderedVideo
from lunaris_video.worker.failure_taxonomy import VideoFailureKind


def _video(scene_ids: list[str], *, degraded: list[str] | None = None) -> RenderedVideo:
    """A canned bundle: ``scene_ids`` becomes the contracts JSON the harness counts, and
    ``degraded`` becomes the best-effort degrade record it reads straight off the bundle."""
    degraded = degraded or []
    contracts = {"scenes": [{"id": sid} for sid in scene_ids]}
    return RenderedVideo(
        mp4=b"\x00\x00\x00\x18ftyp",
        poster=b"\xff\xd8\xff",
        contracts_json=json.dumps(contracts).encode(),
        timing_json=b"{}",
        degraded_scenes=tuple(DegradedScene(scene_id=sid, issues=["overflow"]) for sid in degraded),
    )


async def test_eval_aggregates_produced_and_degraded_across_topics() -> None:
    # Arrange — one clean video and one with two degraded scenes.
    topics = [TopicSpec(id="t1", label="clean lesson"), TopicSpec(id="t2", label="busy lesson")]
    videos = {
        "t1": _video(["S1", "S2", "S3"]),
        "t2": _video(["S1", "S2", "S3", "S4"], degraded=["S2", "S4"]),
    }

    async def produce(topic: TopicSpec) -> RenderedVideo:
        return videos[topic.id]

    # Act
    report = await VideoQualityEval().run(topics, produce)

    # Assert — aggregate metrics.
    assert report.produced == 2
    assert report.degraded == 1  # only t2 shipped a degraded scene
    assert report.total_scenes == 7
    assert report.degraded_scenes == 2
    assert report.degraded_scene_rate == pytest.approx(2 / 7)

    # Assert — per-topic classification.
    by_id = {result.topic_id: result for result in report.results}
    assert by_id["t1"].status is QualityStatus.PRODUCED_CLEAN
    assert by_id["t1"].scene_count == 3
    assert by_id["t1"].degraded_scene_count == 0
    assert by_id["t2"].status is QualityStatus.PRODUCED_DEGRADED
    assert by_id["t2"].degraded_scene_count == 2


async def test_eval_counts_scenes_in_a_chaptered_contract() -> None:
    # Arrange — the overview kind nests scenes under chapters; the harness must count them all.
    chaptered = RenderedVideo(
        mp4=b"\x00\x00\x00\x18ftyp",
        poster=b"\xff\xd8\xff",
        contracts_json=json.dumps(
            {"chapters": [{"scenes": [{"id": "S1"}, {"id": "S2"}]}, {"scenes": [{"id": "S3"}]}]}
        ).encode(),
        timing_json=b"{}",
    )

    async def produce(_: TopicSpec) -> RenderedVideo:
        return chaptered

    report = await VideoQualityEval().run([TopicSpec(id="ov", label="overview")], produce)

    assert report.total_scenes == 3
    assert report.results[0].status is QualityStatus.PRODUCED_CLEAN


async def test_eval_records_a_pipeline_failure_with_its_taxonomy_kind() -> None:
    # Arrange — one topic ships, one raises the way the pipeline does (Gate C major, pre-render).
    async def produce(topic: TopicSpec) -> RenderedVideo:
        if topic.id == "boom":
            raise FactualGateError("S2_mechanism", unsupported=["7 comparisons"], detail="smuggled")
        return _video(["S1", "S2"])

    report = await VideoQualityEval().run(
        [TopicSpec(id="ok", label="fine"), TopicSpec(id="boom", label="uncited figure")], produce
    )

    # A failure is NOT produced; it is bucketed by the SAME taxonomy the worker logs.
    assert report.produced == 1
    assert report.failed == 1
    assert report.failure_rate == pytest.approx(0.5)
    assert report.failures_by_kind == {VideoFailureKind.FACTUAL.value: 1}
    failed = next(result for result in report.results if result.topic_id == "boom")
    assert failed.status is QualityStatus.FAILED
    assert failed.failure_kind is VideoFailureKind.FACTUAL
    # A failed topic contributes no scenes, so it never dilutes the degraded-scene rate.
    assert failed.scene_count == 0


async def test_eval_aggregates_the_per_gate_degrade_histogram_from_telemetry() -> None:
    # Arrange — the harness reads the per-kind split off the pipeline's `produced` telemetry event
    # (the same one E1 / video-observability.md define), since the bundle flattens kind away.
    async def produce(_: TopicSpec) -> RenderedVideo:
        structlog.get_logger("test").info(
            "video_pipeline.produced", degraded_by_kind={"visual": 2, "sync": 1, "factual": 0}
        )
        return _video(["S1", "S2"], degraded=["S1"])

    report = await VideoQualityEval().run([TopicSpec(id="t", label="busy")], produce)

    assert report.degraded_by_kind == {"visual": 2, "sync": 1, "factual": 0}
    assert report.results[0].degraded_by_kind == {"visual": 2, "sync": 1, "factual": 0}


async def test_meets_ceiling_gates_on_both_degrade_rate_and_failures() -> None:
    # Arrange — 3 topics: clean (3 scenes), degraded (4 scenes, 1 degraded), and one failure.
    async def produce(topic: TopicSpec) -> RenderedVideo:
        if topic.id == "fail":
            raise FactualGateError("S1", unsupported=["x"], detail="d")
        if topic.id == "degraded":
            return _video(["S1", "S2", "S3", "S4"], degraded=["S2"])
        return _video(["S1", "S2", "S3"])

    topics = [
        TopicSpec(id="clean", label="a"),
        TopicSpec(id="degraded", label="b"),
        TopicSpec(id="fail", label="c"),
    ]
    report = await VideoQualityEval().run(topics, produce)

    assert report.degraded_scene_rate == pytest.approx(1 / 7)
    # Within both budgets (rate under 0.2, one failure allowed).
    assert report.meets_ceiling(max_degraded_scene_rate=0.2, max_failures=1) is True
    # The rate ceiling bites.
    assert report.meets_ceiling(max_degraded_scene_rate=0.1, max_failures=1) is False
    # The failure ceiling bites (default tolerates zero failures).
    assert report.meets_ceiling(max_degraded_scene_rate=0.2) is False
