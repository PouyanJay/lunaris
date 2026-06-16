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
    captions: str
    provenance: str
    # Written at the source so finalize folds it into the lesson with a single storage read (V4-T1).
    artifact: str

    @classmethod
    def for_job(cls, job: VideoJob) -> Self:
        return cls.for_coordinates(job.user_id, job.course_id, job.id)

    @classmethod
    def for_coordinates(cls, user_id: str, course_id: str, job_id: str) -> Self:
        """The paths for any (owner, course, job) — the coordinates are all the convention needs.

        Lets a caller that holds another job's id (e.g. an upstream sibling video referenced from
        the course payload) derive that job's paths without reconstructing its whole ``VideoJob``.
        """
        prefix = f"{user_id}/{course_id}/{job_id}"
        return cls(
            mp4=f"{prefix}/final.mp4",
            poster=f"{prefix}/poster.jpg",
            contracts=f"{prefix}/scene_contracts.json",
            timing=f"{prefix}/timing.json",
            captions=f"{prefix}/captions.vtt",
            provenance=f"{prefix}/provenance.json",
            artifact=f"{prefix}/artifact.json",
        )
