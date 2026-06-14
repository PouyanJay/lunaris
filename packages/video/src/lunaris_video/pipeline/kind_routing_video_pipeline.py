from collections.abc import Mapping

import structlog
from lunaris_runtime.schema import VideoJob, VideoKind

from lunaris_video.errors import VideoPipelineError
from lunaris_video.models.rendered_video import RenderedVideo
from lunaris_video.protocols.video_pipeline_protocol import IVideoPipeline, StageReporter

_logger = structlog.get_logger(__name__)


class KindRoutingVideoPipeline:
    """Dispatches each job to the pipeline configured for its kind (``IVideoPipeline``).

    The worker holds ONE pipeline (its contract is unchanged); this is that one — a thin router that
    sends a LESSON job to the lesson pipeline, a SUMMARY/OVERVIEW job to the course-level pipelines
    (the latter chaptered). The only kind-aware seam in the worker path: each inner pipeline is
    configured for its kind and never re-derives it. A kind with no pipeline fails the job
    cleanly rather than rendering the wrong shape.
    """

    def __init__(self, *, pipelines: Mapping[VideoKind, IVideoPipeline]) -> None:
        self._pipelines = dict(pipelines)

    async def produce(
        self, job: VideoJob, *, on_stage: StageReporter | None = None
    ) -> RenderedVideo:
        pipeline = self._pipelines.get(job.kind)
        if pipeline is None:
            raise VideoPipelineError(f"no video pipeline configured for kind {job.kind.value}")
        _logger.info("kind_routing.dispatch", job_id=job.id, kind=job.kind.value)
        return await pipeline.produce(job, on_stage=on_stage)
