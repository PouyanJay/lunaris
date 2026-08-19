"""Priors: what the placement interview says the learner already knows, and what the director does
about it (Lunaris Live, Phase 2c, T3).

A prior is a *claim*, never evidence (U2). It seeds a node with nothing demonstrated — the
estimate stays what evidence made it, which is nothing — and it changes exactly two things: which
concept the director treats as the frontier (a claimed chain is skipped), and how the boundary is
crossed (the deepest claimed prerequisite of the frontier is *retrieved and graded* before anything
past it is introduced). A verified claim becomes real evidence, starting from the prior; a claim
that does not hold is dropped and the concept is taught. Tier 2 also reads the claim: a learner
who says they know something is not handed a beginner's scaffold to prove it.
"""

from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import (
    DECAYED,
    MASTERED,
    EvidenceKind,
    LearnerModel,
    LessonParts,
    MemoryKnowledgeStore,
    MoveKind,
    NodeKnowledge,
    NodePrior,
    SessionClock,
    WorkedExample,
    apply_evidence,
    claim_of,
    compose_layout,
    decide_move,
    seed_priors,
)


def _chain() -> ConceptGraph:
    """a → b → c → d, each with something to check, so a verification can be staged."""

    def node(node_id: str, *requires: str) -> ConceptNode:
        return ConceptNode(
            id=node_id,
            name=node_id.upper(),
            definition=f"The idea {node_id}.",
            requires=list(requires),
            mastery_criteria=[
                MasteryCriterion(kind=MasteryCriterionKind.EXPLAIN, statement=f"Explain {node_id}.")
            ],
        )

    return ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[node("a"), node("b", "a"), node("c", "b"), node("d", "c")],
        topo_order=["a", "b", "c", "d"],
        is_acyclic=True,
    )


def _clock(turn: int = 1) -> SessionClock:
    return SessionClock(turn=turn, elapsed_s=0.0, budget_s=1800.0)


def _claimed(*node_ids: str, prior: float = 0.8) -> LearnerModel:
    return seed_priors(
        LearnerModel(graph_id="g1"), [NodePrior(node_id=n, prior=prior) for n in node_ids]
    )


# ── seeding ─────────────────────────────────────────────────────────────────────────────────────


def test_a_prior_seeds_a_claim_and_no_evidence() -> None:
    model = _claimed("a")

    known = model.nodes["a"]
    assert known.prior == 0.8
    assert known.estimate == 0.0, "a claim is not a belief: the estimate is what evidence made it"
    assert known.evidence_count == 0


def test_a_prior_never_overwrites_evidence() -> None:
    """A returning learner's second placement (or a re-mapped interview) must not erase what the
    grader has already established about a concept."""
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)
    before = model.nodes["a"]

    seeded = seed_priors(model, [NodePrior(node_id="a", prior=0.9)])

    assert seeded.nodes["a"].estimate == before.estimate
    assert seeded.nodes["a"].evidence_count == before.evidence_count
    assert seeded.nodes["a"].prior is None, "evidence outranks a claim; the claim is not kept"


def test_a_prior_survives_the_store() -> None:
    store = MemoryKnowledgeStore()
    store.save(_claimed("a"), owner_id="learner-1")

    assert store.load("g1", owner_id="learner-1").nodes["a"].prior == 0.8


# ── verifying ───────────────────────────────────────────────────────────────────────────────────


def test_a_met_verification_starts_the_belief_from_the_claim() -> None:
    """One MET on a claimed concept lands it demonstrated: that is what makes a claim worth
    checking rather than ignoring."""
    model = apply_evidence(_claimed("a"), "a", EvidenceKind.MET, at_turn=1)

    assert model.nodes["a"].estimate >= MASTERED
    assert model.nodes["a"].evidence_count == 1
    # The claim was settled by the evidence, and the row says so: it is not carried on.
    assert model.nodes["a"].prior is None


def test_a_verification_that_does_not_hold_starts_the_belief_from_nothing() -> None:
    """PARTIAL or NOT_MET on a claim drops the claim: the belief moves from zero, as it would for a
    concept never claimed, so a half-answer cannot ride a confident prior over the bar."""
    partial = apply_evidence(_claimed("a"), "a", EvidenceKind.PARTIAL, at_turn=1)
    missed = apply_evidence(_claimed("a"), "a", EvidenceKind.NOT_MET, at_turn=1)

    assert partial.nodes["a"].estimate < DECAYED
    assert missed.nodes["a"].estimate == 0.0


def test_a_hesitant_claim_does_not_buy_mastery_on_one_answer() -> None:
    """Found in review: a claim under the mastery bar credits nothing for the director, so its
    first evidence must start from nothing like any other — or a 0.4 claim plus one right answer
    would land at 0.67, mastered on turn one, which no un-claimed concept can do."""
    model = apply_evidence(_claimed("a", prior=0.4), "a", EvidenceKind.MET, at_turn=1)

    assert model.nodes["a"].estimate < MASTERED
    # Exactly what one MET from nothing gives (`_PULL`), pinned by value.
    unclaimed = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)
    assert model.nodes["a"].estimate == unclaimed.nodes["a"].estimate


def test_introducing_a_claimed_but_never_taught_concept_does_not_call_it_started() -> None:
    """Found in review: the INTRODUCE reason read "has been started" off the presence of a row, and
    a hesitant claim seeds a row. The trace must not say a concept was taught when it was not."""
    move = decide_move(_chain(), _claimed("a", prior=0.4), _clock())

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "a")
    assert "started" not in move.reason
    assert "next thing this map can teach" in move.reason


def test_a_claim_alone_never_counts_as_demonstrated() -> None:
    """Every node claimed and nothing checked must not close the session as exhausted, and must
    not introduce past the claims: it verifies."""
    move = decide_move(_chain(), _claimed("a", "b", "c", "d"), _clock())

    assert move.kind is MoveKind.RETRIEVE
    assert move.node_id == "d"


def test_a_row_carrying_both_evidence_and_a_claim_reads_as_evidence() -> None:
    """The writers keep the invariant (a claim is cleared by the first evidence, never seeded over
    it); the readers do not trust them. A row some writer got wrong is read as what it has been
    shown, not as what it says — pinned by constructing the invalid row directly."""
    wrong = NodeKnowledge(node_id="a", estimate=0.1, evidence_count=1, prior=0.9)

    assert claim_of(wrong) is None
    model = LearnerModel(graph_id="g1", nodes={"a": wrong})
    # Not credited (0.1 with evidence), so a is the frontier and is introduced, not skipped.
    assert (
        decide_move(_chain(), model, _clock()).kind,
        decide_move(_chain(), model, _clock()).node_id,
    ) == (
        MoveKind.INTRODUCE,
        "a",
    )


# ── the director's boundary ─────────────────────────────────────────────────────────────────────


def test_a_claimed_chain_is_skipped_to_its_boundary_and_the_deepest_claim_is_checked() -> None:
    """The learner claims a, b, c. The frontier is d; before d is introduced, c (the deepest
    claimed prerequisite, the one d stands on) is retrieved and graded."""
    move = decide_move(_chain(), _claimed("a", "b", "c"), _clock())

    assert (move.kind, move.node_id) == (MoveKind.RETRIEVE, "c")
    # In the trace's own voice (third person, like every other reason), naming the interview.
    assert "interview" in move.reason.lower()
    assert move.reason.startswith("C ")


def test_of_two_claims_the_frontier_stands_on_the_deeper_one_is_checked() -> None:
    """A diamond: c stands on BOTH a and b, both claimed. "Deepest" is the later in teaching order
    (b), not merely "the only one" — the chain fixture cannot tell `max` from `min` here, this can
    (found in review)."""
    diamond = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[
            _chain().nodes[0],
            _chain().nodes[1].model_copy(update={"requires": []}),
            _chain().nodes[2].model_copy(update={"requires": ["a", "b"]}),
        ],
        topo_order=["a", "b", "c"],
        is_acyclic=True,
    )

    move = decide_move(diamond, _claimed("a", "b"), _clock())

    assert (move.kind, move.node_id) == (MoveKind.RETRIEVE, "b")


def test_a_verified_boundary_opens_the_frontier() -> None:
    model = apply_evidence(_claimed("a", "b", "c"), "c", EvidenceKind.MET, at_turn=1)

    move = decide_move(_chain(), model, _clock(2))

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "d")


def test_a_boundary_that_does_not_hold_is_taught_after_its_own_boundary_is_checked() -> None:
    """c did not hold, so c is what to teach; but c stands on b, which is still only a claim, so b
    is checked first. The verification walks back down the chain until something holds."""
    model = apply_evidence(_claimed("a", "b", "c"), "c", EvidenceKind.NOT_MET, at_turn=1)

    move = decide_move(_chain(), model, _clock(2))

    assert (move.kind, move.node_id) == (MoveKind.RETRIEVE, "b")


def test_once_the_chain_below_holds_the_failed_claim_is_introduced() -> None:
    model = apply_evidence(_claimed("a", "b", "c"), "c", EvidenceKind.NOT_MET, at_turn=1)
    model = apply_evidence(model, "b", EvidenceKind.MET, at_turn=2)

    move = decide_move(_chain(), model, _clock(3))

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "c")


def test_a_claim_beneath_a_demonstrated_concept_is_vouched_for_and_not_checked() -> None:
    """Found by driving the real loop: after the top of a claimed chain held (MET), the director
    went on to verify the claims beneath it, one by one. A demonstrated concept is evidence for
    what it stands on. Here the map branches — c and d both stand on b — so that b, claimed and
    never checked, is *vouched for* by c holding: d is introduced without b being checked. Without
    vouching, b (the deepest claim d stands on) would be retrieved first."""
    branch = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[
            *_chain().nodes[:3],
            _chain().nodes[3].model_copy(update={"requires": ["b"]}),
        ],
        topo_order=["a", "b", "c", "d"],
        is_acyclic=True,
    )
    model = apply_evidence(_claimed("a", "b", "c"), "c", EvidenceKind.MET, at_turn=1)

    move = decide_move(branch, model, _clock(2))

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "d")


def test_when_everything_is_claimed_and_the_top_holds_the_map_is_done() -> None:
    """All four claimed, d verified: the chain beneath is vouched for, nothing is left to teach or
    to check, and the session closes as exhausted rather than walking back down the claims."""
    model = apply_evidence(_claimed("a", "b", "c", "d"), "d", EvidenceKind.MET, at_turn=1)

    move = decide_move(_chain(), model, _clock(2))

    assert move.kind is MoveKind.CLOSE


def test_a_prior_below_mastery_credits_nothing() -> None:
    """A4: a hesitant claim seeds Tier 2's band but skips nothing — the root is introduced."""
    move = decide_move(_chain(), _claimed("a", "b", prior=0.4), _clock())

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "a")


def test_a_claim_on_a_concept_whose_prerequisite_is_unclaimed_does_not_skip_it() -> None:
    """A claim on b alone: a is neither demonstrated nor claimed, so a is the frontier and there is
    nothing to verify beneath it. Claims do not let a learner skip over a hole."""
    move = decide_move(_chain(), _claimed("b"), _clock())

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "a")


# ── Tier 2 reads the claim ──────────────────────────────────────────────────────────────────────


def _parts() -> LessonParts:
    return LessonParts(
        worked_example=WorkedExample(title="Worked", steps=["one", "two"]),
        hint="A hint.",
        practice=["p1", "p2", "p3"],
    )


def test_a_confident_claim_gets_the_lean_layout_not_a_beginners_scaffold() -> None:
    claimed = compose_layout(_parts(), node_id="a", model=_claimed("a"))
    fresh = compose_layout(_parts(), node_id="a", model=LearnerModel(graph_id="g1"))

    assert claimed != fresh
    claimed_kinds = [block.component.value for block in claimed.blocks]
    fresh_kinds = [block.component.value for block in fresh.blocks]
    assert "WorkedExample" in fresh_kinds
    assert "WorkedExample" not in claimed_kinds
