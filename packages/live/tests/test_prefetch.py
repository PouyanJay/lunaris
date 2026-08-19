"""Per-node material, one node ahead (Lunaris Live, Phase 2c, T4).

Plan §6: Stage 2 materials are "generated on demand and prefetched one node ahead", so the runtime
is always ahead of the learner. Today the material is asked for *beside* the lesson with a grace,
and lost when it is late. This is the other half: a store of first-turn material per node, a pure
prediction of which node the director will pick next, and a loop that reads a node's first-turn
material from the store — no model call, no grace — when it is there, and falls back to today's
path when it is not. Later turns on a node (a remediation) always generate fresh: the P2a eval
showed the tutor coming at a stuck concept a different way each time is what worked.
"""

import types
from datetime import UTC, datetime

from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import (
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    LessonParts,
    MemoryMaterialStore,
    MoveKind,
    Session,
    SessionClock,
    SessionStatus,
    SessionTurn,
    StubGrader,
    StubTutor,
    WorkedExample,
    apply_evidence,
    next_turn,
    predict_next,
    take_turn,
)


def _graph() -> ConceptGraph:
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
        nodes=[node("a"), node("b", "a"), node("c", "b")],
        topo_order=["a", "b", "c"],
        is_acyclic=True,
    )


def _parts(title: str = "Prefetched") -> LessonParts:
    return LessonParts(
        worked_example=WorkedExample(title=title, steps=["one", "two"]),
        hint="A hint.",
        practice=["p1", "p2"],
    )


class CountingTutor(StubTutor):
    """The stub tutor, counting what it was asked to illustrate."""

    def __init__(self) -> None:
        self.illustrated: list[str] = []

    async def illustrate(
        self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
    ):  # type: ignore[override]
        self.illustrated.append(node.id)
        return await super().illustrate(
            move,
            node,
            topic=topic,
            criterion=criterion,
            already_said=already_said,
            profile=profile,
            run_id=run_id,
        )


def _session(*turns: SessionTurn) -> Session:
    return Session(
        session_id="s1",
        graph_id="g1",
        status=SessionStatus.ACTIVE,
        started_at=datetime(2026, 8, 19, 9, 0, tzinfo=UTC),
        turns=list(turns),
    )


def _clock(turn: int) -> SessionClock:
    return SessionClock(turn=turn, elapsed_s=0.0, budget_s=1800.0)


# ── predicting ──────────────────────────────────────────────────────────────────────────────────


def test_the_next_node_is_what_the_director_would_pick_if_the_current_one_held() -> None:
    """The prediction is the director's own answer to "and if this lands?": no second policy."""
    assert predict_next(_graph(), LearnerModel(graph_id="g1"), current="a") == "b"


def test_the_prediction_follows_the_map_not_the_current_node_alone() -> None:
    """With a demonstrated and b current, the next is c; the prediction reads the whole model."""
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)
    model = apply_evidence(model, "a", EvidenceKind.MET, at_turn=2)

    assert predict_next(_graph(), model, current="b") == "c"


def test_nothing_is_predicted_past_the_end_of_the_map() -> None:
    model = LearnerModel(graph_id="g1")
    for node_id in ("a", "b"):
        for turn in (1, 2):
            model = apply_evidence(model, node_id, EvidenceKind.MET, at_turn=turn)

    assert predict_next(_graph(), model, current="c") is None


def test_the_prediction_never_names_the_current_node() -> None:
    """A learner half-way through a concept is not "about to start it": what is prefetched is the
    node after, and a prediction that named the current node would prefetch material the turn on
    it already has."""
    assert predict_next(_graph(), LearnerModel(graph_id="g1"), current="a") != "a"


def test_nothing_is_predicted_for_a_concept_the_learner_has_already_met() -> None:
    """Found in review: with a demonstrated and b stuck (evidence, low belief), the director's next
    move after a is a REMEDIATE of b — a second pass, which by rule generates fresh material and
    never reads the store. Prefetching for it would be spend nothing ever reads."""
    model = LearnerModel(graph_id="g1")
    for turn in (1, 2):
        model = apply_evidence(model, "a", EvidenceKind.MET, at_turn=turn)
    for turn in (3, 4):
        model = apply_evidence(model, "b", EvidenceKind.NOT_MET, at_turn=turn)

    assert predict_next(_graph(), model, current="a") is None


# ── consuming ───────────────────────────────────────────────────────────────────────────────────


async def test_a_first_turn_on_a_node_uses_its_prefetched_material_and_asks_for_none() -> None:
    tutor = CountingTutor()
    session = _session()

    advanced, consumed = await next_turn(
        session,
        _graph(),
        LearnerModel(graph_id="g1"),
        [],
        clock=_clock(1),
        tutor=tutor,
        run_id="r1",
        prefetched={"a": _parts("From the store")},
    )

    assert consumed == "a"
    lesson = advanced.turns[-1]
    assert lesson.move.node_id == "a"
    assert tutor.illustrated == [], "the material was there; the tutor was not asked for it"
    assert lesson.layout is not None
    example = next(
        block for block in lesson.layout.blocks if block.component.value == "WorkedExample"
    )
    assert example.title == "From the store"


async def test_a_second_turn_on_the_same_node_generates_fresh_material() -> None:
    """A remediation must not reuse the first turn's worked example: the P2a eval showed the tutor
    coming at a stuck concept a different way each time is what worked."""
    tutor = CountingTutor()
    first = SessionTurn(
        seq=1,
        move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Root."),
        tutor="A, once.",
        run_id="r1",
        answer="wrong",
    )
    session = _session(first)
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.NOT_MET, at_turn=1)

    advanced, consumed = await next_turn(
        session,
        _graph(),
        model,
        list(session.turns),
        clock=_clock(2),
        tutor=tutor,
        run_id="r2",
        prefetched={"a": _parts("Stale")},
    )

    assert advanced.turns[-1].move.node_id == "a"
    assert consumed is None
    assert tutor.illustrated == ["a"], "a second pass asks the tutor, prefetched or not"


async def test_a_turn_says_which_prefetched_material_it_used() -> None:
    """So the caller can let the store go of it: consumed once, generated fresh after."""
    tutor = CountingTutor()
    outcome = await take_turn(
        _session(
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Root."),
                tutor="A.",
                run_id="r1",
                criterion=_graph().nodes[0].mastery_criteria[0],
            )
        ),
        _graph(),
        LearnerModel(graph_id="g1"),
        answer="Explain a. Explain a.",
        answering_seq=1,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r2",
        elapsed_s=10.0,
        budget_s=1800.0,
        prefetched={"b": _parts()},
    )

    # One MET from nothing is not mastery, so the director stays on a: b's material is not used,
    # and the outcome says so.
    assert outcome.session.turns[-1].move.node_id == "a"
    assert outcome.consumed_material is None

    outcome = await take_turn(
        outcome.session,
        _graph(),
        outcome.model,
        answer="Explain a. Explain a.",
        answering_seq=2,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r3",
        elapsed_s=20.0,
        budget_s=1800.0,
        prefetched={"b": _parts()},
    )
    assert outcome.session.turns[-1].move.node_id == "b"
    assert outcome.consumed_material == "b"


# ── the store ───────────────────────────────────────────────────────────────────────────────────


def test_material_round_trips_per_owner_map_and_node() -> None:
    store = MemoryMaterialStore()
    store.save("g1", "b", _parts("B's"), owner_id="learner-1")

    assert store.load("g1", owner_id="learner-1") == {"b": _parts("B's")}
    assert store.load("g1", owner_id="learner-2") == {}
    assert store.load("g2", owner_id="learner-1") == {}


def test_consumed_material_is_forgotten() -> None:
    store = MemoryMaterialStore()
    store.save("g1", "b", _parts(), owner_id="learner-1")

    store.forget("g1", "b", owner_id="learner-1")

    assert store.load("g1", owner_id="learner-1") == {}


# ── the durable store, against the client's shape ────────────────────────────────────────────────


class FakeSupabase:
    """The narrow slice of supabase-py the material store uses, recording what it was asked."""

    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []
        self.upserts: list[tuple[dict, str]] = []
        self.deleted: list[dict] = []
        self._filters: dict = {}
        self._deleting = False

    def table(self, _name: str) -> "FakeSupabase":
        self._filters, self._deleting = {}, False
        return self

    def select(self, *_columns: str) -> "FakeSupabase":
        return self

    def upsert(self, row: dict, *, on_conflict: str) -> "FakeSupabase":
        self.upserts.append((row, on_conflict))
        return self

    def delete(self) -> "FakeSupabase":
        self._deleting = True
        return self

    def eq(self, column: str, value: object) -> "FakeSupabase":
        self._filters[column] = value
        return self

    def is_(self, column: str, value: object) -> "FakeSupabase":
        self._filters[column] = value
        return self

    def execute(self) -> "types.SimpleNamespace":
        if self._deleting:
            self.deleted.append(dict(self._filters))
        matching = [
            row for row in self.rows if all(row.get(k) == v for k, v in self._filters.items())
        ]
        return types.SimpleNamespace(data=matching)


def test_the_durable_store_writes_the_wire_shape_and_reads_it_back() -> None:
    from lunaris_live.session import SupabaseMaterialStore

    client = FakeSupabase()
    store = SupabaseMaterialStore(client=client)

    store.save("g1", "b", _parts("B's"), owner_id="u1")

    ((row, on_conflict),) = client.upserts
    assert on_conflict == "user_id,graph_id,node_id"
    assert (row["user_id"], row["graph_id"], row["node_id"]) == ("u1", "g1", "b")
    # camelCase, as the wire carries LessonParts, so a stored part and a live part are one shape.
    assert row["payload"]["workedExample"]["title"] == "B's"

    client.rows = [row]
    assert store.load("g1", owner_id="u1") == {"b": _parts("B's")}
    assert store.load("g1", owner_id="someone-else") == {}


def test_the_durable_store_forgets_by_owner_map_and_concept() -> None:
    from lunaris_live.session import SupabaseMaterialStore

    client = FakeSupabase()
    SupabaseMaterialStore(client=client).forget("g1", "b", owner_id="u1")

    assert client.deleted == [{"graph_id": "g1", "node_id": "b", "user_id": "u1"}]
