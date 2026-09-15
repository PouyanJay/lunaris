"""The authenticated media read traverses real owner-bound course/graph/session persistence."""

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
from _auth import JWT_SECRET, auth_headers
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.live.corpus.access_guard import StudioCorpusAccessGuard
from lunaris_api.live.corpus.dependencies import get_corpus_media_resolver
from lunaris_api.live.corpus.media_resolver import CorpusMediaResolver
from lunaris_api.live.corpus.models.media_services import CorpusMediaServices
from lunaris_api.live.corpus.normalize_course import normalize_course
from lunaris_live.corpus.schemas.asset import NodeAsset
from lunaris_live.corpus.schemas.asset_verification import AssetVerification
from lunaris_live.graph import ConceptGraph, ConceptNode, SupabaseGraphStore
from lunaris_live.session import Session, SupabaseSessionStore
from lunaris_runtime.persistence import SupabaseCourseStore
from lunaris_runtime.schema import Course
from test_corpus_media_api import Inventory, Storage, clip_fixture
from test_studio_corpus_resolver import course_payload

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY"), reason="local database required"
    ),
]


async def test_media_read_with_real_database_preserves_state_and_refuses_changed_course(
    tmp_path: Path,
) -> None:
    owner, other, course_id, graph_id, session_id = (str(uuid4()) for _ in range(5))
    env = {"url_env": "LOCAL_SUPABASE_URL", "service_key_env": "LOCAL_SUPABASE_SERVICE_KEY"}
    courses, graphs, sessions = (
        SupabaseCourseStore(**env),
        SupabaseGraphStore(**env),
        SupabaseSessionStore(**env),
    )
    payload = course_payload()
    payload["id"] = course_id
    course = Course.model_validate(payload)
    source = normalize_course(course, run_id="initial").source.model_copy(
        update={"status": "verified"}
    )
    clip = clip_fixture()
    asset = NodeAsset(
        asset_id="asset",
        kind="video_clip",
        origin="ingested",
        locator=clip.locator,
        source_digest=source.digest,
        clip=clip,
        verification=AssetVerification(
            run_id="mapping", verifier_version="fixture", source_digest=source.digest
        ),
    )
    graph = ConceptGraph(
        graph_id=graph_id,
        topic="Consent",
        corpus=source,
        nodes=[ConceptNode(id="node", name="Consent", definition="Purpose", assets=[asset])],
    )
    session = Session.model_validate(
        {
            "sessionId": session_id,
            "graphId": graph_id,
            "startedAt": datetime.now(UTC),
            "turns": [
                {
                    "seq": 1,
                    "move": {"kind": "introduce", "nodeId": "node", "reason": "Teach"},
                    "tutor": "Consent",
                    "runId": "turn",
                    "materials": [asset],
                }
            ],
        }
    )
    inventory, storage = Inventory(clip), Storage()
    resolver = CorpusMediaResolver(
        CorpusMediaServices(sessions, graphs, StudioCorpusAccessGuard(courses), inventory, storage),
        session_budget_s=1800,
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings_for(
        tmp_path, supabase_jwt_secret=JWT_SECRET
    )
    app.dependency_overrides[get_corpus_media_resolver] = lambda: resolver
    path = f"/api/live/sessions/{session_id}/materials/asset/media?turn=1"
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
        try:
            db.execute("insert into auth.users(id) values (%s),(%s)", (owner, other))
            courses.save(course, owner_id=owner)
            graphs.save(graph, owner_id=owner)
            sessions.save(session, owner_id=owner)
            before = db.execute(
                "select payload from public.live_sessions where id=%s", (session_id,)
            ).fetchone()[0]
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(path, headers=auth_headers(owner))
                assert response.status_code == 200
                foreign = await client.get(path, headers=auth_headers(other))
                assert foreign.status_code == 404
                course.modules[0].lessons[0].segments.activate.prose = "A different revision"
                courses.save(course, owner_id=owner)
                changed = await client.get(path, headers=auth_headers(owner))
                assert changed.status_code == 409
            assert storage.paths == [(f"{owner}/{course_id}/job/final.mp4", 60)]
            assert (
                db.execute(
                    "select payload from public.live_sessions where id=%s", (session_id,)
                ).fetchone()[0]
                == before
            )
        finally:
            db.execute(
                "delete from public.live_sessions where id=%s and user_id=%s", (session_id, owner)
            )
            db.execute(
                "delete from public.live_graphs where id=%s and user_id=%s", (graph_id, owner)
            )
            db.execute("delete from public.courses where id=%s and user_id=%s", (course_id, owner))
            db.execute("delete from auth.users where id in (%s,%s)", (owner, other))
