"""The close is a ceremony, not a sentence (Lunaris Live, Phase 2c, T5).

Plan §6: "Sessions run 25 to 40 minutes and end deliberately: recap, mastery delta shown to the
learner …". P2a's close was a fixed sentence plus the director's reason and a mastery meter of what
was demonstrated. This makes it: a **recap** in the tutor's words over what was covered and how it
went (with a deterministic sentence when the tutor cannot speak — a close must never fail on its
own ceremony), and a **mastery delta**: the meter shows each concept's recall beside what it was
when the session opened, so a learner sees movement, not a number.

What is deterministic stays deterministic (R4): the delta is arithmetic over the beliefs the row
recorded at open and the beliefs now; only the recap's words are the tutor's.
"""

from collections.abc import Sequence

from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import (
    Covered,
    CoveredOutcome,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    StubGrader,
    StubTutor,
    TutorUnavailableError,
    apply_evidence,
    open_session,
    take_turn,
)


def _graph() -> ConceptGraph:
    def node(node_id: str, name: str, *requires: str) -> ConceptNode:
        return ConceptNode(
            id=node_id,
            name=name,
            definition=f"The idea {name}.",
            requires=list(requires),
            mastery_criteria=[
                MasteryCriterion(kind=MasteryCriterionKind.EXPLAIN, statement=f"Explain {name}.")
            ],
        )

    return ConceptGraph(
        graph_id="g1",
        topic="Bayes' theorem",
        nodes=[
            node("prior", "Prior"),
            node("update", "Update", "prior"),
            node("odds", "Odds", "update"),
        ],
        topo_order=["prior", "update", "odds"],
        is_acyclic=True,
    )


class RecapSpy(StubTutor):
    """The stub tutor, recording what it was asked to recap, and saying something findable."""

    def __init__(self) -> None:
        self.briefs: list[tuple[str, tuple[Covered, ...], str | None]] = []

    async def recap(
        self, topic: str, covered: Sequence[Covered], *, profile: str | None = None, run_id: str
    ) -> str:
        self.briefs.append((topic, tuple(covered), profile))
        return "Here is where you got to today."


class MuteRecap(StubTutor):
    async def recap(
        self, topic: str, covered: Sequence[Covered], *, profile: str | None = None, run_id: str
    ) -> str:
        raise TutorUnavailableError("provider is down")


_BUDGET_S = 100.0


async def _opened(tutor: StubTutor, model: LearnerModel | None = None) -> Session:
    outcome = await open_session(
        _graph(),
        model or LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id="s1",
        run_id="r1",
        tutor=tutor,
    )
    return outcome.session


async def _answered(
    session: Session, tutor: StubTutor, *, answer: str, elapsed_s: float, model=None
):
    return await take_turn(
        session,
        _graph(),
        model or LearnerModel(graph_id="g1"),
        answer=answer,
        answering_seq=session.turns[-1].seq,
        grader=StubGrader(),
        tutor=tutor,
        run_id=f"r{len(session.turns) + 1}",
        elapsed_s=elapsed_s,
        budget_s=_BUDGET_S,
    )


# ── the recap ───────────────────────────────────────────────────────────────────────────────────


async def test_the_close_speaks_the_tutors_recap_over_what_was_covered() -> None:
    tutor = RecapSpy()
    session = await _opened(tutor)
    # One MET on the root (the criterion restated), then the clock runs out.
    met = await _answered(session, tutor, answer="Explain Prior. Explain Prior.", elapsed_s=10.0)
    closed = await _answered(
        met.session,
        tutor,
        answer="Explain Prior. Explain Prior.",
        elapsed_s=_BUDGET_S + 1,
        model=met.model,
    )

    goodbye = closed.session.turns[-1]
    assert closed.session.status is SessionStatus.CLOSED
    assert goodbye.move.kind is MoveKind.CLOSE
    assert "Here is where you got to today." in goodbye.tutor
    # The director's reason still rides the goodbye: the learner is owed the trace's explanation.
    assert goodbye.move.reason in goodbye.tutor
    # The tutor was briefed with what was covered and how it went, pinned by value.
    ((topic, covered, _),) = tutor.briefs
    assert topic == "Bayes' theorem"
    assert [(c.node_id, c.outcome) for c in covered] == [("prior", CoveredOutcome.DEMONSTRATED)]
    assert covered[0].evidence_count == 2


async def test_a_concept_met_but_not_yet_held_is_recapped_as_still_forming() -> None:
    tutor = RecapSpy()
    session = await _opened(tutor)
    missed = await _answered(session, tutor, answer="No idea at all.", elapsed_s=10.0)
    closed = await _answered(
        missed.session, tutor, answer="Still no.", elapsed_s=_BUDGET_S + 1, model=missed.model
    )

    ((_, covered, _),) = tutor.briefs
    assert [(c.concept, c.outcome) for c in covered] == [("Prior", CoveredOutcome.FORMING)]
    assert closed.session.status is SessionStatus.CLOSED


async def test_a_recap_that_cannot_be_written_never_fails_the_close() -> None:
    """The ceremony is owed; the words are a nicety. A provider down at the last minute gets a
    plain sentence naming what was covered, and the session still ends properly."""
    tutor = MuteRecap()
    session = await _opened(tutor)
    met = await _answered(session, tutor, answer="Explain Prior. Explain Prior.", elapsed_s=10.0)

    closed = await _answered(
        met.session,
        tutor,
        answer="Explain Prior. Explain Prior.",
        elapsed_s=_BUDGET_S + 1,
        model=met.model,
    )

    goodbye = closed.session.turns[-1]
    assert closed.session.status is SessionStatus.CLOSED
    assert "Prior" in goodbye.tutor, "the fallback names what was covered"
    assert goodbye.move.reason in goodbye.tutor


async def test_the_recap_is_briefed_with_the_learners_profile_when_there_is_one() -> None:
    tutor = RecapSpy()
    session = (await _opened(tutor)).model_copy(update={"profile": "A nurse reading papers."})
    closed = await _answered(session, tutor, answer="Something.", elapsed_s=_BUDGET_S + 1)

    ((_, _, profile),) = tutor.briefs
    assert profile == "A nurse reading papers."
    assert closed.session.status is SessionStatus.CLOSED


# ── the mastery delta ───────────────────────────────────────────────────────────────────────────


async def test_the_session_records_the_beliefs_it_opened_with() -> None:
    """Stamped once at open, from what the learner already knew: the delta's zero line."""
    known = apply_evidence(LearnerModel(graph_id="g1"), "prior", EvidenceKind.MET, at_turn=1)
    known = apply_evidence(known, "prior", EvidenceKind.MET, at_turn=2)

    session = await _opened(StubTutor(), model=known)

    assert session.opening_beliefs == {"prior": known.nodes["prior"].estimate}


async def test_a_fresh_learner_opens_with_no_beliefs_recorded() -> None:
    session = await _opened(StubTutor())

    assert session.opening_beliefs == {}


async def test_the_close_meter_shows_where_each_concept_was_when_the_session_opened() -> None:
    """The delta the learner sees: recall now beside recall at open, per concept, from the row's
    own record — a returning learner who came in holding Prior at 0.7 and leaves at 0.9 is shown
    both, and a concept first met today shows it started from nothing."""
    tutor = StubTutor()
    known = apply_evidence(LearnerModel(graph_id="g1"), "prior", EvidenceKind.MET, at_turn=1)
    known = apply_evidence(known, "prior", EvidenceKind.MET, at_turn=2)
    opened_at = known.nodes["prior"].estimate
    session = await _opened(tutor, model=known)  # the director introduces "update" (prior held)
    met = await _answered(
        session, tutor, answer="Explain Update. Explain Update.", elapsed_s=10.0, model=known
    )
    closed = await _answered(
        met.session,
        tutor,
        answer="Explain Update. Explain Update.",
        elapsed_s=_BUDGET_S + 1,
        model=met.model,
    )

    meter = closed.session.turns[-1].surface
    assert meter is not None and meter.kind.value == "mastery_meter"
    by_id = {entry.node_id: entry for entry in meter.entries}
    assert by_id["prior"].recall_before == opened_at
    assert by_id["update"].recall_before is None, "first met today: nothing to have opened with"
    assert by_id["update"].recall > 0.0


async def test_the_zero_line_is_the_stamp_not_the_belief_now() -> None:
    """Review catch: with a concept touched again after open, ``recall_before`` must be what the row
    recorded, while ``recall`` moved. A meter recomputing "before" from the live model would show a
    zero delta on exactly the concept the learner came back to work on."""
    tutor = StubTutor()
    known = apply_evidence(LearnerModel(graph_id="g1"), "prior", EvidenceKind.MET, at_turn=1)
    opened_at = known.nodes["prior"].estimate  # one MET: prior is forming, so the director stays
    session = await _opened(tutor, model=known)
    assert session.turns[-1].move.node_id == "prior"
    met = await _answered(
        session, tutor, answer="Explain Prior. Explain Prior.", elapsed_s=10.0, model=known
    )
    closed = await _answered(
        met.session,
        tutor,
        answer="Explain Prior. Explain Prior.",
        elapsed_s=_BUDGET_S + 1,
        model=met.model,
    )

    (entry,) = [e for e in closed.session.turns[-1].surface.entries if e.node_id == "prior"]
    assert entry.recall_before == opened_at
    assert entry.recall > opened_at


async def test_a_claim_never_checked_is_not_on_the_meter() -> None:
    """Review catch: a credited claim (T3) has a belief but no evidence. Before the fix the meter
    listed it at its claim beside a recall of nothing, which read as the session having lost the
    learner ground they were merely never asked about. The meter is over what the grader moved."""
    from lunaris_live.session import NodePrior, seed_priors

    tutor = StubTutor()
    known = seed_priors(
        LearnerModel(graph_id="g1"),
        [NodePrior(node_id="odds", prior=0.8)],
    )
    session = await _opened(tutor, model=known)
    assert session.opening_beliefs == {"odds": 0.8}, "the claim is still the zero line"
    closed = await _answered(
        session, tutor, answer="Something.", elapsed_s=_BUDGET_S + 1, model=known
    )

    surface = closed.session.turns[-1].surface
    assert surface is not None
    assert "odds" not in {entry.node_id for entry in surface.entries}


def test_the_plain_recap_reads_right_over_more_than_one_opened_concept() -> None:
    """The fallback's grammar over the branch nothing else exercised: two concepts opened and not
    checked are "them", not "it", and the pick-up-first is the first of them."""
    from lunaris_live.session import recap_sentence

    said = recap_sentence(
        "Bayes' theorem",
        [
            Covered(
                node_id="update",
                concept="Update",
                outcome=CoveredOutcome.INTRODUCED,
                evidence_count=0,
            ),
            Covered(
                node_id="odds", concept="Odds", outcome=CoveredOutcome.INTRODUCED, evidence_count=0
            ),
        ],
    )

    assert "We opened Update and Odds and did not get to check them yet." in said
    assert said.endswith("Next time we pick up Update first.")
