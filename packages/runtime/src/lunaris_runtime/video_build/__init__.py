"""The build's video lifecycle: enqueue lesson videos as modules clear, await them at finalize.

The seam between the course-build harness and the video-job queue (plan §V4): the author→verify→
revise loop enqueues a lesson's job the moment its module clears verification, and finalize awaits
the jobs before publishing (V4-T1). A run-scope ``ContextVar`` (sibling of ``credentials`` /
``run_config`` / ``device_bridge``) carries the coordinator into the run task; ``None`` means video
generation is off for the build, so the harness never re-derives the gate.
"""

from .coordinator_protocol import IVideoBuildCoordinator
from .input_hash import video_input_hash
from .queue_coordinator import QueueVideoBuildCoordinator
from .run_scope import resolve_video_coordinator, run_video_coordinator
from .video_lengths import target_seconds_for

__all__ = [
    "IVideoBuildCoordinator",
    "QueueVideoBuildCoordinator",
    "resolve_video_coordinator",
    "run_video_coordinator",
    "target_seconds_for",
    "video_input_hash",
]
