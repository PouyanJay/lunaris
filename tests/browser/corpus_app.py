"""Authenticated corpus browser fixture with the real database graph store."""

import asyncio
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.dependencies import get_live_graph_service
from lunaris_api.live.service import LiveGraphService
from lunaris_live.corpus.schemas.provenance import CorpusProvenance
from lunaris_live.corpus.schemas.reference import CorpusReference
from lunaris_live.corpus.schemas.snapshot import CorpusSnapshot
from lunaris_live.graph import StubGraphCompiler, SupabaseGraphStore
from lunaris_runtime.persistence import SupabaseCourseStore

JWT_SECRET = "browser-fixture-signing-key-with-at-least-sixty-four-bytes-for-tests-only"


class _FixtureCorpusResolver:
    async def resolve(
        self, reference: CorpusReference, *, owner_id: str, run_id: str
    ) -> CorpusSnapshot:
        assert owner_id
        assert reference.course_id == "corpus-fixture"
        course = await asyncio.to_thread(
            courses.load, f"corpus-fixture-{owner_id}", owner_id=owner_id
        )
        return CorpusSnapshot(
            source=CorpusProvenance(
                course_id=reference.course_id,
                title=course.topic,
                digest="a" * 64,
                run_id=run_id,
                adapter_version="studio-v1",
                status="pending",
            ),
            sections=[],
        )


app = create_app()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Run-Id"],
)
courses = SupabaseCourseStore(
    url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
)
store = SupabaseGraphStore(
    url_env="LOCAL_SUPABASE_URL", service_key_env="LOCAL_SUPABASE_SERVICE_KEY"
)
service = LiveGraphService(StubGraphCompiler(), store, corpus_resolver=_FixtureCorpusResolver())
app.dependency_overrides[get_settings] = lambda: Settings(
    pipeline="stub",
    course_dir=Path("/tmp/lunaris-corpus-browser-test"),
    env_file=Path("/nonexistent/lunaris-browser-test.env"),
    supabase_jwt_secret=JWT_SECRET,
    cors_origins=("*",),
)
app.dependency_overrides[get_live_graph_service] = lambda: service
