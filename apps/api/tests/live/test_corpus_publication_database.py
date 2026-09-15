"""Real course snapshot, model orchestration, authenticated API and Postgres publication."""

import json
import os
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
from lunaris_api.live.corpus.preparer import CorpusGraphPreparer
from lunaris_api.live.corpus.studio_resolver import StudioCorpusResolver
from lunaris_api.live.dependencies import get_live_graph_service
from lunaris_api.live.service import LiveGraphService
from lunaris_live.corpus.mapping.asset_mapper import AssetMapper
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.corpus.stores.supabase_snapshot_store import SupabaseCorpusSnapshotStore
from lunaris_live.corpus.video.schemas.inventory import VideoGap, VideoInventory
from lunaris_live.graph import ClaudeGraphCompiler, SupabaseGraphStore
from lunaris_runtime.persistence import SupabaseCourseStore
from lunaris_runtime.schema import Course
from test_studio_corpus_resolver import course_payload

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.getenv("LOCAL_SUPABASE_SERVICE_KEY"), reason="local database required"
    ),
]


class FixtureProvider:
    def __init__(self, snapshot: CorpusSnapshot) -> None:
        self.sections = snapshot.sections
        self.calls = 0

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.calls += 1
        assert "PRIVATE KEY" not in prompt
        if prompt.startswith("You are mapping a topic"):
            payload = _concept_response()
        elif prompt.startswith("You are writing the teaching notes"):
            payload = _teaching_response()
        elif prompt.startswith("Independently verify the complete authored"):
            payload = self._grounding_response()
        elif prompt.startswith("Map exact supplied"):
            payload = self._mapping_response(verified=False)
        else:
            assert prompt.startswith("Independently verify every proposed")
            payload = self._mapping_response(verified=True)
        return AIMessage(content=json.dumps(payload))

    def _grounding_response(self) -> dict[str, object]:
        return {
            "nodes": [
                {
                    "nodeId": "consent",
                    "classification": "source",
                    "supported": True,
                    "rationale": "Exact course passages support consent and its purpose.",
                    "evidence": [{"locator": s.locator, "quote": s.text} for s in self.sections],
                }
            ]
        }

    def _mapping_response(self, *, verified: bool) -> dict[str, object]:
        return {
            "mappings": [
                {
                    "nodeId": "consent",
                    "locator": s.locator,
                    **({"approved": True, "evidence": [s.text]} if verified else {}),
                }
                for s in self.sections
            ]
        }


def _concept_response() -> dict[str, object]:
    return {
        "concepts": [
            {
                "id": "consent",
                "name": "Consent",
                "definition": "Consent has a purpose.",
                "requires": [],
            }
        ]
    }


def _teaching_response() -> dict[str, object]:
    return {
        "objective": "Explain consent",
        "misconceptions": [],
        "depth": "applied",
        "criteria": [{"kind": "explain", "statement": "State the purpose"}],
    }


class FixtureVideoInventory:
    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        return VideoInventory(gaps=(VideoGap(reason="no_ready_video"),))


async def test_authenticated_publication_keeps_answers_private_and_persists_complete_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    owner, other, course_id = str(uuid4()), str(uuid4()), uuid4().hex
    courses = SupabaseCourseStore(
        url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
    )
    snapshots = SupabaseCorpusSnapshotStore(
        url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
    )
    graphs = SupabaseGraphStore(
        url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
    )
    resolver = StudioCorpusResolver(courses, snapshots)
    payload = course_payload()
    payload["id"] = course_id
    with psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True) as db:
        try:
            db.execute("insert into auth.users(id) values (%s),(%s)", (owner, other))
            courses.save(Course.model_validate(payload), owner_id=owner)
            from lunaris_live.corpus.schemas.reference import CorpusReference

            source = await resolver.resolve(
                CorpusReference(course_id=course_id), owner_id=owner, run_id="fixture"
            )
            provider = FixtureProvider(source)
            service = LiveGraphService(
                ClaudeGraphCompiler("fixture", client=provider),
                graphs,
                corpus_resolver=resolver,
                corpus_preparer=CorpusGraphPreparer(
                    AssetMapper("fixture", client=provider), FixtureVideoInventory()
                ),
            )
            app = create_app()
            app.dependency_overrides[get_settings] = lambda: settings_for(
                tmp_path, supabase_jwt_secret=JWT_SECRET
            )
            app.dependency_overrides[get_live_graph_service] = lambda: service
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/live/graphs",
                    headers=auth_headers(owner),
                    json={"topic": "Consent", "corpus": {"courseId": course_id}},
                )
                assert response.status_code == 201, response.text
                result = response.json()
                assert result["corpus"]["status"] == "verified", result
                assert result["mappingReport"]["status"] == "passed"
                assert provider.calls == 5
                denied = await client.get(
                    f"/api/live/graphs/{result['graphId']}", headers=auth_headers(other)
                )
                assert denied.status_code == 404
            stored = db.execute(
                "select payload from live_graphs where id=%s and user_id=%s",
                (result["graphId"], owner),
            ).fetchone()[0]
            assert stored == result
            assert "PRIVATE KEY" not in json.dumps(stored)
            private = db.execute(
                "select payload from live_corpus_snapshots where course_id=%s and owner_id=%s",
                (course_id, owner),
            ).fetchone()[0]
            assert private["source"]["digest"] == stored["corpus"]["digest"]
            assert "PRIVATE KEY" in json.dumps(private)
            logs = capsys.readouterr().out
            assert "PRIVATE KEY" not in logs
            entries = [json.loads(line) for line in logs.splitlines() if line.startswith("{")]
            events = {
                entry["event"]
                for entry in entries
                if entry.get("run_id") == result["corpus"]["runId"]
            }
            assert {
                "live.graph.grounding_verified",
                "live.corpus.assets_mapped",
                "live.corpus.prepared",
                "live.graph.compile_finished",
            } <= events
        finally:
            db.execute("delete from auth.users where id in (%s,%s)", (owner, other))
