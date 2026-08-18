"""Lunaris Live, Phase 2b T10: every Tier 1 variant, reached end to end and offline.

T3 pinned each card at the package level and T4 drew each one; what neither could do was reach
every card **through the real path**, compile → session → AG-UI, without a key, because the stub
compiler authored one EXPLAIN criterion per concept and never a simulator-only one. So three of the
six kinds (`CRITERION_CARD`, `CONCEPT_MAP`, `SIM_APP`) were only ever seen with a planted map, and
a stub-mode session, which is what CI and keyless dev run, could never show them.

The variant table is the whole `SurfaceKind` enum, asserted as such: a seventh kind fails this file
until it is driven here, which is the point of a variant task. Each kind is reached by *driving the
loop* (answering the way a learner would have to) rather than by planting a session, so the path a
card takes to a learner is the path under test.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from _agui_frames import call_named
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.session.agui.surface_tool import SURFACE_TOOL
from lunaris_live.session import SurfaceKind

#: A topic the stub compiler adds a hands-on, simulator-only concept to (T10). Any other topic
#: compiles to the three prose concepts every earlier task's tests read.
_HANDS_ON_TOPIC = "Hands-on with pendulums"
_PROSE_TOPIC = "How tides work"

#: How many answers a driven session may take before a variant is declared unreachable. Generous:
#: the longest path (three concepts mastered, then the simulator-only one) is under fifteen turns.
_MAX_TURNS = 30


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture
async def make_client(tmp_path: Path):
    """A client over the real app, with the settings a variant needs (a spent clock for the meter,
    the placeholder registry for the simulator card). Every client made is closed on teardown,
    whether or not the test closed it: a variant that forgets its ``async with`` must not leak a
    transport, and closing twice is a no-op."""
    clients: list[httpx.AsyncClient] = []

    async def _make(**overrides: object) -> httpx.AsyncClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: _settings(tmp_path, **overrides)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield _make

    for client in clients:
        await client.aclose()


async def _open(client: httpx.AsyncClient, topic: str) -> dict[str, Any]:
    graph = (await client.post("/api/live/graphs", json={"topic": topic})).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


async def _run(
    client: httpx.AsyncClient, session_id: str, *, answer: str | None
) -> list[dict[str, Any]]:
    """One AG-UI run: an answer takes a turn, no answer replays the standing one."""
    messages = [{"id": "m", "role": "user", "content": answer}] if answer is not None else []
    collected: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/live/sessions/{session_id}/agui",
        json={
            "threadId": "t",
            "runId": "r",
            "state": {},
            "messages": messages,
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                collected.append(json.loads(line.removeprefix("data:").strip()))
    return collected


def _card(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return call_named(events, SURFACE_TOOL)
    except StopIteration:
        return None


def _snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    return next(event["snapshot"] for event in events if event["type"] == "STATE_SNAPSHOT")


async def _drive_until(
    client: httpx.AsyncClient,
    session_id: str,
    kind: SurfaceKind,
    *,
    answer_with: str,
) -> dict[str, Any]:
    """Answer turn after turn until the standing card is ``kind``, and return that card.

    ``answer_with`` is the learner's strategy: ``"criterion"`` echoes the staged do-statement (the
    stub grader marks word overlap, so this is MET, and the director advances), ``"miss"`` says
    something unrelated (NOT_MET, twice over, and the director remediates).
    """
    events = await _run(client, session_id, answer=None)
    for _ in range(_MAX_TURNS):
        card = _card(events)
        if card is not None and card["kind"] == kind.value:
            return card
        snapshot = _snapshot(events)
        if snapshot["status"] != "active":
            break
        criterion = snapshot.get("criterion") or "nothing"
        said = criterion if answer_with == "criterion" else "I have no idea, honestly."
        events = await _run(client, session_id, answer=said)
    raise AssertionError(f"{kind.value} was never reached; last card: {_card(events)}")


VARIANTS: dict[SurfaceKind, dict[str, Any]] = {
    # The opening turn on the first prose concept: explain it back.
    SurfaceKind.EXPLAIN_BACK: {"topic": _PROSE_TOPIC, "answer_with": "criterion"},
    # Master the first concept and the director introduces the second, whose criterion is a
    # PREDICT do-statement, met as written.
    SurfaceKind.CRITERION_CARD: {"topic": _PROSE_TOPIC, "answer_with": "criterion"},
    # Miss twice and the director remediates with the authored misconceptions.
    SurfaceKind.QUIZ_CARD: {"topic": _PROSE_TOPIC, "answer_with": "miss"},
    # A spent clock closes the session on the next turn.
    SurfaceKind.MASTERY_METER: {
        "topic": _PROSE_TOPIC,
        "answer_with": "criterion",
        "settings": {"live_session_budget_s": 0.001},
    },
    # A hands-on topic ends in a simulator-only concept; with no registry it cannot be checked.
    SurfaceKind.CONCEPT_MAP: {"topic": _HANDS_ON_TOPIC, "answer_with": "criterion"},
    # The same concept, with the placeholder registry mounted.
    SurfaceKind.SIM_APP: {
        "topic": _HANDS_ON_TOPIC,
        "answer_with": "criterion",
        "settings": {"live_sims": "stub"},
    },
}


def test_every_kind_the_director_can_choose_has_a_variant_here() -> None:
    """The table is the enum. A new card kind fails here until somebody drives it."""
    assert set(VARIANTS) == set(SurfaceKind)


@pytest.mark.parametrize("kind", list(SurfaceKind), ids=[kind.value for kind in SurfaceKind])
async def test_every_tier1_card_is_reachable_through_the_real_path(make_client, kind) -> None:
    """Compile → open → answer → AG-UI, offline, and the card the director chose comes down the
    wire as the tool call the browser registers, with the props that kind carries."""
    variant = VARIANTS[kind]
    client = await make_client(**variant.get("settings", {}))
    async with client:
        session = await _open(client, variant["topic"])

        card = await _drive_until(
            client, session["sessionId"], kind, answer_with=variant["answer_with"]
        )

    assert card["kind"] == kind.value
    # Every card names the concept it is about except the meter, which is about the session.
    if kind is not SurfaceKind.MASTERY_METER:
        assert card["concept"]
    if kind is SurfaceKind.CRITERION_CARD:
        assert card["asks"] == "predict", card
    if kind is SurfaceKind.QUIZ_CARD:
        assert len(card["options"]) >= 2
    if kind is SurfaceKind.CONCEPT_MAP:
        assert card["prerequisites"], "the simulator-only concept sits on the prose ones"
    if kind is SurfaceKind.SIM_APP:
        assert card["url"].endswith("/api/live/sims/stub")
