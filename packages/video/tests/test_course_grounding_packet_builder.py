"""CourseGroundingPacketBuilder: the moat a video grounds against, for all three packet kinds.

LESSON (V2-T0): a lesson's verifier-PASSED claims become a grounding packet — synthesized stable
claim ids, resolved ``supported_by`` citation labels, and every non-SUPPORTED claim
(CUT/REVISE/UNVERIFIED) excluded. SUMMARY (V5-T0): the course trailer grounds in the designed
curriculum (``course.modules``). OVERVIEW (V5-T0): the topic intro grounds in the ``CourseBrief`` +
its researched standard, and a source-less research grounds nothing. Nothing the verifier (or the
research) did not actually support may reach a scene (cross-cutting principle 2)."""

import pytest
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    Claim,
    Course,
    CourseBrief,
    Lesson,
    MerrillSegments,
    Module,
    Objective,
    ResearchSource,
    ResearchStatus,
    Segment,
    StandardResearch,
    TargetStandard,
    VerifierStatus,
)
from lunaris_video.grounding import CourseGroundingPacketBuilder
from lunaris_video.models import PacketKind

# --- LESSON (verifier-PASSED claims) ----------------------------------------------------------


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
    packet = CourseGroundingPacketBuilder().build_lesson_packet(course, lesson)

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
    packet = CourseGroundingPacketBuilder().build_lesson_packet(course, lesson)

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
    packet = CourseGroundingPacketBuilder().build_lesson_packet(course, lesson)

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
    packet = CourseGroundingPacketBuilder().build_lesson_packet(course, lesson)

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
    packet = CourseGroundingPacketBuilder().build_lesson_packet(course, lesson)

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
    packet = CourseGroundingPacketBuilder().build_lesson_packet(course, lesson)

    # Assert
    assert packet.kind is PacketKind.LESSON
    assert packet.claims == ()
    assert packet.is_empty


# --- SUMMARY (curriculum-grounded course trailer) ---------------------------------------------


def _modules() -> list[Module]:
    return [
        Module(
            id="m1",
            title="Foundations of Sorting",
            competency="reason about asymptotic cost",
            objectives=[
                Objective(statement="Explain Big-O", bloom_level=BloomLevel.UNDERSTAND, kc="a")
            ],
        ),
        Module(id="m2", title="Divide and Conquer", competency="apply merge sort"),
        Module(id="m3", title="Lower Bounds"),  # no competency
    ]


def test_summary_packet_grounds_in_the_curriculum() -> None:
    # Arrange
    modules = _modules()

    # Act
    packet = CourseGroundingPacketBuilder().build_summary_packet(
        topic="Algorithms", modules=modules
    )

    # Assert — a SUMMARY packet whose first claim is the exact, groundable module count (Gate C
    # diffs the trailer's "3 modules" against this verbatim), then one claim per module by title.
    assert packet.kind is PacketKind.SUMMARY
    assert packet.claims[0].text == "This course is organized into 3 modules."
    module_texts = " ".join(claim.text for claim in packet.claims[1:])
    assert "Foundations of Sorting" in module_texts
    assert "Divide and Conquer" in module_texts
    assert "Lower Bounds" in module_texts


def test_summary_module_claims_name_the_competency_when_present() -> None:
    # Act
    packet = CourseGroundingPacketBuilder().build_summary_packet(
        topic="Algorithms", modules=_modules()
    )

    # Assert — both branches of the module claim text: a module with a competency states it; one
    # without falls back to naming the title alone.
    assert "builds the competency" in packet.claims[1].text  # m1 has a competency
    assert "builds the competency" not in packet.claims[3].text  # m3 has none


def test_summary_packet_synthesizes_stable_ids_and_a_curriculum_source() -> None:
    # Act
    packet = CourseGroundingPacketBuilder().build_summary_packet(
        topic="Algorithms", modules=_modules()
    )

    # Assert — stable c1, c2, … ids (count claim + one per module) and the curriculum source label,
    # so the PLAN prompt can cite the structure the trailer narrates.
    assert [claim.id for claim in packet.claims] == ["c1", "c2", "c3", "c4"]
    assert all(claim.source_label == "course curriculum" for claim in packet.claims)


def test_summary_packet_for_a_course_with_no_modules_is_empty() -> None:
    # Act / Assert — a degenerate course with no curriculum grounds nothing (framing-only trailer).
    packet = CourseGroundingPacketBuilder().build_summary_packet(topic="Algorithms", modules=[])
    assert packet.kind is PacketKind.SUMMARY
    assert packet.is_empty


# --- OVERVIEW (brief + researched-standard intro) ---------------------------------------------


def _brief_with_research() -> CourseBrief:
    research = StandardResearch(
        status=ResearchStatus.COMPLETE,
        competencies=[
            "Listen to a 5-minute lecture and answer comprehension questions",
            "Write a 250-word argumentative essay",
        ],
        score_table=["CLB 10 requires a band score of 8.0 in each skill"],
        sources=[
            ResearchSource(
                url="https://ircc.canada.ca/clb",
                title="CLB 10 descriptors",
                fetched_at="2026-06-13T09:00:00+00:00",
            )
        ],
    )
    return CourseBrief(
        subject="English for IELTS",
        goal="reach CLB 10",
        target_standard=TargetStandard(name="CLB 10", authority_hint="ircc.canada.ca"),
        research=research,
    )


def test_overview_packet_grounds_in_competencies_and_score_thresholds() -> None:
    # Act
    packet = CourseGroundingPacketBuilder().build_overview_packet(_brief_with_research())

    # Assert — an OVERVIEW packet carrying the researched competencies AND the score-table line (the
    # figure "8.0" Gate C diffs the intro's narration against).
    assert packet.kind is PacketKind.OVERVIEW
    texts = [claim.text for claim in packet.claims]
    assert "Write a 250-word argumentative essay" in texts
    assert any("8.0" in text for text in texts)


def test_overview_packet_attributes_claims_to_the_researched_standard() -> None:
    # Act
    packet = CourseGroundingPacketBuilder().build_overview_packet(_brief_with_research())

    # Assert — claims name the standard and carry the auditable source url (provenance flows from
    # the research, never re-derived), with stable c1, c2, … ids.
    assert [claim.id for claim in packet.claims] == ["c1", "c2", "c3"]
    assert all(claim.source_label == "CLB 10" for claim in packet.claims)
    assert all(claim.citation_id == "https://ircc.canada.ca/clb" for claim in packet.claims)


def test_overview_packet_with_no_research_is_framing_only() -> None:
    # Act / Assert — a brief that skipped research (the no-key / non-research goal path) grounds
    # nothing; the intro must be framing-only.
    brief = CourseBrief(subject="Rhetoric", goal="argue persuasively")
    packet = CourseGroundingPacketBuilder().build_overview_packet(brief)
    assert packet.kind is PacketKind.OVERVIEW
    assert packet.is_empty


def test_overview_packet_ignores_ungrounded_research() -> None:
    # Arrange — research that found no usable source (UNAVAILABLE): its competencies came from the
    # model's memory, not a real source, so the moat must not let them reach a scene.
    brief = CourseBrief(
        subject="English",
        goal="reach CLB 10",
        research=StandardResearch(
            status=ResearchStatus.UNAVAILABLE,
            competencies=["An ungrounded competency from memory"],
        ),
    )

    # Act / Assert
    packet = CourseGroundingPacketBuilder().build_overview_packet(brief)
    assert packet.is_empty
