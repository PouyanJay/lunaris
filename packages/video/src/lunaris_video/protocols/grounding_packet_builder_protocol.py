from typing import Protocol

from lunaris_runtime.schema import Course, Lesson

from lunaris_video.models import GroundingPacket


class IGroundingPacketBuilder(Protocol):
    """Builds the grounding packet a video plans against (cross-cutting principle 2).

    The packet is the verifier-PASSED claims of a course unit plus their citation labels — the
    only facts the video may assert. The lesson builder ships in V2; the summary (curriculum) and
    overview (brief + standard) builders arrive in V5 against the same packet shape.
    """

    def build_lesson_packet(self, course: Course, lesson: Lesson) -> GroundingPacket: ...
