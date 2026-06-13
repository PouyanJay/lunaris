from dataclasses import dataclass, field

from lunaris_video.models.grounding_packet import GroundingPacket
from lunaris_video.models.packet_kind import PacketKind


def _empty_lesson_packet() -> GroundingPacket:
    return GroundingPacket(kind=PacketKind.LESSON)


@dataclass(frozen=True)
class LessonSource:
    """What the PLAN node knows about a lesson — the pipeline-internal view of its inputs.

    Deliberately minimal and decoupled from the course payload's shape: the composition layer
    maps a real ``Lesson`` (module title, Merrill segment prose, learner audience) into this,
    so the planner never reaches into course internals. ``packet`` is the V2 grounding moat — the
    verifier-PASSED claims the video may assert; ``prose`` gives narrative framing only. It
    defaults to an empty packet so a source built without grounding is framing-only by construction.
    """

    course_topic: str
    lesson_title: str
    audience: str
    prose: str
    packet: GroundingPacket = field(default_factory=_empty_lesson_packet)

    def __post_init__(self) -> None:
        # A blank field here would surface later as a model hallucination (an empty lesson block
        # in the prompt), so construction is where it fails.
        for name in ("course_topic", "lesson_title", "audience", "prose"):
            if not getattr(self, name).strip():
                raise ValueError(f"LessonSource.{name} must not be blank")
