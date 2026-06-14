from typing import Protocol

from lunaris_runtime.schema import VideoJob

from lunaris_video.schemas import VideoContract


class IPriorContractProvider(Protocol):
    """Loads the scene contract a regenerate job re-renders (explainer-video V6-T2).

    A ``RETRY`` / ``ADD_NARRATION`` regenerate reuses the prior job's planned contract instead of
    re-planning — so the same storyboard renders again (Stage 2+), only narration / render output
    differing. The new job carries the source's contract storage path on ``config["regenerate"]``;
    the implementation downloads + parses it. Returns ``None`` when there is no prior contract to
    reuse (not a regenerate, no path, or the artifact is missing / unreadable), so the pipeline
    falls back to a fresh plan rather than failing.
    """

    async def load(self, job: VideoJob) -> VideoContract | None: ...
