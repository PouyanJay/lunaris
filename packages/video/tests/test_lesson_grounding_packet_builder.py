"""LessonGroundingPacketBuilder (V2-T0): a lesson's verifier-PASSED claims become a grounding
packet — synthesized stable claim ids, resolved ``supported_by`` citation labels, and every
non-SUPPORTED claim (CUT/REVISE/UNVERIFIED) excluded. This is the moat the video grounds against;
nothing the verifier did not pass may reach a scene (cross-cutting principle 2)."""

import pytest
from lunaris_runtime.schema import (
    Citation,
    Claim,
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VerifierStatus,
)
from lunaris_video.grounding import LessonGroundingPacketBuilder
from lunaris_video.models import PacketKind


def _supported(text: str, citation_id: str) -> Claim:
    return Claim(text=text, supported_by=citation_id, verifier_status=VerifierStatus.SUPPORTED)


def _cut(text: str) -> Claim:
    return Claim(text=text, supported_by=None, verifier_status=VerifierStatus.CUT)


def _course_with_claims() -> tuple[Course, Lesson]:
    segments = MerrillSegments(
        activate=Segment(
            prose="Merge sort is a divide-and-conquer sort.",
            claims=[_supported("Merge sort runs in O(n log n) time.", "cite-clrs")],
        ),
        demonstrate=Segment(
            prose="It splits the array in half repeatedly.",
            claims=[
                _supported("Each merge pass touches all n elements.", "cite-clrs"),
                _cut("Merge sort is the fastest sort ever invented."),  # excluded: CUT
            ],
        ),
        apply=Segment(prose="Trace the merge of two runs."),  # no claims
        integrate=Segment(
            prose="Where else does divide-and-conquer help?",
            claims=[_supported("Quicksort averages O(n log n) comparisons.", "cite-sedgewick")],
        ),
    )
    lesson = Lesson(id="lesson-1", segments=segments)
    module = Module(id="m1", title="Sorting", competency="sort efficiently", lessons=[lesson])
    course = Course(
        id="course-1",
        topic="Algorithms",
        scope_note="for CS undergrads",
        modules=[module],
        provenance=[
            Citation(
                id="cite-clrs", title="CLRS, Introduction to Algorithms", url="https://x/clrs"
            ),
            Citation(id="cite-sedgewick", title="Sedgewick, Algorithms"),
        ],
    )
    return course, lesson


def test_packet_holds_only_supported_claims_in_teaching_order() -> None:
    # Arrange
    course, lesson = _course_with_claims()

    # Act
    packet = LessonGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert — three SUPPORTED claims, in activate→demonstrate→apply→integrate order; the CUT one
    # ("fastest sort ever") and the claimless segment contribute nothing. The exact ordered list is
    # the whole assertion: the cut claim's absence is proven by its non-membership.
    assert packet.kind is PacketKind.LESSON
    assert [claim.text for claim in packet.claims] == [
        "Merge sort runs in O(n log n) time.",
        "Each merge pass touches all n elements.",
        "Quicksort averages O(n log n) comparisons.",
    ]


def test_packet_synthesizes_stable_sequential_claim_ids() -> None:
    # Arrange
    course, lesson = _course_with_claims()

    # Act
    packet = LessonGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert — Claim carries no id of its own, so the packet assigns c1, c2, … in teaching order.
    assert [claim.id for claim in packet.claims] == ["c1", "c2", "c3"]
    second = packet.by_id("c2")
    assert second is not None
    assert second.text == "Each merge pass touches all n elements."
    assert packet.by_id("nope") is None


def test_packet_resolves_supported_by_into_a_source_label() -> None:
    # Arrange
    course, lesson = _course_with_claims()

    # Act
    packet = LessonGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert — each grounded claim carries its citation id and a human label resolved from
    # Course.provenance (title preferred), so the PLAN prompt can name the source.
    by_id = {claim.id: claim for claim in packet.claims}
    assert by_id["c1"].citation_id == "cite-clrs"
    assert by_id["c1"].source_label == "CLRS, Introduction to Algorithms"
    assert by_id["c3"].citation_id == "cite-sedgewick"
    assert by_id["c3"].source_label == "Sedgewick, Algorithms"


@pytest.mark.parametrize(
    "excluded_status",
    [VerifierStatus.CUT, VerifierStatus.REVISE, VerifierStatus.UNVERIFIED],
)
def test_only_supported_claims_survive_every_other_verifier_status(
    excluded_status: VerifierStatus,
) -> None:
    # Arrange — one SUPPORTED claim alongside one in a non-supported state. Only SUPPORTED is the
    # verifier's "publishable" verdict, so CUT, REVISE and UNVERIFIED must all be filtered out.
    segments = MerrillSegments(
        activate=Segment(
            prose="Two claims, one verdict apart.",
            claims=[
                _supported("Merge sort runs in O(n log n) time.", "cite-clrs"),
                Claim(text="An unsettled assertion.", verifier_status=excluded_status),
            ],
        ),
        demonstrate=Segment(prose="More framing."),
        apply=Segment(prose="Practice."),
        integrate=Segment(prose="Reflect."),
    )
    lesson = Lesson(id="lesson-3", segments=segments)
    module = Module(id="m1", title="Sorting", lessons=[lesson])
    course = Course(id="course-3", topic="Algorithms", modules=[module])

    # Act
    packet = LessonGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert
    assert [claim.text for claim in packet.claims] == ["Merge sort runs in O(n log n) time."]


def test_a_claim_whose_citation_was_dropped_falls_back_to_the_bare_id() -> None:
    # Arrange — a SUPPORTED claim points at a citation id no longer in Course.provenance (it was
    # removed after authoring). The claim is still grounded; the label degrades, it does not vanish.
    segments = MerrillSegments(
        activate=Segment(
            prose="A grounded fact with an orphaned citation.",
            claims=[_supported("Heaps support O(log n) insertion.", "cite-gone")],
        ),
        demonstrate=Segment(prose="More framing."),
        apply=Segment(prose="Practice."),
        integrate=Segment(prose="Reflect."),
    )
    lesson = Lesson(id="lesson-4", segments=segments)
    module = Module(id="m1", title="Heaps", lessons=[lesson])
    course = Course(id="course-4", topic="Data structures", modules=[module], provenance=[])

    # Act
    packet = LessonGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert
    assert packet.claims[0].citation_id == "cite-gone"
    assert packet.claims[0].source_label == "cite-gone"


def test_a_lesson_with_no_supported_claims_yields_an_empty_packet() -> None:
    # Arrange — every claim CUT: a framing-only lesson. The packet is empty but valid; T4 proves
    # such a lesson still renders (asserting nothing) rather than failing.
    segments = MerrillSegments(
        activate=Segment(prose="A gentle intro.", claims=[_cut("An unproven boast.")]),
        demonstrate=Segment(prose="More framing."),
        apply=Segment(prose="Practice."),
        integrate=Segment(prose="Reflect."),
    )
    lesson = Lesson(id="lesson-2", segments=segments)
    module = Module(id="m1", title="Intro", lessons=[lesson])
    course = Course(id="course-2", topic="Rhetoric", modules=[module])

    # Act
    packet = LessonGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert
    assert packet.kind is PacketKind.LESSON
    assert packet.claims == ()
    assert packet.is_empty
