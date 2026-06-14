from collections.abc import Sequence
from itertools import chain

import structlog
from lunaris_runtime.schema import (
    Citation,
    Course,
    CourseBrief,
    Lesson,
    Module,
    Segment,
    StandardResearch,
    VerifierStatus,
)

from lunaris_video._merrill import SEGMENT_ORDER
from lunaris_video.models import GroundedClaim, GroundingPacket, PacketKind

_logger = structlog.get_logger(__name__)

# The source label for a summary trailer's claims: the curriculum the build designed is the moat the
# trailer grounds against — its own designed structure, not an external citation.
_CURRICULUM_SOURCE = "course curriculum"


class CourseGroundingPacketBuilder:
    """Builds the grounding packet a video plans against, for all three kinds (the protocol impl).

    Every packet carries only what a verified source supports (cross-cutting principle 2): the
    LESSON packet (V2-T0) is the lesson's verifier-PASSED claims; the SUMMARY packet (V5) grounds
    the course trailer in the designed curriculum; the OVERVIEW packet (V5) grounds the topic intro
    in the brief's researched standard. Each synthesizes stable sequential ids (``c1``, ``c2``, …)
    the planner cites and provenance records, and resolves a human source label for the PLAN prompt.
    """

    def build_lesson_packet(self, course: Course, lesson: Lesson) -> GroundingPacket:
        """A lesson's verifier-PASSED claims, in teaching order (V2-T0).

        Walks the four Merrill segments, keeps only ``SUPPORTED`` claims, assigns each a stable id,
        and resolves its ``supported_by`` against the course's ``provenance`` into a source label.
        Anything CUT/REVISE/UNVERIFIED is filtered out, so a fully-cut lesson yields an empty
        (framing-only) packet the planner must respect.
        """
        citations = {citation.id: citation for citation in course.provenance}
        grounded: list[GroundedClaim] = []
        for segment in self._segments_in_order(lesson):
            for claim in segment.claims:
                if claim.verifier_status is not VerifierStatus.SUPPORTED:
                    continue
                grounded.append(
                    GroundedClaim(
                        id=_next_id(grounded),
                        text=claim.text,
                        citation_id=claim.supported_by or "",
                        source_label=_source_label(claim.supported_by, citations),
                    )
                )
        return self._packet(PacketKind.LESSON, grounded, unit=lesson.id)

    def build_summary_packet(self, *, topic: str, modules: Sequence[Module]) -> GroundingPacket:
        """The course trailer's grounding: the designed curriculum (V5-T0).

        The trailer narrates the course "module by module", so the packet grounds the two things it
        states: the module count (the one citable figure Gate C checks the trailer's "N modules"
        against) and each module's title/competency. A course with no curriculum grounds nothing — a
        framing-only trailer. The source is the curriculum itself, not an external citation.
        """
        if not modules:
            return self._packet(PacketKind.SUMMARY, [], unit=topic)
        grounded: list[GroundedClaim] = []
        grounded.append(
            GroundedClaim(
                id=_next_id(grounded),
                text=f"This course is organized into {len(modules)} modules.",
                citation_id="",
                source_label=_CURRICULUM_SOURCE,
            )
        )
        for position, module in enumerate(modules, start=1):
            grounded.append(
                GroundedClaim(
                    id=_next_id(grounded),
                    text=_module_claim_text(position, module),
                    citation_id="",
                    source_label=_CURRICULUM_SOURCE,
                )
            )
        return self._packet(PacketKind.SUMMARY, grounded, unit=topic)

    def build_overview_packet(self, brief: CourseBrief) -> GroundingPacket:
        """The topic intro's grounding: the brief's researched standard (V5-T0).

        Grounds the intro in the standard's real competency descriptors and any score/threshold
        lines (the figures Gate C diffs the narration against), attributed to the researched source.
        Only a research that actually grounded against a source contributes — a ``None`` or
        source-less research (the no-key / non-research-goal path, whose competencies came from the
        model's memory) yields a framing-only packet, so the intro never asserts what the research
        did not prove.
        """
        research = brief.research
        if research is None or not research.sources:
            return self._packet(PacketKind.OVERVIEW, [], unit=brief.subject)
        source_label = _standard_source_label(brief, research)
        # Unlike a lesson claim's ``supported_by`` (a Course.provenance key), an overview claim's
        # source is the researched standard itself: ``citation_id`` carries the auditable source URL
        # directly — it is provenance metadata for the PLAN prompt, not a Course.provenance lookup.
        citation_id = research.sources[0].url
        grounded: list[GroundedClaim] = []
        for text in chain(research.competencies, research.score_table):
            grounded.append(
                GroundedClaim(
                    id=_next_id(grounded),
                    text=text,
                    citation_id=citation_id,
                    source_label=source_label,
                )
            )
        return self._packet(PacketKind.OVERVIEW, grounded, unit=brief.subject)

    @staticmethod
    def _segments_in_order(lesson: Lesson) -> tuple[Segment, ...]:
        return tuple(getattr(lesson.segments, name) for name in SEGMENT_ORDER)

    @staticmethod
    def _packet(kind: PacketKind, claims: list[GroundedClaim], *, unit: str) -> GroundingPacket:
        packet = GroundingPacket(kind=kind, claims=tuple(claims))
        _logger.info(
            "grounding_packet.built", unit=unit, kind=kind.value, claims=len(packet.claims)
        )
        return packet


def _next_id(grounded: list[GroundedClaim]) -> str:
    return f"c{len(grounded) + 1}"


def _module_claim_text(position: int, module: Module) -> str:
    if module.competency:
        return f"Module {position}, “{module.title}”, builds the competency: {module.competency}."
    return f"Module {position} is “{module.title}”."


def _standard_source_label(brief: CourseBrief, research: StandardResearch) -> str:
    # Prefer the named standard the competencies describe ("per CLB 10"); else the researched
    # source's own title or url. ``research.sources`` is non-empty here (the caller guards it).
    if brief.target_standard is not None and brief.target_standard.name:
        return brief.target_standard.name
    first = research.sources[0]
    return first.title or first.url


def _source_label(citation_id: str | None, citations: dict[str, Citation]) -> str:
    if not citation_id:
        return ""
    citation = citations.get(citation_id)
    if citation is None:
        # The claim's citation was dropped from the course after authoring — fall back to the bare
        # id so the PLAN prompt still names *a* source rather than a blank.
        return citation_id
    return citation.title or citation.url or citation.id
