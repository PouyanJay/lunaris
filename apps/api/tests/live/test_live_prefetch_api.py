"""Lunaris Live, Phase 2c — material one node ahead, through the API (T4).

Plan §6: per-node material is "generated on demand and prefetched one node ahead", so the runtime is
always ahead of the learner. Through the real app: after a teaching turn, the concept the director
would move to next has its first-turn material in the store before the learner has answered; the
turn that then reaches that concept uses it and asks the tutor for nothing (no second model call,
no grace to lose); the root's material is prefetched while the learner is still being interviewed,
so the first lesson arrives full; and every prefetch is the session's own spend, on the session's
own ledger, under the session's own ceiling.

Rendezvous, not sleeps: the tutor double counts and gates its illustrations, and the prefetcher's
registry is awaited at its end.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_cost_event_store, get_subject_cost_store
from lunaris_api.live.dependencies import launched_compiles
from lunaris_api.live.session.dependencies import get_live_tutor
from lunaris_api.live.session.prefetch_registry import prefetch_registry
from lunaris_live.graph import ConceptNode, MasteryCriterion
from lunaris_live.session import DirectorMove, LessonParts, StubTutor, WorkedExample
from lunaris_runtime.metering import record_cost
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostProvider, CostSubjectType, CostUnit


class GatedIllustrator(StubTutor):
    """The stub tutor whose material is counted, priced, and — after ``allow`` runs out — held.

    ``allow`` is how many illustrations may complete; the next one parks on ``held`` until the
    test releases it. A turn that reaches a concept whose material was prefetched never asks, so
    it never parks: that a turn completes with material while the illustrator is held is the proof
    that the material came from the store and not from a call that happened to be fast.
    """

    def __init__(self, allow: int) -> None:
        self.allow = allow
        self.illustrated: list[str] = []
        self.release = asyncio.Event()

    async def illustrate(
        self,
        move: DirectorMove,
        node: ConceptNode,
        *,
        topic: str,
        criterion: MasteryCriterion | None = None,
        already_said: Sequence[str] = (),
        profile: str | None = None,
        run_id: str,
    ) -> LessonParts:
        self.illustrated.append(node.id)
        if len(self.illustrated) > self.allow:
            await asyncio.wait_for(self.release.wait(), 5)
        record_cost(
            component="live_tutor_material",
            provider=CostProvider.ANTHROPIC,
            model="claude-opus-4-8",
            usage={CostUnit.INPUT_TOKENS: 800.0, CostUnit.OUTPUT_TOKENS: 300.0},
        )
        return LessonParts(
            worked_example=WorkedExample(title=f"{node.name}, worked", steps=["one", "two"]),
            hint=f"About {node.name}.",
            practice=[f"Try {node.name}."],
        )


@pytest.fixture
async def stack(
    tmp_path: Path,
) -> AsyncIterator[tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore]]:
    tutor = GatedIllustrator(allow=10)
    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app.dependency_overrides[get_live_tutor] = lambda: tutor
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, tutor, events
        tutor.release.set()
        await prefetch_registry().settled()


async def _graph(client: httpx.AsyncClient) -> dict:
    return (await client.post("/api/live/graphs", json={"topic": "How tides work"})).json()


def _example_titles(turn: dict) -> list[str]:
    layout = turn.get("layout") or {}
    return [
        block["title"]
        for block in layout.get("blocks", [])
        if block.get("component") == "WorkedExample"
    ]


async def test_after_a_turn_the_next_concepts_material_is_already_there(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """The map is a chain: foundations → core → top. Opening teaches the root (its own material,
    asked for beside the lesson); before the learner has said a word, the next concept's material
    has been asked for and stored."""
    client, tutor, _ = stack
    graph = await _graph(client)

    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    await prefetch_registry().settled()

    # The lesson's own material, then the prefetch for the next concept, in that order.
    assert tutor.illustrated == [graph["topoOrder"][0], graph["topoOrder"][1]]
    assert session["turns"][0]["move"]["nodeId"] == graph["topoOrder"][0]


async def test_the_turn_that_reaches_a_prefetched_concept_asks_the_tutor_for_no_material(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """The point of prefetching: the second concept's first turn carries material and made no
    illustrate call to get it — proven by holding the illustrator from here on: had the turn asked,
    it would have parked (and lost the material to the grace); it did neither."""
    client, tutor, _ = stack
    graph = await _graph(client)
    root, second = graph["topoOrder"][0], graph["topoOrder"][1]
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    await prefetch_registry().settled()
    assert tutor.illustrated == [root, second]
    url = f"/api/live/sessions/{session['sessionId']}"

    # Demonstrate the root (two METs from nothing; the offline grader marks a restated criterion
    # MET), so the director moves on to the second concept. The first answer keeps the director on
    # the root (one MET is not mastery), and that second pass over the root asks the tutor live —
    # the third illustration. From there everything parks: a live illustrate for the second concept
    # would be the fourth call, and it would park, and the grace would lose the material.
    tutor.allow = 3
    for _ in range(2):
        standing = session["turns"][-1]
        response = await client.post(
            f"{url}/turns",
            json={"answer": standing["criterion"]["statement"], "answeringSeq": standing["seq"]},
        )
        assert response.status_code == 200, response.text
        session = response.json()

    reached = session["turns"][-1]
    assert reached["move"]["nodeId"] == second
    assert _example_titles(reached), "the first turn on the second concept carries material"
    # The lesson's own, the prefetch, the second pass over the root, then whatever prefetch parked
    # after the hold: never a second call for the second concept.
    assert tutor.illustrated[:3] == [root, second, root]
    assert tutor.illustrated.count(second) == 1, "the store, not a call, supplied it"


async def test_a_second_pass_over_a_concept_generates_fresh_material(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """A remediation must not be handed the first turn's example again."""
    client, tutor, _ = stack
    graph = await _graph(client)
    root = graph["topoOrder"][0]
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    await prefetch_registry().settled()
    url = f"/api/live/sessions/{session['sessionId']}"

    # A miss keeps the director on the root; the second pass asks the tutor again.
    standing = session["turns"][-1]
    response = await client.post(
        f"{url}/turns", json={"answer": "no idea", "answeringSeq": standing["seq"]}
    )
    assert response.status_code == 200, response.text
    again = response.json()["turns"][-1]
    assert again["move"]["nodeId"] == root
    await prefetch_registry().settled()
    assert tutor.illustrated.count(root) == 2


async def test_used_material_is_let_go_of_so_a_later_first_turn_asks_afresh(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """Consumed once: the turn that used a concept's kept material lets the store go of it. A
    second session on the same map (P2a's opening) meets the root as a first turn again, and asks
    the tutor afresh rather than being handed the words the first session already used."""
    client, tutor, _ = stack
    # Session one is placed by topic, so the root's material is prefetched when the map lands and
    # then USED by the first lesson (kept → consumed).
    placed = (await client.post("/api/live/sessions", json={"topic": "How tides work"})).json()
    compiling = launched_compiles().compiling(placed["graphId"])
    if compiling is not None:
        await compiling
    await prefetch_registry().settled()
    first = await client.post(
        f"/api/live/sessions/{placed['sessionId']}/turns",
        json={"answer": "Nothing yet.", "answeringSeq": 1},
    )
    assert first.status_code == 200, first.text
    await prefetch_registry().settled()
    used_root = first.json()["turns"][-1]["move"]["nodeId"]
    before = tutor.illustrated.count(used_root)

    # Session two on the same map: the root is a first turn again, and its material is gone.
    again = await client.post("/api/live/sessions", json={"graphId": placed["graphId"]})
    assert again.status_code == 201, again.text
    await prefetch_registry().settled()

    assert again.json()["turns"][0]["move"]["nodeId"] == used_root
    assert tutor.illustrated.count(used_root) == before + 1, "asked afresh: the store let it go"


async def test_the_roots_material_is_prefetched_while_the_learner_is_still_being_interviewed(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """Plan §6: "teaching begins the moment the first node's materials exist". The compile lands
    during the interview; the root's material is asked for then, so the first lesson is full and
    made no illustrate call of its own — proven with the illustrator held from the moment the
    prefetch completed."""
    client, tutor, _ = stack
    session = (await client.post("/api/live/sessions", json={"topic": "How tides work"})).json()
    # Meet the compile at its end (its landing schedules the prefetch), then the prefetch at its.
    compiling = launched_compiles().compiling(session["graphId"])
    if compiling is not None:
        await compiling
    await prefetch_registry().settled()
    assert len(tutor.illustrated) == 1, "the root, prefetched when the map landed"
    tutor.allow = 1

    response = await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={"answer": "Not much, honestly.", "answeringSeq": 1},
    )

    assert response.status_code == 200, response.text
    lesson = response.json()["turns"][-1]
    assert lesson["move"]["kind"] == "introduce"
    assert _example_titles(lesson) == [f"{lesson['surface']['concept']}, worked"]
    assert tutor.illustrated[0] == lesson["move"]["nodeId"]


async def test_a_session_opened_on_a_map_uses_material_kept_from_an_abandoned_placement(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """The opening on a map (P2a's) reads the store too: a placement that prefetched the root and
    was then walked away from leaves the root's material kept, and a later session opened by map
    id starts on it without asking — proven with the illustrator held from that point."""
    client, tutor, _ = stack
    placed = (await client.post("/api/live/sessions", json={"topic": "How tides work"})).json()
    compiling = launched_compiles().compiling(placed["graphId"])
    if compiling is not None:
        await compiling
    await prefetch_registry().settled()
    assert len(tutor.illustrated) == 1
    tutor.allow = 1

    again = await client.post("/api/live/sessions", json={"graphId": placed["graphId"]})

    assert again.status_code == 201, again.text
    lesson = again.json()["turns"][0]
    assert _example_titles(lesson) == [f"{lesson['surface']['concept']}, worked"]
    assert tutor.illustrated[:1] == [lesson["move"]["nodeId"]]

    # Consumed once, at the open as at any turn (found in review: an opening used the material and
    # never let the store go of it, so every later session replayed the same words): a THIRD
    # session on the map asks afresh for the root.
    tutor.release.set()  # nothing to hold from here: what is asked is the point
    await prefetch_registry().settled()
    third = await client.post("/api/live/sessions", json={"graphId": placed["graphId"]})
    assert third.status_code == 201, third.text
    assert tutor.illustrated.count(lesson["move"]["nodeId"]) == 2, "asked afresh"


async def test_a_prefetch_is_the_sessions_own_spend(
    stack: tuple[httpx.AsyncClient, GatedIllustrator, InMemoryCostEventStore],
) -> None:
    """The ledger sees the material one node ahead as this session's money, filed under the
    session (``LIVE_SESSION``), not under the map and not nowhere: two material events on the
    session — the lesson's own and the prefetched one — each under its own run."""
    client, tutor, events = stack
    graph = await _graph(client)
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    await prefetch_registry().settled()
    assert len(tutor.illustrated) == 2

    filed = await events.list_for_subject(
        subject_type=CostSubjectType.LIVE_SESSION, subject_id=session["sessionId"], owner_id=None
    )
    material = [event for event in filed if event.component == "live_tutor_material"]
    assert len(material) == 2
    run_ids = {event.run_id for event in material}
    assert len(run_ids) == 2, "a prefetch is its own run"
    assert session["turns"][0]["runId"] in run_ids, "one of them is the lesson's own"
