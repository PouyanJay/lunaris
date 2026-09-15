"""Authenticated course references survive graph compilation without claiming verified teaching."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.live.dependencies import get_live_graph_service
from lunaris_api.live.service import LiveGraphService
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptGraph, MemoryGraphStore, StubGraphCompiler
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor

if TYPE_CHECKING:
    from lunaris_live.corpus.schemas.reference import CorpusReference
    from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot

Stack = tuple[httpx.AsyncClient, "RecordingCompiler"]

COURSE_ID = "corpus-skeleton-course"
DIGEST = "a" * 64
ANSWER_KEY = "private-assessment-answer"


class RecordingCompiler(StubGraphCompiler):
    def __init__(self) -> None:
        self.runs: list[str] = []
        self.sources: list[CorpusSnapshot | None] = []

    async def compile(self, topic: str, **kwargs: Any) -> ConceptGraph:
        self.runs.append(kwargs["run_id"])
        self.sources.append(kwargs.get("grounding"))
        return await super().compile(topic, **kwargs)


class FixtureResolver:
    async def resolve(
        self, reference: "CorpusReference", *, owner_id: str, run_id: str
    ) -> "CorpusSnapshot":
        from lunaris_live.corpus.schemas.provenance import CorpusProvenance
        from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot

        if owner_id != USER_A or reference.course_id != COURSE_ID:
            raise FileNotFoundError(reference.course_id)
        return CorpusSnapshot(
            source=CorpusProvenance(
                course_id=COURSE_ID,
                title="Patient data fixture",
                digest=DIGEST,
                run_id=run_id,
            ),
            sections=[
                {"locator": "lesson:1", "text": "Records hold patient data.", "kind": "lesson"},
                {
                    "locator": "assessment:1",
                    "text": "What does a record hold?",
                    "kind": "assessment",
                    "answer_key": ANSWER_KEY,
                },
            ],
        )


@pytest.fixture
async def stack(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, RecordingCompiler]]:
    graphs = MemoryGraphStore()
    compiler = RecordingCompiler()
    service = LiveGraphService(compiler, graphs, corpus_resolver=FixtureResolver())
    sessions = LiveSessionService(
        graphs,
        MemorySessionStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=1800,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_for(
        tmp_path, supabase_jwt_secret=JWT_SECRET
    )
    app.dependency_overrides[get_live_graph_service] = lambda: service
    app.dependency_overrides[get_live_session_service] = lambda: sessions
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, compiler


async def test_source_provenance_survives_graph_read_without_assessment_keys(
    stack: Stack, capsys: pytest.CaptureFixture[str]
) -> None:
    client, compiler = stack
    response = await client.post(
        "/api/live/graphs",
        json={"topic": "Patient data", "corpus": {"courseId": COURSE_ID}},
        headers=auth_headers(USER_A),
    )
    assert response.status_code == 201, response.text
    graph = response.json()
    assert graph.get("corpus") == {
        "courseId": COURSE_ID,
        "title": "Patient data fixture",
        "digest": DIGEST,
        "adapterVersion": "studio-v1",
        "runId": response.headers["X-Run-Id"],
        "status": "pending",
    }
    assert compiler.runs == [response.headers["X-Run-Id"]]
    assert compiler.sources[0] is not None
    assert compiler.sources[0].sections[0].text == "Records hold patient data."
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    events = {line.get("event") for line in lines if line.get("run_id") == graph["corpus"]["runId"]}
    assert {"live.corpus.resolved", "live.graph.compiled", "live.graph.compile_finished"} <= events
    assert ANSWER_KEY not in json.dumps(lines)
    assert all(node["assets"] == [] for node in graph["nodes"])
    reread = await client.get(f"/api/live/graphs/{graph['graphId']}", headers=auth_headers(USER_A))
    assert reread.status_code == 200
    assert reread.json() == graph
    assert ANSWER_KEY not in response.text + reread.text
    foreign = await client.get(f"/api/live/graphs/{graph['graphId']}", headers=auth_headers(USER_B))
    assert foreign.status_code == 404


@pytest.mark.parametrize("owner,course", [(USER_B, COURSE_ID), (USER_A, "missing")])
async def test_unavailable_source_is_rejected_before_compilation(
    stack: Stack, owner: str, course: str
) -> None:
    client, compiler = stack
    response = await client.post(
        "/api/live/graphs",
        json={"topic": "Patient data", "corpus": {"courseId": course}},
        headers=auth_headers(owner),
    )
    assert response.status_code == 404, response.text
    assert compiler.runs == []


async def test_pending_corpus_graph_cannot_open_teaching_session(stack: Stack) -> None:
    client, _ = stack
    response = await client.post(
        "/api/live/graphs",
        json={"topic": "Patient data", "corpus": {"courseId": COURSE_ID}},
        headers=auth_headers(USER_A),
    )
    assert response.status_code == 201, response.text
    opened = await client.post(
        "/api/live/sessions",
        json={"graphId": response.json()["graphId"]},
        headers=auth_headers(USER_A),
    )
    assert opened.status_code == 409, opened.text


async def test_topic_only_compile_still_opens_a_teaching_session(stack: Stack) -> None:
    client, compiler = stack
    response = await client.post(
        "/api/live/graphs", json={"topic": "Fractions"}, headers=auth_headers(USER_A)
    )
    assert response.status_code == 201, response.text
    assert response.json().get("corpus") is None
    opened = await client.post(
        "/api/live/sessions",
        json={"graphId": response.json()["graphId"]},
        headers=auth_headers(USER_A),
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["turns"][0]["tutor"]
    assert len(compiler.runs) == 1
