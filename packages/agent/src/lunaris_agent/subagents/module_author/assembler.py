from lunaris_runtime.schema import (
    Claim,
    GagneFlags,
    Lesson,
    MerrillSegments,
    Segment,
)

from .lesson_draft import LessonDraft, SegmentDraft


class LessonAssembler:
    """Turns a LessonDraft into a validated course-object ``Lesson``.

    Deterministic: builds the four Merrill segments (claims become unverified
    ``Claim`` objects for the verifier), marks the Gagné events the Merrill cycle
    structurally covers, and estimates cognitive load from the content volume.
    """

    def assemble(self, draft: LessonDraft, *, lesson_id: str) -> Lesson:
        segments = MerrillSegments(
            activate=self._segment(draft.activate),
            demonstrate=self._segment(draft.demonstrate),
            apply=self._segment(draft.apply),
            integrate=self._segment(draft.integrate),
        )
        claim_total = sum(
            len(s.claims) for s in (draft.activate, draft.demonstrate, draft.apply, draft.integrate)
        )
        return Lesson(
            id=lesson_id,
            segments=segments,
            expects=list(draft.expects),
            self_check=list(draft.self_check),
            gagne=GagneFlags(
                gain_attention=True,
                state_objective=True,
                recall_prior=True,
                present_content=True,
                guide_learning=True,
                elicit_performance=True,
                provide_feedback=True,
                enhance_transfer=True,
            ),
            load_estimate=float(claim_total),
        )

    def _segment(self, draft: SegmentDraft) -> Segment:
        return Segment(
            prose=draft.prose,
            claims=[Claim(text=text) for text in draft.claims],
        )
