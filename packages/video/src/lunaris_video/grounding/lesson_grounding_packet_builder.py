import structlog
from lunaris_runtime.schema import Citation, Course, Lesson, Segment, VerifierStatus

from lunaris_video._merrill import SEGMENT_ORDER
from lunaris_video.models import GroundedClaim, GroundingPacket, PacketKind

_logger = structlog.get_logger(__name__)


class LessonGroundingPacketBuilder:
    """Turns a lesson's verifier-PASSED claims into a grounding packet (V2-T0).

    Walks the four Merrill segments in teaching order, keeps only ``SUPPORTED`` claims, assigns
    each a stable sequential id (the runtime ``Claim`` carries none), and resolves its
    ``supported_by`` against the course's ``provenance`` into a source label for the PLAN prompt.
    Only ``SUPPORTED`` claims reach the packet — anything the verifier left ``CUT``, ``REVISE`` or
    ``UNVERIFIED`` is filtered out, so a lesson whose claims were all cut yields an empty
    (framing-only) packet the planner must respect.
    """

    def build_lesson_packet(self, course: Course, lesson: Lesson) -> GroundingPacket:
        citations = {citation.id: citation for citation in course.provenance}
        grounded: list[GroundedClaim] = []
        for segment in self._segments_in_order(lesson):
            for claim in segment.claims:
                if claim.verifier_status is not VerifierStatus.SUPPORTED:
                    continue
                grounded.append(
                    GroundedClaim(
                        id=f"c{len(grounded) + 1}",
                        text=claim.text,
                        citation_id=claim.supported_by or "",
                        source_label=_source_label(claim.supported_by, citations),
                    )
                )
        packet = GroundingPacket(kind=PacketKind.LESSON, claims=tuple(grounded))
        _logger.info(
            "grounding_packet.built",
            lesson_id=lesson.id,
            kind=packet.kind.value,
            supported_claims=len(packet.claims),
        )
        return packet

    @staticmethod
    def _segments_in_order(lesson: Lesson) -> tuple[Segment, ...]:
        return tuple(getattr(lesson.segments, name) for name in SEGMENT_ORDER)


def _source_label(citation_id: str | None, citations: dict[str, Citation]) -> str:
    if not citation_id:
        return ""
    citation = citations.get(citation_id)
    if citation is None:
        # The claim's citation was dropped from the course after authoring — fall back to the bare
        # id so the PLAN prompt still names *a* source rather than a blank.
        return citation_id
    return citation.title or citation.url or citation.id
