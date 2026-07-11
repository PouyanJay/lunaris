from dataclasses import dataclass
from typing import Self

from lunaris_runtime.schema import CoverJob


@dataclass(frozen=True)
class CoverArtifactPaths:
    """Where a cover job's artifacts live in the course-covers bucket — the one path convention.

    ``{user_id}/{course_id}/{job_id}/…`` is load-bearing three ways: the storage RLS policy scopes
    reads to the first segment, course deletion is a prefix-delete on the first two, and the
    worker/API never have to exchange paths — both derive them from the job row. A cover has up to
    three durable artifacts: the ``image`` (the DARK PNG — the original ``cover.png``, so every
    pre-dual-theme cover keeps working unchanged), the optional ``image_light`` (the LIGHT-theme
    rendition, present only for dual-theme covers), and the ``provenance`` (the structural record
    the API threads onto the wire).
    """

    image: str
    image_light: str
    provenance: str

    @classmethod
    def for_job(cls, job: CoverJob) -> Self:
        return cls.for_coordinates(job.user_id, job.course_id, job.id)

    @classmethod
    def for_coordinates(cls, user_id: str, course_id: str, job_id: str) -> Self:
        """The paths for any (owner, course, job) — the coordinates are all the convention needs."""
        prefix = f"{user_id}/{course_id}/{job_id}"
        return cls(
            image=f"{prefix}/cover.png",
            image_light=f"{prefix}/cover-light.png",
            provenance=f"{prefix}/provenance.json",
        )
