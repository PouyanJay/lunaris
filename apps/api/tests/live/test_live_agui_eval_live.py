"""The ceiling on real spend, through the real API (Phase 2b, T10).

Every offline test of the per-session ceiling plants a number in the ledger. This one lets the
real tutor teach the opening turn, so the ledger row is what the metering callback recorded off a
real completion, and then asks the AG-UI door for one more turn against a ceiling set below that
spend: a 429 with the ceiling's own sentence, before any frame. One keyed turn, deliberately: it is
the whole chain (model → callback → ledger → rollup → admission → status) that the offline suite
cannot close.

    uv run --env-file .env pytest apps/api/tests/live/test_live_agui_eval_live.py -m eval -q
"""

import os
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_cost_event_store, get_subject_cost_store
from lunaris_runtime.persistence import InMemoryCostEventStore, InMemorySubjectCostStore
from lunaris_runtime.schema import CostSubjectType

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]


async def test_a_session_that_really_spent_past_its_ceiling_is_refused_on_the_stream(
    tmp_path: Path,
) -> None:
    # Arrange: the keyed pipeline, an in-memory ledger, and a ceiling no real turn fits under.
    events, rollup = InMemoryCostEventStore(), InMemorySubjectCostStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="agent",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        live_session_budget_usd=0.0001,
    )
    app.dependency_overrides[get_cost_event_store] = lambda: events
    app.dependency_overrides[get_subject_cost_store] = lambda: rollup
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=180
    ) as client:
        graph = (await client.post("/api/live/graphs", json={"topic": "How tides work"})).json()
        opened = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        assert opened.status_code == 201, opened.text
        session_id = opened.json()["sessionId"]

        # Act: one more turn, over AG-UI.
        response = await client.post(
            f"/api/live/sessions/{session_id}/agui",
            json={
                "threadId": "t",
                "runId": "r",
                "state": {},
                "messages": [{"id": "m1", "role": "user", "content": "The moon pulls the water."}],
                "tools": [],
                "context": [],
                "forwardedProps": {"answeringSeq": 1},
            },
        )

    # Assert: the opening turn's real spend was recorded, and it is what refused the next turn.
    spent = await rollup.get(
        subject_type=CostSubjectType.LIVE_SESSION, subject_id=session_id, owner_id=None
    )
    assert spent is not None and spent.total_amount > 0, (
        "the real turn's spend never reached the ledger"
    )
    assert response.status_code == 429, response.text
    assert "cost ceiling" in response.json()["detail"]
