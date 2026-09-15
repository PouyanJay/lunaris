"""Production corpus services over real stores; deterministic model and synthetic clip inventory."""

import asyncio
import json
import os
from hashlib import sha256
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_course_store
from lunaris_api.live.corpus.access_guard import StudioCorpusAccessGuard
from lunaris_api.live.corpus.dependencies import get_corpus_media_resolver
from lunaris_api.live.corpus.media_resolver import CorpusMediaResolver
from lunaris_api.live.corpus.models.media_services import CorpusMediaServices
from lunaris_api.live.corpus.preparer import CorpusGraphPreparer
from lunaris_api.live.corpus.studio_resolver import StudioCorpusResolver
from lunaris_api.live.dependencies import get_live_graph_service
from lunaris_api.live.service import LiveGraphService
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.corpus.mapping.asset_mapper import AssetMapper
from lunaris_live.corpus.stores.supabase_snapshot_store import SupabaseCorpusSnapshotStore
from lunaris_live.corpus.video.schemas.clip import VideoClip
from lunaris_live.corpus.video.schemas.inventory import VideoInventory
from lunaris_live.graph import ClaudeGraphCompiler, SupabaseGraphStore
from lunaris_live.session import StubGrader, StubTutor, SupabaseKnowledgeStore, SupabaseSessionStore
from lunaris_live.session.transactions.supabase_backend import SupabaseGraphTransactions
from lunaris_runtime.persistence import SupabaseCourseStore, SupabaseVideoStorage

JWT_SECRET = "browser-fixture-signing-key-with-at-least-sixty-four-bytes-for-tests-only"
ROOT = Path(__file__).resolve().parents[2]
MEDIA = ROOT / "packages/video/src/lunaris_video/assets/stub.mp4"
VIDEO_DIGEST = sha256(MEDIA.read_bytes()).hexdigest()
CLIP = VideoClip.model_validate(
    {
        "jobId": "browser-clip",
        "sourceDigest": VIDEO_DIGEST,
        "locator": f"video:browser-clip:{VIDEO_DIGEST}:500:1400",
        "startS": 0.5,
        "endS": 1.4,
        "durationS": 2,
        "title": "Consent in context",
        "transcript": [
            {
                "startS": 0.5,
                "endS": 1.4,
                "text": "Consent has a purpose.",
            }
        ],
    }
)


class FixtureModel:
    async def ainvoke(self, prompt: str) -> AIMessage:
        assert "PRIVATE ANSWER" not in prompt
        if prompt.startswith("You are mapping a topic"):
            result = {
                "concepts": [
                    {
                        "id": "consent",
                        "name": "Consent",
                        "definition": "Consent has a purpose.",
                        "requires": [],
                    }
                ]
            }
        elif prompt.startswith("You are writing the teaching notes"):
            result = {
                "objective": "Explain consent",
                "misconceptions": [],
                "depth": "applied",
                "criteria": [{"kind": "explain", "statement": "Explain the purpose of consent."}],
            }
        elif prompt.startswith("Independently verify the complete authored"):
            source = json.loads(prompt.rsplit("\n", 1)[-1])
            result = {
                "nodes": [
                    {
                        "nodeId": "consent",
                        "classification": "source",
                        "supported": True,
                        "rationale": "The supplied passages explain consent.",
                        "evidence": [
                            {"locator": section["locator"], "quote": section["text"]}
                            for section in source["sections"]
                        ],
                    }
                ]
            }
        else:
            assert prompt.startswith(("Map exact supplied", "Independently verify every proposed"))
            data = json.loads(prompt.split("SOURCE DATA:\n", 1)[1].split("\nPROPOSED PAIRS:", 1)[0])
            verified = prompt.startswith("Independently")
            result = {
                "mappings": [
                    {
                        "nodeId": "consent",
                        "locator": candidate["locator"],
                        **({"approved": True, "evidence": [candidate["text"]]} if verified else {}),
                    }
                    for candidate in data["candidates"]
                ]
            }
        return AIMessage(content=json.dumps(result))


class FixtureInventory:
    async def load(self, course_id: str, *, owner_id: str, run_id: str) -> VideoInventory:
        course = await asyncio.to_thread(courses.load, course_id, owner_id=owner_id)
        assert course.id == course_id and run_id
        return VideoInventory(clips=(CLIP,))


class HttpsLocalVideoStorage(SupabaseVideoStorage):
    """Browser bridges HTTPS to local HTTP storage, retaining the genuine signed capability."""

    async def signed_url(self, *, path: str, expires_in_seconds: int = 3600) -> str:
        signed = await super().signed_url(path=path, expires_in_seconds=expires_in_seconds)
        return signed.replace("http://", "https://", 1)


stores = {"url_env": "LOCAL_SUPABASE_URL", "service_key_env": "LOCAL_SUPABASE_SERVICE_KEY"}
courses = SupabaseCourseStore(**stores)
graphs = SupabaseGraphStore(**stores)
snapshots = SupabaseCorpusSnapshotStore(**stores)
sessions = SupabaseSessionStore(**stores)
knowledge = SupabaseKnowledgeStore(**stores)
storage = HttpsLocalVideoStorage(**stores)
access = StudioCorpusAccessGuard(courses)
resolver = StudioCorpusResolver(courses, snapshots)
inventory = FixtureInventory()
model = FixtureModel()
compiler = LiveGraphService(
    ClaudeGraphCompiler("fixture", client=model),
    graphs,
    corpus_resolver=resolver,
    source_access=access,
    corpus_preparer=CorpusGraphPreparer(AssetMapper("fixture", client=model), inventory),
)
loop = LiveSessionService(
    graphs,
    sessions,
    knowledge=knowledge,
    tutor=StubTutor(),
    grader=StubGrader(),
    session_budget_s=1800,
    source_access=access,
    transactions=SupabaseGraphTransactions(),
)
media = CorpusMediaResolver(
    CorpusMediaServices(sessions, graphs, access, inventory, storage), session_budget_s=1800
)
app = create_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Run-Id"],
)
app.dependency_overrides[get_settings] = lambda: Settings(
    pipeline="stub",
    supabase_url=os.getenv("LOCAL_SUPABASE_URL"),
    supabase_service_role_key=os.getenv("LOCAL_SUPABASE_SERVICE_KEY"),
    course_dir=Path("/tmp/lunaris-live-corpus-browser"),
    env_file=Path("/nonexistent/lunaris-browser.env"),
    supabase_jwt_secret=JWT_SECRET,
    cors_origins=("*",),
)
app.dependency_overrides[get_course_store] = lambda: courses
app.dependency_overrides[get_live_graph_service] = lambda: compiler
app.dependency_overrides[get_live_session_service] = lambda: loop
app.dependency_overrides[get_corpus_media_resolver] = lambda: media
