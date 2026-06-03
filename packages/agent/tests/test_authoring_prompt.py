"""P7.3-T1 — the personalized lesson-arc authoring prompt + its threading into the loop.

The arc is the model's job, so the end-to-end outcome is proven by the live eval; here we prove
deterministically the two things that DON'T need a model: ``build_authoring_prompt`` shapes the full
arc (expects → strategies → worked example → practice → self-check), personalizes it from the brief
(competency / level / frontier / requested voice), degrades to a generic arc without a brief, and
folds cut-claim feedback in for a revision; and the authoring loop threads the draft's brief +
frontier into the reviser so that personalization actually reaches the author.
"""

from collections.abc import Sequence

from langchain_core.messages import HumanMessage
from lunaris_agent.harness.authoring import build_authoring_subgraph
from lunaris_agent.harness.draft import CourseDraft
from lunaris_agent.subagents.module_author import LessonDraft, SegmentDraft, build_authoring_prompt
from lunaris_grounding import Evidence, StubEvidenceRetriever, StubSupportAssessor, Verifier
from lunaris_runtime.schema import (
    BloomLevel,
    Citation,
    CourseBrief,
    DetailDepth,
    LanguageStyle,
    Level,
    Module,
    Objective,
    Preferences,
)


def _module(*, competency: str | None = None) -> Module:
    return Module(
        id="m0",
        title="Listening for intent",
        kcs=["intent"],
        competency=competency,
        objectives=[
            Objective(
                statement="Given audio, the learner can analyze implied intent.",
                bloom_level=BloomLevel.ANALYZE,
                kc="intent",
            )
        ],
        difficulty_index=0.6,
    )


def _researched_brief() -> CourseBrief:
    return CourseBrief(
        subject="English language proficiency",
        goal="reach CLB 10",
        target_level=Level.ADVANCED,
        assumed_prior="strong everyday English (around CLB 8-9)",
        preferences=Preferences(
            detail_depth=DetailDepth.IN_DEPTH, language_style=LanguageStyle.SOPHISTICATED
        ),
    )


def test_build_authoring_prompt_shapes_the_full_arc() -> None:
    # Act — the plain (no-brief) prompt still shapes the whole arc, not a bare Merrill cycle.
    prompt = build_authoring_prompt(_module())

    # Assert — every arc step is asked for, and the JSON shape carries the two new bookends.
    lowered = prompt.lower()
    assert "expects" in lowered
    assert "worked example" in lowered
    assert "strategy" in lowered  # the demonstrate phase names the core strategy
    assert "practice" in lowered
    assert "self-check" in lowered or "self_check" in lowered
    assert '"expects"' in prompt
    assert '"self_check"' in prompt
    # The four Merrill phases remain (the parser requires them).
    for phase in ("activate", "demonstrate", "apply", "integrate"):
        assert f'"{phase}"' in prompt


def test_build_authoring_prompt_personalizes_from_a_researched_brief() -> None:
    # Arrange — a module mapped to a researched competency + a personalized brief + a frontier.
    module = _module(competency="hear implied intent in speech")
    brief = _researched_brief()
    frontier = ["everyday conversation", "core grammar"]

    # Act
    prompt = build_authoring_prompt(module, brief=brief, frontier=frontier)

    # Assert — the lesson is aimed at the competency, pitched at the level, scoped above the
    # frontier, and written in the requested register/depth.
    assert "hear implied intent in speech" in prompt
    assert "advanced" in prompt.lower()
    assert "everyday conversation" in prompt  # the frontier the arc must sit above
    assert "sophisticated" in prompt.lower()  # the requested register
    assert "in-depth" in prompt.lower() or "in_depth" in prompt.lower()


def test_build_authoring_prompt_is_generic_without_a_brief() -> None:
    # No brief / no module competency → the generic arc, no personalization sections leaking in.
    prompt = build_authoring_prompt(_module())

    assert "target level:" not in prompt.lower()  # no brief context section
    assert "register" not in prompt.lower()  # no voice line
    assert "builds toward the competency" not in prompt.lower()  # no module-competency line
    # …but the arc itself is still there.
    assert '"expects"' in prompt and '"self_check"' in prompt


def test_build_authoring_prompt_folds_in_cut_claim_revision_feedback() -> None:
    # Arrange — a revision pass: claims the verifier cut must be re-grounded, arc kept intact.
    cut = ["CLB 10 requires a 700-word essay.", "Intent is always explicit."]

    # Act
    prompt = build_authoring_prompt(_module(), cut_claims=cut)

    # Assert — the cut claims are listed with a re-author instruction that preserves the arc.
    assert "CLB 10 requires a 700-word essay." in prompt
    assert "Intent is always explicit." in prompt
    assert "cut" in prompt.lower()
    assert "keep the arc" in prompt.lower()
    # The arc JSON shape stays the FINAL instruction — the revision note is folded in before it, not
    # after, so the model still ends on "respond with this JSON".
    assert prompt.rstrip().endswith('"self_check": ["..."]}')
    assert prompt.index("were CUT") < prompt.index('"self_check": ["..."]}')


def _arc_lesson(module: Module) -> LessonDraft:
    """A groundable lesson draft (the marker word grounds it) carrying the arc bookends."""
    return LessonDraft(
        activate=SegmentDraft("Recall.", []),
        demonstrate=SegmentDraft("Worked example.", ["grounded fact"]),
        apply=SegmentDraft("Practice.", []),
        integrate=SegmentDraft("Transfer.", []),
        expects=[f"You can already follow {module.title}."],
        self_check=[f"Can you do {module.title} unaided?"],
    )


class _RecordingReviser:
    """An ILessonReviser that records the brief + frontier each call gets (and authors an arc).

    Both ``author`` and ``revise`` record, so either threading path can be asserted independently.
    """

    def __init__(self) -> None:
        self.author_briefs: list[CourseBrief | None] = []
        self.author_frontiers: list[list[str] | None] = []
        self.revise_briefs: list[CourseBrief | None] = []
        self.revise_frontiers: list[list[str] | None] = []

    async def author(
        self,
        module: Module,
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft:
        self.author_briefs.append(brief)
        self.author_frontiers.append(frontier)
        return _arc_lesson(module)

    async def revise(
        self,
        module: Module,
        cut_claims: Sequence[str],
        *,
        brief: CourseBrief | None = None,
        frontier: list[str] | None = None,
    ) -> LessonDraft:
        self.revise_briefs.append(brief)
        self.revise_frontiers.append(frontier)
        return _arc_lesson(module)


def _verifier(*, marker: str | None = None) -> Verifier:
    """Grounds claims containing ``marker`` (every claim when ``marker`` is None)."""

    def evidence(claim: str) -> list[Evidence]:
        if marker is not None and marker not in claim:
            return []
        return [Evidence(citation=Citation(id="src", snippet=claim), score=0.9)]

    return Verifier(StubEvidenceRetriever(evidence), StubSupportAssessor())


def _draft_to_author() -> CourseDraft:
    draft = CourseDraft(topic="Improve my English to CLB 10", course_id="c", run_id="r")
    draft.brief = _researched_brief()
    draft.frontier = ["everyday conversation"]
    draft.goal_concept = "intent"
    draft.modules = [_module(competency="hear implied intent in speech")]
    return draft


async def test_authoring_loop_threads_brief_and_frontier_into_the_author() -> None:
    # Arrange — a draft carrying a brief + frontier; every claim grounds, so no revision is needed.
    draft = _draft_to_author()
    reviser = _RecordingReviser()
    subgraph = build_authoring_subgraph(reviser, _verifier(), draft)

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — the loop passed the draft's brief + frontier to the author (so the prompt is tuned),
    # and never reached a revision.
    assert reviser.author_briefs == [draft.brief]
    assert reviser.author_frontiers == [draft.frontier]
    assert reviser.revise_briefs == []


async def test_authoring_loop_threads_brief_and_frontier_into_the_revision() -> None:
    # Arrange — the first-pass claim never grounds (no marker), so the loop must revise; that
    # revision must carry the same brief + frontier so personalization survives the revise pass.
    draft = _draft_to_author()
    reviser = _RecordingReviser()
    subgraph = build_authoring_subgraph(reviser, _verifier(marker="never-present-marker"), draft)

    # Act
    await subgraph.ainvoke({"messages": [HumanMessage(content="author")]})

    # Assert — the revision path was exercised and threaded the brief + frontier too.
    assert reviser.revise_briefs and reviser.revise_briefs[0] == draft.brief
    assert reviser.revise_frontiers[0] == draft.frontier
