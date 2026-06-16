"""Hermetic tests for the C4 quality-eval harness (`_quality_eval`).

The harness drives a ``produce`` thunk (the pipeline seam) over a topic set and aggregates a
``QualityReport``. These tests stub the thunk so the aggregation logic — the part that must stay
green in CI — is exercised without a live model or render; the real pipeline is driven by the
key-gated ``test_video_quality_eval_live`` (added in T2).
"""

import json

import pytest
from _quality_eval import QualityStatus, TopicSpec, VideoQualityEval
from lunaris_runtime.schema import DegradedScene
from lunaris_video.models import RenderedVideo


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
