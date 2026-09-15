"""Cross-domain corpus publication variants through authenticated API and real Postgres."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from _auth import JWT_SECRET, auth_headers
from _live_stack import settings_for
from langchain_core.messages import AIMessage
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.live.corpus.access_guard import StudioCorpusAccessGuard
from lunaris_api.live.corpus.preparer import CorpusGraphPreparer
from lunaris_api.live.corpus.studio_resolver import StudioCorpusResolver
from lunaris_api.live.dependencies import get_live_graph_service
from lunaris_api.live.service import LiveGraphService
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.corpus.mapping.asset_mapper import AssetMapper
from lunaris_live.corpus.schemas.reference import CorpusReference
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.corpus.stores.supabase_snapshot_store import SupabaseCorpusSnapshotStore
from lunaris_live.corpus.video.schemas.inventory import VideoGap, VideoInventory
from lunaris_live.graph import ClaudeGraphCompiler, SupabaseGraphStore
from lunaris_live.session import MemoryKnowledgeStore, StubGrader, StubTutor, SupabaseSessionStore
from lunaris_runtime.persistence import SupabaseCourseStore
from lunaris_runtime.schema import Course
from test_corpus_publication_database import FixtureProvider
from test_studio_corpus_resolver import course_payload

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY"), reason="local database required"
    ),
]


class VariantProvider(FixtureProvider):
    def __init__(self, snapshot: CorpusSnapshot, domain: str) -> None:
        super().__init__(snapshot)
        self.domain = domain
        self.mode = "normal"
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False

    def _grounding_response(self) -> dict[str, object]:
        return {
            "nodes": [
                {
                    "nodeId": "consent",
                    "classification": "source",
                    "supported": True,
                    "rationale": "Exact course passages support the teaching objective.",
                    "evidence": [
                        {"locator": section.locator, "quote": section.text[:1000]}
                        for section in self.sections
                    ],
                }
            ]
        }

    async def ainvoke(self, prompt: str) -> AIMessage:
        if prompt.startswith("Map exact supplied") and self.mode in {"failure", "waiting"}:
            self.calls += 1
            if self.mode == "failure":
                raise RuntimeError("PRIVATE KEY https://storage.test/file?token=secret")
            self.entered.set()
            try:
                await self.release.wait()
            finally:
                self.cancelled = True
        if "They asked:" in prompt:
            self.calls += 1
            if self.mode == "extension_waiting":
                self.entered.set()
                await self.release.wait()
            return AIMessage(
                content=json.dumps(
                    {
                        "concepts": [
                            {
                                "id": "new",
                                "name": "New concept",
                                "definition": "Beyond source",
                                "requires": [self.domain.lower()],
                            }
                        ]
                    }
                )
            )
        response = await super().ainvoke(prompt)
        assert isinstance(response.content, str)
        return AIMessage(
            content=response.content.replace("Consent", self.domain).replace(
                "consent", self.domain.lower()
            )
        )


class GapInventory:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        return VideoInventory(gaps=(VideoGap.model_validate({"reason": self.reason}),))


@dataclass
class Stack:
    owner: str
    course: Course
    courses: SupabaseCourseStore
    graphs: SupabaseGraphStore
    resolver: StudioCorpusResolver
    db: psycopg.Connection
    tmp_path: Path

    def client(
        self, provider: VariantProvider, reason: str = "no_ready_video"
    ) -> httpx.AsyncClient:
        service = LiveGraphService(
            ClaudeGraphCompiler("fixture", client=provider),
            self.graphs,
            corpus_resolver=self.resolver,
            corpus_preparer=CorpusGraphPreparer(
                AssetMapper("fixture", client=provider), GapInventory(reason)
            ),
            source_access=StudioCorpusAccessGuard(self.courses),
        )
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings_for(
            self.tmp_path, supabase_jwt_secret=JWT_SECRET
        )
        app.dependency_overrides[get_live_graph_service] = lambda: service
        sessions = LiveSessionService(
            self.graphs,
            SupabaseSessionStore(
                url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
            ),
            knowledge=MemoryKnowledgeStore(),
            tutor=StubTutor(),
            grader=StubGrader(),
            source_access=StudioCorpusAccessGuard(self.courses),
            session_budget_s=1800,
        )
        app.dependency_overrides[get_live_session_service] = lambda: sessions
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=auth_headers(self.owner),
        )

    async def provider(self, domain: str = "Consent") -> VariantProvider:
        snapshot = await self.resolver.resolve(
            CorpusReference(course_id=self.course.id), owner_id=self.owner, run_id="fixture"
        )
        return VariantProvider(snapshot, domain)

    def graph_count(self) -> int:
        row = self.db.execute(
            "select count(*) from live_graphs where user_id=%s", (self.owner,)
        ).fetchone()
        assert row is not None
        return row[0]


@pytest.fixture
async def stack(tmp_path: Path) -> AsyncIterator[Stack]:
    owner, course_id = str(uuid4()), uuid4().hex
    env = {"url_env": "LOCAL_SUPABASE_URL", "service_key_env": "LOCAL_SUPABASE_SERVICE_KEY"}
    courses = SupabaseCourseStore(**env)
    graphs = SupabaseGraphStore(**env)
    resolver = StudioCorpusResolver(courses, SupabaseCorpusSnapshotStore(**env))
    payload = course_payload()
    payload["id"] = course_id
    course = Course.model_validate(payload)
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
        try:
            db.execute("insert into auth.users(id) values (%s)", (owner,))
            courses.save(course, owner_id=owner)
            yield Stack(owner, course, courses, graphs, resolver, db, tmp_path)
        finally:
            db.execute("delete from auth.users where id=%s", (owner,))


@pytest.mark.parametrize(
    "domain,reason,source_backed",
    [
        ("Consent", "no_ready_video", True),
        ("Fractions", "silent", True),
        ("Rhythm", "chapter_mismatch", True),
        ("Consent", "inventory_limit", True),
        ("Fractions", "no_ready_video", False),
        ("Rhythm", "silent", False),
    ],
)
async def test_domain_and_optional_video_variants(
    stack: Stack, domain: str, reason: str, source_backed: bool
) -> None:
    stack.course = Course.model_validate_json(
        stack.course.model_dump_json().replace("Consent", domain).replace("consent", domain.lower())
    )
    stack.courses.save(stack.course, owner_id=stack.owner)
    provider = await stack.provider(domain)
    async with stack.client(provider, reason) as client:
        body: dict[str, object] = {"topic": domain}
        if source_backed:
            body["corpus"] = {"courseId": stack.course.id}
        response = await client.post("/api/live/graphs", json=body)
        assert response.status_code == 201, response.text
        graph = response.json()
        assert graph["nodes"][0]["name"] == domain
        reread = await client.get(f"/api/live/graphs/{graph['graphId']}")
        assert reread.json() == graph
        assert (
            stack.graphs.load(graph["graphId"], owner_id=stack.owner).model_dump(
                mode="json", by_alias=True
            )
            == graph
        )
        if source_backed:
            assert graph["corpus"]["status"] == "verified"
            assert graph["mappingReport"]["status"] == "passed"
            assert graph["mappingReport"]["gaps"]
            assert {a["kind"] for a in graph["nodes"][0]["assets"]} == {"lesson", "assessment"}
            assert provider.calls == 5
        else:
            assert graph["corpus"] is None
            assert graph["nodes"][0]["assets"] == []
            assert provider.calls == 2
        assert "PRIVATE KEY" not in response.text


@pytest.mark.parametrize("variant", ["empty", "oversized"])
async def test_invalid_corpus_refused_before_inference(stack: Stack, variant: str) -> None:
    provider = await stack.provider()
    if variant == "empty":
        stack.course.modules = []
    else:
        stack.course.modules[0].lessons[0].segments.activate.prose = "x" * 21000
    stack.courses.save(stack.course, owner_id=stack.owner)
    async with stack.client(provider) as client:
        response = await client.post(
            "/api/live/graphs", json={"topic": "Consent", "corpus": {"courseId": stack.course.id}}
        )
    assert response.status_code == 422, response.text
    assert provider.calls == 0
    assert stack.graph_count() == 0


async def test_mapping_failure_is_not_retried_and_private_inputs_never_logged(
    stack: Stack, capsys: pytest.CaptureFixture[str]
) -> None:
    stack.course.topic = "PRIVATE_COURSE_TITLE_SENTINEL"
    stack.courses.save(stack.course, owner_id=stack.owner)
    provider = await stack.provider()
    provider.mode = "failure"
    async with stack.client(provider) as client:
        response = await client.post(
            "/api/live/graphs",
            json={"topic": "PRIVATE_TOPIC_SENTINEL", "corpus": {"courseId": stack.course.id}},
        )
    assert response.status_code == 201, response.text
    assert response.json()["corpus"]["status"] == "failed"
    assert response.json()["mappingReport"]["status"] == "failed"
    assert response.json()["nodes"][0]["assets"] == []
    assert provider.calls == 4
    logs = capsys.readouterr().out
    for private in (
        "PRIVATE_TOPIC_SENTINEL",
        "PRIVATE_COURSE_TITLE_SENTINEL",
        "PRIVATE KEY",
        "token=secret",
        "Recall consent",
    ):
        assert private not in logs


async def test_cancelled_mapping_does_not_publish_or_restart(stack: Stack) -> None:
    provider = await stack.provider()
    provider.mode = "waiting"
    async with stack.client(provider) as client:
        task = asyncio.create_task(
            client.post(
                "/api/live/graphs",
                json={"topic": "Consent", "corpus": {"courseId": stack.course.id}},
            )
        )
        try:
            await asyncio.wait_for(provider.entered.wait(), 2)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert provider.cancelled
    assert provider.calls == 4
    assert stack.graph_count() == 0


async def test_unverified_extension_is_refused_without_replacing_usable_source_graph(
    stack: Stack, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = await stack.provider()
    async with stack.client(provider) as client:
        initial = await client.post(
            "/api/live/graphs", json={"topic": "Consent", "corpus": {"courseId": stack.course.id}}
        )
        assert initial.status_code == 201, initial.text
        graph = initial.json()
        response = await client.post(
            f"/api/live/graphs/{graph['graphId']}/extend",
            json={"request": "PRIVATE_EXTENSION_SENTINEL", "anchors": ["consent"]},
        )
        assert response.status_code == 409, response.text
        persisted = stack.graphs.load(graph["graphId"], owner_id=stack.owner)
        assert persisted.model_dump(mode="json", by_alias=True) == graph
        opened = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        assert opened.status_code == 201, opened.text
        assert all(turn["move"]["nodeId"] != "new" for turn in opened.json()["turns"])
    assert "PRIVATE_EXTENSION_SENTINEL" not in capsys.readouterr().out


async def test_source_revision_during_extension_never_overwrites_published_graph(
    stack: Stack,
) -> None:
    provider = await stack.provider()
    async with stack.client(provider) as client:
        initial = await client.post(
            "/api/live/graphs", json={"topic": "Consent", "corpus": {"courseId": stack.course.id}}
        )
        assert initial.status_code == 201, initial.text
        graph = initial.json()
        provider.mode = "extension_waiting"
        task = asyncio.create_task(
            client.post(
                f"/api/live/graphs/{graph['graphId']}/extend",
                json={"request": "New branch", "anchors": ["consent"]},
            )
        )
        try:
            await asyncio.wait_for(provider.entered.wait(), 2)
            stack.course.modules[0].lessons[0].segments.activate.prose = "Revised source"
            stack.courses.save(stack.course, owner_id=stack.owner)
            provider.release.set()
            response = await asyncio.wait_for(task, 2)
            assert response.status_code == 409, response.text
        finally:
            provider.release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    persisted = stack.graphs.load(graph["graphId"], owner_id=stack.owner)
    assert persisted.model_dump(mode="json", by_alias=True) == graph


async def test_legacy_graph_and_session_json_without_material_fields_still_read(
    stack: Stack,
) -> None:
    provider = await stack.provider()
    async with stack.client(provider) as client:
        response = await client.post("/api/live/graphs", json={"topic": "Consent"})
        assert response.status_code == 201, response.text
        graph = response.json()
        for key in ("corpus", "groundingReport", "mappingReport"):
            graph.pop(key, None)
        for node in graph["nodes"]:
            node.pop("assets", None)
        stack.db.execute(
            "update live_graphs set payload=%s::jsonb where id=%s and user_id=%s",
            (json.dumps(graph), graph["graphId"], stack.owner),
        )
        reread = await client.get(f"/api/live/graphs/{graph['graphId']}")
        assert reread.status_code == 200, reread.text
        assert reread.json()["corpus"] is None
        assert reread.json()["nodes"][0]["assets"] == []
        started = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        assert started.status_code == 201, started.text
        session = started.json()
        for turn in session["turns"]:
            turn.pop("materials", None)
        stack.db.execute(
            "update live_sessions set payload=%s::jsonb where id=%s and user_id=%s",
            (json.dumps(session), session["sessionId"], stack.owner),
        )
        reread_session = await client.get(f"/api/live/sessions/{session['sessionId']}")
        assert reread_session.status_code == 200, reread_session.text
        assert reread_session.json()["turns"][0]["materials"] == []
        assert reread_session.json()["turns"][0]["tutor"] == session["turns"][0]["tutor"]
        assert provider.calls == 2


async def test_large_valid_source_is_honestly_not_ready_when_material_cannot_be_mapped(
    stack: Stack,
) -> None:
    stack.course.modules[0].lessons[0].segments.activate.prose = "Source detail. " * 1000
    stack.courses.save(stack.course, owner_id=stack.owner)
    provider = await stack.provider()
    async with stack.client(provider) as client:
        response = await client.post(
            "/api/live/graphs", json={"topic": "Consent", "corpus": {"courseId": stack.course.id}}
        )
        assert response.status_code == 201, response.text
        graph = response.json()
        assert graph["corpus"]["status"] == "failed"
        assert graph["mappingReport"]["status"] == "failed"
        assert graph["mappingReport"]["gaps"]
        assert not any(
            asset["kind"] == "lesson" for node in graph["nodes"] for asset in node["assets"]
        )
        refused = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})
        assert refused.status_code == 409, refused.text
        assert provider.calls == 5
