"""The spaced schedule: a review ladder, shown at close, honoured by the next session (P2c T6).

Plan §6: sessions end with a schedule the learner can see ("come back Thursday for X, Y") and the
next session on the map honours it. Deterministic on purpose: at close each concept with evidence
gets a due date from a named-constant ladder keyed on how it stands (SM-2-lite: a demonstrated
concept's interval grows x2.5 per stage from one day; a forming one is due tomorrow and its ladder
restarts). This is a review ladder, not a forgetting curve — beliefs still do not decay across
sessions (AD6's trigger stays open) — so the only cross-session pull the director feels is "this
is due", which is what spaced retrieval spanning more than one sitting needs.
"""

from datetime import UTC, datetime, timedelta

import pytest
from _bayes_map import bayes_map, held
from lunaris_live.session import (
    LAST_RUNG,
    Covered,
    CoveredOutcome,
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    MemoryKnowledgeStore,
    MoveKind,
    NodeKnowledge,
    NodePrior,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    StubGrader,
    StubTutor,
    apply_evidence,
    decide_move,
    next_turn,
    open_session,
    recap_sentence,
    review_interval,
    schedule_reviews,
    seed_priors,
    take_turn,
)

_NOON = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)
_DAY = timedelta(days=1)
_BUDGET_S = 100.0


async def _closed_over(
    model: LearnerModel, *, answer: str, at: datetime = _NOON, tutor: StubTutor | None = None
):
    """Open at ``at``, answer once, and let the clock run out: the close's own outcome."""
    tutor = tutor or StubTutor()
    opened = await open_session(
        bayes_map(),
        model,
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S, at=at),
        session_id="s1",
        run_id="r1",
        tutor=tutor,
    )
    return await take_turn(
        opened.session,
        bayes_map(),
        opened.model,
        answer=answer,
        answering_seq=opened.session.turns[-1].seq,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r2",
        elapsed_s=_BUDGET_S + 1,
        budget_s=_BUDGET_S,
    )


# ── the ladder ──────────────────────────────────────────────────────────────────────────────────


def test_the_first_review_is_a_day_out_and_each_rung_is_further() -> None:
    assert review_interval(1) == _DAY
    assert review_interval(2) == _DAY * 2.5
    assert review_interval(3) == _DAY * 2.5 * 2.5


def test_a_rung_below_the_first_is_not_a_place_on_the_ladder() -> None:
    with pytest.raises(ValueError):
        review_interval(0)


def test_the_ladder_has_a_top_and_a_concept_held_there_stays_there() -> None:
    """Found in review: a geometric ladder with no top would, on a runaway writer, carry a rung
    past anything a date can hold. The top rung is a place; above it is not."""
    assert review_interval(LAST_RUNG) == _DAY * 2.5 ** (LAST_RUNG - 1)
    with pytest.raises(ValueError):
        review_interval(LAST_RUNG + 1)
    at_the_top = held(LearnerModel(graph_id="g1"), "prior", stage=LAST_RUNG, due_at=_NOON - _DAY)
    held_turn = SessionTurn(
        seq=1,
        move=DirectorMove(kind=MoveKind.RETRIEVE, node_id="prior", reason="Due."),
        tutor="Prior?",
        run_id="r1",
    )

    scheduled = schedule_reviews(at_the_top, bayes_map(), [held_turn], at=_NOON)

    assert scheduled.nodes["prior"].review_stage == LAST_RUNG
    assert scheduled.nodes["prior"].due_at == _NOON + review_interval(LAST_RUNG)


# ── scheduling at close ─────────────────────────────────────────────────────────────────────────


async def test_a_concept_demonstrated_today_is_due_tomorrow() -> None:
    """The close writes the schedule: a MET verification of a held root (one answer lands it,
    the claim rule aside — here two METs already hold it) is due back in a day, on rung one."""
    known = held(LearnerModel(graph_id="g1"), "prior")  # the director moves on to Update

    closed = await _closed_over(known, answer="Explain Update. Explain Update.")

    assert closed.session.status is SessionStatus.CLOSED
    # Update was MET once from nothing: forming, so due tomorrow on rung zero.
    update = closed.model.nodes["update"]
    assert update.due_at == _NOON + timedelta(seconds=_BUDGET_S + 1) + _DAY
    assert update.review_stage == 0


async def test_a_concept_held_at_the_close_climbs_a_rung() -> None:
    """Prior was checked (a due review, say) and held: its next review is further out."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)

    closed = await _closed_over(known, answer="Explain Prior. Explain Prior.")

    assert closed.session.turns[0].move.node_id == "prior", "the due review was what was asked"
    prior = closed.model.nodes["prior"]
    assert prior.review_stage == 2
    assert prior.due_at == closed.session.started_at + timedelta(seconds=_BUDGET_S + 1) + _DAY * 2.5


async def test_a_concept_that_slipped_restarts_its_ladder() -> None:
    """A demonstrated concept on rung three, missed twice at its review, is forming again: due
    tomorrow, from the bottom. The ladder is a record of what held, not of what was once held."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=3, due_at=_NOON - _DAY)
    tutor = StubTutor()
    opened = await open_session(
        bayes_map(),
        known,
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S, at=_NOON),
        session_id="s1",
        run_id="r1",
        tutor=tutor,
    )
    missed = await take_turn(
        opened.session,
        bayes_map(),
        opened.model,
        answer="No idea.",
        answering_seq=1,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r2",
        elapsed_s=10.0,
        budget_s=_BUDGET_S,
    )
    closed = await take_turn(
        missed.session,
        bayes_map(),
        missed.model,
        answer="Still no.",
        answering_seq=missed.session.turns[-1].seq,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r3",
        elapsed_s=_BUDGET_S + 1,
        budget_s=_BUDGET_S,
    )

    prior = closed.model.nodes["prior"]
    assert prior.estimate < 0.6, "two misses from 0.6975 leave it under the bar"
    assert prior.review_stage == 0
    assert prior.due_at == _NOON + timedelta(seconds=_BUDGET_S + 1) + _DAY


def test_a_concept_only_introduced_is_not_scheduled() -> None:
    """Nothing was graded, so there is nothing to space: the concept is picked up next time by the
    frontier, not by a review. (Directly, because every answer the loop takes is graded: the case
    is a turn that asked nothing — a concept with no criterion, an interview.)"""
    introduced = SessionTurn(
        seq=1,
        move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="prior", reason="Root."),
        tutor="Prior is…",
        run_id="r1",
    )
    # A row with no evidence: a hesitant claim from the interview (T3), so the concept HAS a row
    # to schedule on and the rule has to decline on the outcome, not on the row's absence.
    claimed = seed_priors(LearnerModel(graph_id="g1"), [NodePrior(node_id="prior", prior=0.3)])

    scheduled = schedule_reviews(claimed, bayes_map(), [introduced], at=_NOON)

    assert scheduled.nodes["prior"].due_at is None
    assert scheduled.nodes["prior"].review_stage == 0


async def test_a_concept_untouched_this_session_keeps_its_date() -> None:
    """Prior's review is next week; a session that works on Update and never comes near Prior
    must not move it."""
    next_week = _NOON + 7 * _DAY
    known = held(LearnerModel(graph_id="g1"), "prior", stage=2, due_at=next_week)

    closed = await _closed_over(known, answer="Explain Update. Explain Update.")

    assert closed.session.turns[0].move.node_id == "update", "the session was about Update"
    assert closed.model.nodes["prior"].due_at == next_week
    assert closed.model.nodes["prior"].review_stage == 2


def test_answering_a_review_moves_its_date_to_tomorrow_until_the_close_sets_the_real_one() -> None:
    """A review answered is no longer due — or the director would ask it again on the very next
    turn, and the next, until the close. Provisionally tomorrow rather than cleared (found in
    review): a session that never closes must not drop the concept off the ladder for good. The
    rung is kept: it is the close's input."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=2, due_at=_NOON - _DAY)

    answered = apply_evidence(known, "prior", EvidenceKind.MET, at_turn=3, on=_NOON)

    assert answered.nodes["prior"].due_at == _NOON + _DAY
    assert answered.nodes["prior"].review_stage == 2


def test_evidence_with_no_day_leaves_no_date() -> None:
    """A replay has no wall time; a date invented from nothing would be a date read as real."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=2, due_at=_NOON - _DAY)

    assert apply_evidence(known, "prior", EvidenceKind.MET, at_turn=3).nodes["prior"].due_at is None


async def test_a_review_answered_is_not_asked_again_on_the_next_turn() -> None:
    """The loop, end to end: the due review is asked, answered, and the next move is not the same
    review — the date moved, and the director reads the moved date."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)
    tutor = StubTutor()
    opened = await open_session(
        bayes_map(),
        known,
        SessionClock(turn=1, elapsed_s=0.0, budget_s=1800.0, at=_NOON),
        session_id="s1",
        run_id="r1",
        tutor=tutor,
    )
    assert opened.session.turns[0].move.node_id == "prior"

    answered = await take_turn(
        opened.session,
        bayes_map(),
        opened.model,
        answer="Explain Prior. Explain Prior.",
        answering_seq=1,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r2",
        elapsed_s=10.0,
        budget_s=1800.0,
    )

    assert answered.session.turns[-1].move.node_id != "prior"
    # And a session abandoned here has left the concept due tomorrow, not lost.
    assert answered.model.nodes["prior"].due_at == _NOON + timedelta(seconds=10.0) + _DAY


# ── shown at close ──────────────────────────────────────────────────────────────────────────────


async def test_the_close_meter_says_when_each_concept_is_due() -> None:
    known = held(LearnerModel(graph_id="g1"), "prior")

    closed = await _closed_over(known, answer="Explain Update. Explain Update.")

    meter = closed.session.turns[-1].surface
    by_id = {entry.node_id: entry for entry in meter.entries}
    assert by_id["update"].due_at == closed.model.nodes["update"].due_at
    assert by_id["update"].due_at is not None


class PassthroughRecapSpy(StubTutor):
    """The stub's own recap, with what it was briefed kept for the test to read."""

    def __init__(self) -> None:
        self.covered: list[Covered] = []

    async def recap(self, topic, covered, *, profile=None, run_id):  # type: ignore[override]
        self.covered = list(covered)
        return await super().recap(topic, covered, profile=profile, run_id=run_id)


async def test_the_recap_is_briefed_with_the_schedule() -> None:
    """So the tutor's words can name the day, and the plain sentence does when the tutor cannot."""
    tutor = PassthroughRecapSpy()
    known = held(LearnerModel(graph_id="g1"), "prior")

    closed = await _closed_over(known, answer="Explain Update. Explain Update.", tutor=tutor)

    (update,) = [c for c in tutor.covered if c.node_id == "update"]
    assert update.due_at == closed.model.nodes["update"].due_at


def test_the_plain_recap_names_the_day_of_the_first_review() -> None:
    thursday = datetime(2026, 8, 20, 12, 5, tzinfo=UTC)
    said = recap_sentence(
        "Bayes' theorem",
        [
            Covered(
                node_id="prior",
                concept="Prior",
                outcome=CoveredOutcome.DEMONSTRATED,
                evidence_count=2,
                due_at=thursday + 2 * _DAY,
            ),
            Covered(
                node_id="update",
                concept="Update",
                outcome=CoveredOutcome.FORMING,
                evidence_count=1,
                due_at=thursday,
            ),
        ],
    )

    assert "Thursday 20 August" in said
    on_the_day = said.split("Thursday 20 August")[1]
    assert "Update" in on_the_day, "the day names what is due on it"
    assert "Prior" not in on_the_day, "and not what is due later"


# ── honoured by the next session ────────────────────────────────────────────────────────────────


def _clock_at(at: datetime | None) -> SessionClock:
    return SessionClock(turn=1, elapsed_s=0.0, budget_s=1800.0, at=at)


def test_a_review_that_has_come_due_is_retrieved_before_anything_new() -> None:
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)

    move = decide_move(bayes_map(), known, _clock_at(_NOON))

    assert (move.kind, move.node_id) == (MoveKind.RETRIEVE, "prior")
    assert "due" in move.reason


def test_the_reason_says_whether_the_due_concept_was_held_or_still_forming() -> None:
    """The trace is read by a human (found in review): a concept at the bottom of the ladder was
    not "held when a session last closed", and the reason must not say it was."""
    holding = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)
    forming = apply_evidence(LearnerModel(graph_id="g1"), "prior", EvidenceKind.NOT_MET, at_turn=1)
    forming = forming.model_copy(
        update={"nodes": {"prior": forming.nodes["prior"].model_copy(update={"due_at": _NOON})}}
    )

    assert "was held" in decide_move(bayes_map(), holding, _clock_at(_NOON)).reason
    reason = decide_move(bayes_map(), forming, _clock_at(_NOON)).reason
    assert "still forming" in reason and "was held" not in reason


def test_a_review_not_yet_due_does_not_interrupt() -> None:
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON + _DAY)

    move = decide_move(bayes_map(), known, _clock_at(_NOON))

    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "update")


def test_a_review_due_this_very_minute_counts_as_due() -> None:
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON)

    assert decide_move(bayes_map(), known, _clock_at(_NOON)).kind is MoveKind.RETRIEVE


def test_of_two_due_reviews_the_longer_overdue_comes_first() -> None:
    """Deterministic, and by lateness rather than by teaching order: Update, two days late,
    before Prior, one day late — the ladder is what put them there."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)
    known = held(known, "update", stage=1, due_at=_NOON - 2 * _DAY)

    move = decide_move(bayes_map(), known, _clock_at(_NOON))

    assert (move.kind, move.node_id) == (MoveKind.RETRIEVE, "update")


def test_a_due_review_waits_for_a_stuck_learner() -> None:
    """The order of concerns holds: a learner failing Update twice running is not walked away from
    to review Prior."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)
    for turn in (3, 4):
        known = apply_evidence(known, "update", EvidenceKind.NOT_MET, at_turn=turn)

    move = decide_move(
        bayes_map(), known, SessionClock(turn=5, elapsed_s=60.0, budget_s=1800.0, at=_NOON)
    )

    assert (move.kind, move.node_id) == (MoveKind.REMEDIATE, "update")


def test_nothing_is_due_when_the_turn_has_no_wall_time() -> None:
    """A clock without a wall time (a replay, the prediction) judges no review due: the ladder is
    read against a day, and there is no day to read it against."""
    known = held(LearnerModel(graph_id="g1"), "prior", stage=1, due_at=_NOON - _DAY)

    assert decide_move(bayes_map(), known, _clock_at(None)).kind is MoveKind.INTRODUCE


async def test_a_session_opened_after_a_review_is_due_asks_it_first() -> None:
    """T6's acceptance, end to end in the package: a concept MET on day 0 is due on day 1, and a
    session opened on day 1 retrieves it before introducing anything."""
    day0 = held(LearnerModel(graph_id="g1"), "prior")
    closed = await _closed_over(day0, answer="Explain Update. Explain Update.", at=_NOON)
    due = closed.model.nodes["update"].due_at
    assert due is not None

    later = await open_session(
        bayes_map(),
        closed.model,
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S, at=due),
        session_id="s2",
        run_id="r3",
        tutor=StubTutor(),
    )

    first = later.session.turns[0]
    assert (first.move.kind, first.move.node_id) == (MoveKind.RETRIEVE, "update")
    assert later.session.started_at == due, "a session opened at a wall time starts then"


async def test_a_session_opened_with_no_wall_time_starts_now() -> None:
    before = datetime.now(UTC)
    opened = await open_session(
        bayes_map(),
        LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )
    assert before <= opened.session.started_at <= datetime.now(UTC)


async def test_a_turn_handed_no_wall_time_reads_the_day_off_the_sessions_own_record() -> None:
    """The one derivation (AD21): a caller that builds a bare clock — a placement's first
    teaching turn does — still closes with a schedule, dated from the session's start plus the
    seconds since, so no turn ever reads a wall clock of its own."""
    known = held(LearnerModel(graph_id="g1"), "prior")
    answered = SessionTurn(
        seq=1,
        move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="update", reason="Next."),
        tutor="Update is…",
        run_id="r1",
        answer="Explain Update.",
    )
    known = apply_evidence(known, "update", EvidenceKind.MET, at_turn=1)
    session = Session(
        session_id="s1",
        graph_id="g1",
        status=SessionStatus.ACTIVE,
        started_at=_NOON,
        turns=[answered],
    )

    outcome = await next_turn(
        session,
        bayes_map(),
        known,
        [answered],
        clock=SessionClock(turn=2, elapsed_s=_BUDGET_S + 1, budget_s=_BUDGET_S),
        tutor=StubTutor(),
        run_id="r2",
    )

    assert outcome.session.status is SessionStatus.CLOSED
    assert outcome.model.nodes["update"].due_at == _NOON + timedelta(seconds=_BUDGET_S + 1) + _DAY


# ── the store ───────────────────────────────────────────────────────────────────────────────────


def test_the_schedule_survives_the_store() -> None:
    store = MemoryKnowledgeStore()
    store.save(held(LearnerModel(graph_id="g1"), "prior", stage=2, due_at=_NOON), owner_id="u1")

    known = store.load("g1", owner_id="u1").nodes["prior"]
    assert (known.review_stage, known.due_at) == (2, _NOON)


def test_a_knowledge_row_round_trips_its_schedule_through_the_wire_shape() -> None:
    original = NodeKnowledge(
        node_id="a",
        estimate=0.7,
        evidence_count=2,
        last_evidence_turn=2,
        review_stage=2,
        due_at=_NOON,
    )

    restored = NodeKnowledge.model_validate(original.model_dump(mode="json", by_alias=True))

    assert restored == original


def test_a_row_written_before_the_schedule_existed_reads_as_unscheduled() -> None:
    known = NodeKnowledge.model_validate(
        {"nodeId": "a", "estimate": 0.7, "evidenceCount": 2, "lastEvidenceTurn": 2}
    )
    assert (known.review_stage, known.due_at) == (0, None)


class FakeSupabase:
    """The slice of supabase-py the knowledge store uses, recording the rows it was handed."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self._filters: dict = {}

    def table(self, _name: str) -> "FakeSupabase":
        self._filters = {}
        return self

    def select(self, *_columns: str) -> "FakeSupabase":
        return self

    def upsert(self, rows: list[dict], *, on_conflict: str) -> "FakeSupabase":
        self.rows.extend(rows)
        return self

    def eq(self, column: str, value: object) -> "FakeSupabase":
        self._filters[column] = value
        return self

    def is_(self, column: str, value: object) -> "FakeSupabase":
        self._filters[column] = value
        return self

    def execute(self):
        import types

        matching = [
            row for row in self.rows if all(row.get(k) == v for k, v in self._filters.items())
        ]
        return types.SimpleNamespace(data=matching)


def test_the_durable_store_writes_the_schedule_and_reads_it_back() -> None:
    from lunaris_live.session import SupabaseKnowledgeStore

    client = FakeSupabase()
    store = SupabaseKnowledgeStore(client=client)
    store.save(held(LearnerModel(graph_id="g1"), "prior", stage=2, due_at=_NOON), owner_id="u1")

    (row,) = client.rows
    assert row["review_stage"] == 2
    assert row["due_at"] == "2026-08-19T12:00:00+00:00", "ISO 8601, as timestamptz reads it"
    known = store.load("g1", owner_id="u1").nodes["prior"]
    assert (known.review_stage, known.due_at) == (2, _NOON)


def test_the_durable_store_reads_a_row_from_before_the_schedule() -> None:
    from lunaris_live.session import SupabaseKnowledgeStore

    client = FakeSupabase()
    client.rows = [
        {
            "user_id": "u1",
            "graph_id": "g1",
            "node_id": "prior",
            "estimate": 0.7,
            "evidence_count": 2,
            "last_evidence_turn": 2,
        }
    ]
    known = SupabaseKnowledgeStore(client=client).load("g1", owner_id="u1").nodes["prior"]
    assert (known.review_stage, known.due_at) == (0, None)
