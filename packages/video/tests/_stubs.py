"""Shared test doubles: the model invoke seams (text + vision) and a lesson-source provider.

The invoke stubs record every prompt they are sent (so parse-repair tests can assert repair-turn
content) and replay scripted replies, REPEATING the last reply once the script is exhausted — that
is what lets a single bad reply drive a "exhaust the repair budget" test without listing it N times.
"""

from lunaris_runtime.schema import VideoJob
from lunaris_video.models import LessonSource


class StubInvokeModel:
    def __init__(self, replies: list[str]) -> None:
        self.prompts: list[str] = []
        self._replies = replies

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        call_index = len(self.prompts) - 1
        return self._replies[min(call_index, len(self._replies) - 1)]


class StubVisionModel:
    """The vision seam's analog of StubInvokeModel — also records the frame batch per call."""

    def __init__(self, replies: list[str]) -> None:
        self.prompts: list[str] = []
        self.frame_batches: list[list[bytes]] = []
        self._replies = replies

    async def __call__(self, prompt: str, frames: list[bytes]) -> str:
        self.prompts.append(prompt)
        self.frame_batches.append(frames)
        call_index = len(self.prompts) - 1
        return self._replies[min(call_index, len(self._replies) - 1)]


_DEFAULT_PROSE = "Merge sort splits the array, sorts the halves, and merges."


class FakeLessonProvider:
    """An ``ILessonSourceProvider`` double returning a fixed merge-sort lesson — the pipeline
    tests' stand-in for the course store."""

    def __init__(self, prose: str = _DEFAULT_PROSE) -> None:
        self._prose = prose

    async def load(self, job: VideoJob) -> LessonSource:
        return LessonSource(
            course_topic="Algorithms",
            lesson_title="Merge sort",
            audience="first-year CS",
            prose=self._prose,
        )
