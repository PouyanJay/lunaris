from lunaris_runtime.schema import VideoJob

from lunaris_video.schemas import VideoContract


class NullPriorContractProvider:
    """The no-reuse ``IPriorContractProvider``: always ``None``, so a bare pipeline always plans
    (the composition root wires the storage-backed provider for the regenerate path)."""

    async def load(self, job: VideoJob) -> VideoContract | None:
        return None
