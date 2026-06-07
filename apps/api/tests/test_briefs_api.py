"""Integration tests for the phase-1 brief endpoint (P7.5): interpret a topic into a brief + the
opt-in confirm clarifier. HTTP → the key-gated goal-interpreter dependency → build_clarifier. No
Anthropic key needed: the dependency falls back to a deterministic topic-derived brief.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
    )


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_briefs_returns_an_inferred_brief_and_the_clarifier(
    client: httpx.AsyncClient,
) -> None:
    # Act — phase 1 of the infer-and-confirm flow.
    response = await client.post("/api/briefs", json={"topic": "binary search"})

    # Assert — the inferred brief (camelCase) + the confirm questions, in order.
    assert response.status_code == 200
    assert response.headers["x-request-id"]  # correlation id surfaced
    body = response.json()
    # The no-key fallback (DefaultGoalInterpreter) derives the subject from the topic, end-to-end.
    assert body["brief"]["subject"] == "binary search"
    assert [q["id"] for q in body["clarifier"]["questions"]] == [
        "goal",
        "level",
        "knowledge",
        "background",
        "detail",
        "language",
    ]


async def test_briefs_clarifier_pre_picks_the_inferred_values(tmp_path: Path) -> None:
    # Arrange — override the interpreter with a stub returning a fully-specified (ADVANCED) brief,
    # so the clarifier's Recommended pre-picks track the inference deterministically.
    from lunaris_agent.subagents.goal_interpreter import StubGoalInterpreter
    from lunaris_api.dependencies import get_goal_interpreter
    from lunaris_runtime.schema import (
        CourseBrief,
        DetailDepth,
        LanguageStyle,
        Level,
        Preferences,
    )

    brief = CourseBrief(
        subject="x",
        goal="g",
        target_level=Level.ADVANCED,
        preferences=Preferences(
            detail_depth=DetailDepth.IN_DEPTH, language_style=LanguageStyle.SOPHISTICATED
        ),
    )
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    app.dependency_overrides[get_goal_interpreter] = lambda: StubGoalInterpreter(brief)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        # Act
        body = (await http.post("/api/briefs", json={"topic": "anything"})).json()

    # Assert — each choice question pre-picks the inferred value (the zero-friction confirm path).
    def recommended(question_id: str) -> list[str]:
        question = next(q for q in body["clarifier"]["questions"] if q["id"] == question_id)
        return [o["value"] for o in question["options"] if o["recommended"]]

    assert recommended("level") == ["advanced"]
    assert recommended("detail") == ["in_depth"]
    assert recommended("language") == ["sophisticated"]


async def test_briefs_rejects_a_blank_topic(client: httpx.AsyncClient) -> None:
    # Act / Assert — the topic is validated at the boundary just like the build endpoints.
    response = await client.post("/api/briefs", json={"topic": ""})

    assert response.status_code == 422


async def test_briefs_rejects_a_whitespace_only_topic(client: httpx.AsyncClient) -> None:
    # Act / Assert — an all-whitespace topic is rejected too, so the fallback never derives a blank
    # subject/goal (``min_length`` alone would admit it).
    response = await client.post("/api/briefs", json={"topic": "   "})

    assert response.status_code == 422
