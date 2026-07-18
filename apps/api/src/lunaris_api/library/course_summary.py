from dataclasses import dataclass
from datetime import datetime

from lunaris_runtime.schema import CourseStatus, CoverArtifact

from .course_level import CourseLevel
from .learner_course_status import LearnerCourseStatus


@dataclass(frozen=True)
class CourseSummary:
    """One My-courses library card's facts — derived per read, never stored (a rebuild can change
    the course shape, so a stored aggregate could go stale)."""

    course_id: str
    topic: str
    lesson_total: int
    lessons_done: int
    percent: int
    concept_total: int
    level: CourseLevel | None
    learner_status: LearnerCourseStatus
    course_status: CourseStatus
    built_at: datetime
    last_opened_at: datetime | None
    # The course's AI cover handle (course-cover-images), carried so the grid card can render the
    # image or the Typographic fallback, and so the reader can regenerate. Only the artifact
    # (jobId + status + provenance) rides here; the router pre-signs the display-size thumb URL onto
    # the wire `CourseSummaryView` at list time (see cover_thumbs.sign_library_cover_thumbs).
    cover: CoverArtifact | None = None
