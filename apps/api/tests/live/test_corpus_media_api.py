"""Authenticated media URLs require fresh source, standing-turn and exact clip evidence."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from _auth import JWT_SECRET, auth_headers
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.live.corpus.access_guard import StudioCorpusAccessGuard
from lunaris_api.live.corpus.dependencies import get_corpus_media_resolver
from lunaris_api.live.corpus.media_resolver import CorpusMediaResolver
from lunaris_api.live.corpus.models.media_services import CorpusMediaServices
from lunaris_live.corpus.schemas.asset import NodeAsset
from lunaris_live.corpus.schemas.asset_verification import AssetVerification
from lunaris_live.corpus.video.schemas.clip import VideoClip
from lunaris_live.corpus.video.schemas.cue import Cue
from lunaris_live.corpus.video.schemas.inventory import VideoInventory
from lunaris_live.graph import ConceptNode, MemoryGraphStore
from lunaris_live.session import MemorySessionStore, Session
from lunaris_live.session.schema import SessionStatus
from test_corpus_access_guard import Courses, source_graph

_NOW = datetime.now(UTC)


class Inventory:
    def __init__(self, clip: VideoClip) -> None:
        self.clips = (clip,)
        self.calls: list[tuple[str, str, str]] = []

    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        self.calls.append((course_id, owner_id, run_id))
        return VideoInventory(clips=self.clips)


class Storage:
    def __init__(self) -> None:
        self.paths: list[tuple[str, int]] = []

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        self.paths.append((path, expires_in_seconds))
        return f"https://media.test/clip?token={len(self.paths)}"


def clip_fixture() -> VideoClip:
    return VideoClip(
        job_id="job",
        source_digest="b" * 64,
        locator="video:job:" + "b" * 64 + ":0:1000",
        start_s=0,
        end_s=1,
        duration_s=10,
        title="Consent",
        transcript=(Cue(start_s=0, end_s=1, text="Consent identifies purpose."),),
    )


@pytest.fixture
async def stack(tmp_path: Path) -> AsyncIterator[tuple[Any, ...]]:
    courses, sessions, graphs = Courses(), MemorySessionStore(), MemoryGraphStore()
    graph = source_graph(courses)
    clip = clip_fixture()
    asset = NodeAsset(
        asset_id="asset",
        kind="video_clip",
        origin="ingested",
        locator=clip.locator,
        source_digest=graph.corpus.digest,
        title="Consent",
        clip=clip,
        verification=AssetVerification(
            run_id="verified", verifier_version="fixture", source_digest=graph.corpus.digest
        ),
    )
    graph.nodes = [ConceptNode(id="node", name="Consent", definition="Consent", assets=[asset])]
    graphs.save(graph, owner_id="owner")
    session = Session.model_validate(
        {
            "sessionId": "session",
            "graphId": "graph",
            "startedAt": _NOW,
            "turns": [
                {
                    "seq": 1,
                    "move": {"kind": "introduce", "nodeId": "node", "reason": "Teach consent"},
                    "tutor": "Consent",
                    "runId": "turn",
                    "materials": [asset],
                }
            ],
        }
    )
    sessions.save(session, owner_id="owner")
    inventory, storage = Inventory(clip), Storage()
    resolver = CorpusMediaResolver(
        CorpusMediaServices(sessions, graphs, StudioCorpusAccessGuard(courses), inventory, storage),
        session_budget_s=1800,
        clock=lambda: _NOW,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_for(
        tmp_path, supabase_jwt_secret=JWT_SECRET
    )
    app.dependency_overrides[get_corpus_media_resolver] = lambda: resolver
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, courses, sessions, graphs, inventory, storage, app


async def test_signed_url_refresh_is_readonly_and_uses_server_derived_path(
    stack: tuple[Any, ...],
) -> None:
    client, _courses, sessions, _graphs, inventory, storage, _app = stack
    before = sessions.load("session", owner_id="owner").model_dump_json()
    first = await client.get(
        "/api/live/sessions/session/materials/asset/media?turn=1", headers=auth_headers("owner")
    )
    assert first.status_code == 200
    second = await client.get(
        "/api/live/sessions/session/materials/asset/media?turn=1", headers=auth_headers("owner")
    )
    assert first.json()["url"] != second.json()["url"]
    assert first.headers["cache-control"] == "no-store"
    assert first.headers["x-request-id"] == inventory.calls[0][2]
    assert storage.paths == [("owner/course-1/job/final.mp4", 60)] * 2
    assert sessions.load("session", owner_id="owner").model_dump_json() == before


@pytest.mark.parametrize(
    "variant,status",
    [
        ("foreign", 404),
        ("foreign_asset", 404),
        ("stale_turn", 409),
        ("expired", 409),
        ("deleted_source", 404),
        ("changed_source", 409),
        ("changed_clip", 404),
        ("missing_graph_asset", 404),
        ("closed", 409),
    ],
)
async def test_media_rejections_do_not_sign_or_mutate_session(
    stack: tuple[Any, ...], variant: str, status: int
) -> None:
    client, courses, sessions, graphs, inventory, storage, _app = stack
    owner, asset_id, turn = "owner", "asset", 1
    session = sessions.load("session", owner_id="owner")
    if variant == "foreign":
        owner = "other"
    elif variant == "foreign_asset":
        asset_id = "foreign"
    elif variant == "stale_turn":
        turn = 2
    elif variant == "expired":
        session = session.model_copy(update={"started_at": _NOW - timedelta(hours=1)})
    elif variant == "deleted_source":
        courses.course = None
    elif variant == "changed_source":
        courses.course.modules[0].lessons[0].segments.activate.prose = "Different"
    elif variant == "changed_clip":
        inventory.clips = ()
    elif variant == "missing_graph_asset":
        graph = graphs.load("graph", owner_id="owner")
        graph.nodes[0].assets = []
        graphs.save(graph, owner_id="owner")
    else:
        session = session.model_copy(update={"status": SessionStatus.CLOSED})
    sessions.save(session, owner_id="owner")
    before = session.model_dump_json()
    response = await client.get(
        f"/api/live/sessions/session/materials/{asset_id}/media?turn={turn}",
        headers=auth_headers(owner),
    )
    assert response.status_code == status
    assert storage.paths == []
    assert sessions.load("session", owner_id="owner").model_dump_json() == before


@pytest.mark.parametrize("changed", [False, True])
async def test_revoked_source_blocks_graph_reopen_extension_session_turn_and_voice(
    stack: tuple[Any, ...], changed: bool
) -> None:
    from unittest.mock import AsyncMock
    from uuid import uuid4

    from lunaris_api.live.dependencies import get_live_graph_service
    from lunaris_api.live.service import LiveGraphService
    from lunaris_api.live.session.dependencies import get_live_session_service
    from lunaris_api.live.session.service import LiveSessionService
    from lunaris_api.live.voice.dependencies import get_live_voice_service
    from lunaris_api.live.voice.session_reader import StoredVoiceSessions
    from lunaris_live.graph import StubGraphCompiler
    from lunaris_live.session import MemoryKnowledgeStore, StubGrader, StubTutor
    from lunaris_live.voice.service import VoiceService

    client, courses, sessions, graphs, _inventory, _storage, app = stack
    access = StudioCorpusAccessGuard(courses)
    compiler, tutor, grader, provider = (
        AsyncMock(spec=StubGraphCompiler),
        AsyncMock(spec=StubTutor),
        AsyncMock(spec=StubGrader),
        AsyncMock(),
    )
    knowledge = MemoryKnowledgeStore()
    graph_service = LiveGraphService(compiler, graphs, source_access=access)
    session_service = LiveSessionService(
        graphs,
        sessions,
        knowledge=knowledge,
        tutor=tutor,
        grader=grader,
        session_budget_s=1800,
        source_access=access,
    )
    voice = VoiceService(
        StoredVoiceSessions(sessions, graphs=graphs, source_access=access), provider
    )
    app.dependency_overrides[get_live_graph_service] = lambda: graph_service
    app.dependency_overrides[get_live_session_service] = lambda: session_service
    app.dependency_overrides[get_live_voice_service] = lambda: voice
    before = sessions.load("session", owner_id="owner").model_dump_json()
    if changed:
        courses.course.modules[0].lessons[0].segments.activate.prose = "New revision"
    else:
        courses.course = None
    requests = [
        ("GET", "/api/live/graphs/graph", None),
        ("POST", "/api/live/graphs/graph/extend", {"request": "More detail", "anchors": []}),
        ("GET", "/api/live/sessions/session", None),
        ("POST", "/api/live/sessions", {"graphId": "graph"}),
        ("POST", "/api/live/sessions/session/turns", {"answer": "A purpose", "answeringSeq": 1}),
        (
            "POST",
            "/api/live/sessions/session/voice/speech",
            {"source": {"turnSeq": 1, "runId": "turn"}, "operationId": str(uuid4())},
        ),
    ]
    for method, path, body in requests:
        response = await client.request(method, path, json=body, headers=auth_headers("owner"))
        assert response.status_code == (409 if changed else 404), (path, response.text)
    assert sessions.load("session", owner_id="owner").model_dump_json() == before
    assert compiler.mock_calls == tutor.mock_calls == grader.mock_calls == provider.mock_calls == []


async def test_source_deleted_during_inventory_does_not_receive_media_url(
    stack: tuple[Any, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, courses, sessions, _graphs, inventory, storage, _app = stack
    entered, release = asyncio.Event(), asyncio.Event()
    original_load = inventory.load

    async def paused_load(course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        result = await original_load(course_id, owner_id=owner_id, run_id=run_id)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(inventory, "load", paused_load)
    before = sessions.load("session", owner_id="owner").model_dump_json()
    pending = asyncio.create_task(
        client.get(
            "/api/live/sessions/session/materials/asset/media?turn=1", headers=auth_headers("owner")
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        courses.course = None
        release.set()
        response = await pending
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
    assert response.status_code == 404
    assert storage.paths == []
    assert sessions.load("session", owner_id="owner").model_dump_json() == before
