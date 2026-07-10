from .base import CourseModel
from .cover_provenance import CoverProvenance
from .enums import CoverJobStatus


class CoverArtifact(CourseModel):
    """A course's AI cover image as it rides in the course payload.

    The course analogue of ``VideoArtifact``: it keeps a ``job_id`` HANDLE (not a raw URL) so the
    API resolves a fresh signed URL on demand from the private ``course-covers`` bucket — a URL is
    never persisted stale in the payload JSONB. ``status`` says whether the image is ready; while a
    cover is still generating (or absent) the reader falls back to the constellation loading state,
    and a keyless account shows the Typographic cover instead of ever enqueuing one.

    ``provenance`` is ``None`` for a cover that has none (a FAILED job); a READY artifact always
    carries it (provenance is built at the source the moment the image passes Claude vision-QA).
    ``job_id`` is present even when FAILED, so the reader's regenerate action can re-run it.
    """

    status: CoverJobStatus
    job_id: str | None = None
    provenance: CoverProvenance | None = None
