"""Tier 2 on the wire: the lesson as it was composed for this learner (Phase 2b, T5).

Plan §8's Tier 2 is the tier where *"the lesson is rendered at runtime"* is literally true — the
same concept laid out differently for two learners who know different amounts. T5 builds that
composition in `lunaris_live`; this is the claim that it survives the API, the store and the
transport, which is where a layout stops being a data structure and starts being what somebody
reads.

Two things are pinned here that the package-level suite cannot see:

* the layout the wire carries **is** the layout the session row stored, so a reloaded tab and a live
  turn are the same lesson;
* it arrives as its own tool call, after the card its slot points at.

Exercised through the real ASGI app: the router, the service, the loop and the store are the
production ones, with the stub tutor and grader standing in for the model.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from _agui_frames import call_named, tool_names
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.session.agui.layout_tool import LAYOUT_TOOL
from lunaris_api.live.session.agui.surface_tool import SURFACE_TOOL


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _session(client: httpx.AsyncClient) -> dict[str, Any]:
    graph = (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


async def _events(
    client: httpx.AsyncClient, session_id: str, *, answer: str | None = None
) -> list[dict[str, Any]]:
    messages = [{"id": "m1", "role": "user", "content": answer}] if answer is not None else []
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


def _components(layout: dict[str, Any]) -> list[str]:
    return [block["component"] for block in layout["blocks"]]


def _example_in(layout: dict[str, Any]) -> dict[str, Any]:
    """The worked example, looked up by name. Never by position: the composer is free to reorder,
    and an index would start silently asserting about a different block."""
    return next(block for block in layout["blocks"] if block["component"] == "WorkedExample")


async def test_a_turn_carries_the_layout_it_was_composed_into(client: httpx.AsyncClient) -> None:
    """The wire and the stored row are the same composition.

    Asserted against the session row rather than against a shape, for the reason Tier 1's own test
    gives: a transport that streamed one lesson and recorded another would look perfect from the
    server and leave a reloaded tab reading something the learner never saw.
    """
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert call_named(events, LAYOUT_TOOL) == reread["turns"][-1]["layout"]


async def test_the_layout_is_named_by_the_tool_the_browser_registers(
    client: httpx.AsyncClient,
) -> None:
    """A contract between two separately deployed things, pinned as a literal on both sides.

    Drift here is a lesson that silently renders as bare prose while every server-side assertion
    passes."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    assert tool_names(events) == ["lunaris.surface", "lunaris.layout"]
    assert LAYOUT_TOOL == "lunaris.layout"


async def test_the_layout_arrives_after_the_card_its_slot_points_at(
    client: httpx.AsyncClient,
) -> None:
    """Order is the contract, again. The layout holds a *slot* for the Tier 1 card, so a client
    drawing frames as they land must already have the card — otherwise its first paint is a hole."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    names = tool_names(events)
    assert names.index(SURFACE_TOOL) < names.index(LAYOUT_TOOL)

    types = [event["type"] for event in events]
    assert types.index("TEXT_MESSAGE_END") < types.index("TOOL_CALL_START")
    assert types.index("STATE_SNAPSHOT") > max(
        index for index, kind in enumerate(types) if kind == "TOOL_CALL_END"
    )


async def test_the_layout_slots_the_words_and_the_card_rather_than_copying_them(
    client: httpx.AsyncClient,
) -> None:
    """What the slots are for. The lesson text and the criterion the learner is marked on each exist
    once, on the turn; a layout carrying its own copy could disagree with the thing being marked."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    standing = reread["turns"][-1]
    layout = call_named(events, LAYOUT_TOOL)

    assert "Prose" in _components(layout)
    assert "Surface" in _components(layout)
    assert standing["tutor"] not in json.dumps(layout)


async def test_the_same_concept_is_laid_out_differently_once_the_learner_has_moved(
    client: httpx.AsyncClient,
) -> None:
    """T5's claim, end to end: one session, one concept, the composition changed because the
    learner did.

    Stronger than two hand-built learner models, and it is the only version that proves the
    *wiring* — that the composer is handed this turn's concept and the belief as it stands after
    the answer, not the belief the turn opened with. A single good answer is enough to cross the
    director's lower threshold, and everything else about the turn is held fixed: same map, same
    concept, same tutor writing the same material.
    """
    # Arrange — the opening turn on a concept the learner has never met.
    session = await _session(client)
    session_id = session["sessionId"]
    opening = session["turns"][-1]
    assert _example_in(opening["layout"])["expanded"] is True, "the fixture needs an open example"

    # Act — one good answer, then the turn the director takes next.
    await _events(client, session_id, answer=opening["criterion"]["statement"])
    reread = (await client.get(f"/api/live/sessions/{session_id}")).json()
    standing = reread["turns"][-1]

    # Assert — the same concept, still being taught, and no longer opened for a beginner.
    assert standing["move"]["nodeId"] == opening["move"]["nodeId"]
    assert _example_in(standing["layout"])["expanded"] is False, (
        "a learner who has just demonstrated something is still being handed a beginner's lesson"
    )
    assert standing["layout"] != opening["layout"]


async def test_a_concept_the_learner_has_no_hold_on_is_scaffolded_in_full(
    client: httpx.AsyncClient,
) -> None:
    """The other end of the same rule, and the band a session opens in: everything the tutor wrote,
    with the example open and the practice unabridged."""
    # Arrange / Act
    session = await _session(client)

    # Assert
    layout = call_named(await _events(client, session["sessionId"], answer=None), LAYOUT_TOOL)
    assert _components(layout) == [
        "Stack",
        "Prose",
        "WorkedExample",
        "Practice",
        "Surface",
        "Hint",
    ]
