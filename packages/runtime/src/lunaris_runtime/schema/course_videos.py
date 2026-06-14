from .base import CourseModel
from .video_artifact import VideoArtifact


class CourseVideos(CourseModel):
    """The course's opening videos — the V5 Overview section (plan §0).

    The course analogue of ``Lesson.video``: a ``summary`` course trailer ("what this course covers,
    module by module") and an ``overview`` topic intro ("what this topic is and why it matters"),
    each populated by the build at finalize (V5-T2) and ``None`` until then — so a course built
    before V5, with video off, or whose course-level render degraded simply carries no opening
    videos. Defined as its own block (rather than two fields on ``Course``) so the reader reads one
    ``course.videos`` slice and the payload grows by exactly one optional key.
    """

    summary: VideoArtifact | None = None
    overview: VideoArtifact | None = None
