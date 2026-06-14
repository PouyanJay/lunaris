"""KindRoutingVideoPipeline (video V5-T2): the worker's single pipeline that dispatches each job to
the inner pipeline configured for its kind — the only kind-aware seam in the worker path."""

import pytest
from lunaris_runtime.schema import VideoJob, VideoKind
from lunaris_video.errors import VideoPipelineError
from lunaris_video.models.rendered_video import RenderedVideo
from lunaris_video.pipeline import KindRoutingVideoPipeline


class _MarkerPipeline:
    """An IVideoPipeline that records the job it produced and returns a marked rendered video."""

    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.produced: list[VideoJob] = []

    async def produce(self, job: VideoJob) -> RenderedVideo:
        self.produced.append(job)
        return RenderedVideo(
            mp4=self.marker.encode(), poster=b"p", contracts_json=b"{}", timing_json=b"{}"
        )


def _job(kind: VideoKind) -> VideoJob:
    return VideoJob(id="j", user_id="u", course_id="c1", kind=kind, input_hash="h")


async def test_routes_each_kind_to_its_configured_pipeline() -> None:
    # Arrange — a distinct pipeline per kind.
    lesson, summary, overview = _MarkerPipeline("L"), _MarkerPipeline("S"), _MarkerPipeline("O")
    router = KindRoutingVideoPipeline(
        pipelines={
            VideoKind.LESSON: lesson,
            VideoKind.SUMMARY: summary,
            VideoKind.OVERVIEW: overview,
        }
    )

    # Act — drive a job of each kind so the whole routing table is triangulated, not one slot.
    overview_out = await router.produce(_job(VideoKind.OVERVIEW))
    summary_out = await router.produce(_job(VideoKind.SUMMARY))

    # Assert — each job reached its own pipeline and that pipeline's output came back; no crosstalk.
    assert overview_out.mp4 == b"O" and [j.kind for j in overview.produced] == [VideoKind.OVERVIEW]
    assert summary_out.mp4 == b"S" and [j.kind for j in summary.produced] == [VideoKind.SUMMARY]
    assert lesson.produced == []


async def test_an_unconfigured_kind_fails_clean() -> None:
    # Arrange — a router missing the OVERVIEW pipeline.
    router = KindRoutingVideoPipeline(pipelines={VideoKind.LESSON: _MarkerPipeline("L")})

    # Act / Assert — a job for a kind with no pipeline fails (the worker settles it FAILED) rather
    # than silently rendering the wrong shape.
    with pytest.raises(VideoPipelineError):
        await router.produce(_job(VideoKind.OVERVIEW))
