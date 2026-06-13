from dataclasses import dataclass
from typing import Self

from lunaris_runtime.schema import VideoJob


@dataclass(frozen=True)
class VideoArtifactPaths:
    """Where a job's artifacts live in the course-videos bucket — the one path convention.

    ``{user_id}/{course_id}/{job_id}/…`` is load-bearing three ways: the storage RLS policy
    scopes reads to the first segment, course deletion is a prefix-delete on the first two, and
    the worker/API never have to exchange paths — both derive them from the job row.
    """

    mp4: str
    poster: str
    contracts: str
    timing: str

    @classmethod
    def for_job(cls, job: VideoJob) -> Self:
        prefix = f"{job.user_id}/{job.course_id}/{job.id}"
        return cls(
            mp4=f"{prefix}/final.mp4",
            poster=f"{prefix}/poster.jpg",
            contracts=f"{prefix}/scene_contracts.json",
            timing=f"{prefix}/timing.json",
        )
