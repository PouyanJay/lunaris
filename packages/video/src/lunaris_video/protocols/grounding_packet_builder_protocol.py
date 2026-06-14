from collections.abc import Sequence
from typing import Protocol

from lunaris_runtime.schema import Course, CourseBrief, Lesson, Module

from lunaris_video.models import GroundingPacket


class IGroundingPacketBuilder(Protocol):
    """Builds the grounding packet a video plans against (cross-cutting principle 2).

    The packet is the verifier-PASSED facts of a course unit plus their source labels — the only
    facts the video may assert. One builder serves all three kinds: the lesson packet (V2) grounds a
    lesson in its claims; the summary packet (V5) grounds the course trailer in the designed
    curriculum; the overview packet (V5) grounds the topic intro in the brief's researched standard.
    """

    def build_lesson_packet(self, course: Course, lesson: Lesson) -> GroundingPacket: ...

    def build_summary_packet(self, *, topic: str, modules: Sequence[Module]) -> GroundingPacket: ...

    def build_overview_packet(self, brief: CourseBrief) -> GroundingPacket: ...
